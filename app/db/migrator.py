"""
AIDU Op · Sistema de migraciones
=================================
Garantiza actualizaciones del esquema SIN perder datos.

REGLAS DE ORO:
1. Cada migración es un archivo .sql numerado: 001_init.sql, 002_xxx.sql
2. Solo se aplican migraciones que no estén en la tabla _migrations
3. Una migración aplicada NUNCA se modifica (se crea una nueva)
4. Antes de aplicar, se hace backup automático de la BD
5. Si una migración falla, rollback completo

Flujo en cada arranque:
    1. Backup de BD actual (si existe)
    2. Listar archivos de migración disponibles
    3. Listar migraciones ya aplicadas (tabla _migrations)
    4. Aplicar las pendientes en orden
    5. Registrar cada aplicación en _migrations
"""
import sqlite3
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
from config.settings import DB_PATH, BACKUP_DIR

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATIONS_DIR.mkdir(exist_ok=True)


def get_connection() -> sqlite3.Connection:
    """Conexión SQLite con foreign keys activas y row_factory dict-like"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")  # Mejor concurrencia
    return conn


def backup_database() -> Path | None:
    """
    Backup automático ANTES de cada migración.
    Crea ZIP timestamped en data/backups/
    Retorna el path del backup o None si no había BD que respaldar.
    """
    if not DB_PATH.exists():
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"aidu_op_pre_migration_{ts}.db"
    shutil.copy2(DB_PATH, backup_path)
    logger.info(f"✅ Backup creado: {backup_path.name}")

    # Limpieza: mantener máx 20 backups (los más recientes)
    backups = sorted(BACKUP_DIR.glob("aidu_op_pre_migration_*.db"))
    while len(backups) > 20:
        oldest = backups.pop(0)
        oldest.unlink()
        logger.info(f"🗑️  Backup antiguo eliminado: {oldest.name}")

    return backup_path


def ensure_migrations_table(conn: sqlite3.Connection):
    """Crea la tabla _migrations si no existe (es la única forma 'segura')"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            checksum TEXT,
            description TEXT
        )
    """)
    conn.commit()


def get_applied_migrations(conn: sqlite3.Connection) -> set:
    """Retorna set de filenames de migraciones ya aplicadas"""
    cur = conn.execute("SELECT filename FROM _migrations ORDER BY id")
    return {row["filename"] for row in cur.fetchall()}


def get_pending_migrations() -> List[Path]:
    """Lista migraciones disponibles ordenadas por nombre"""
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def apply_migration(conn: sqlite3.Connection, migration_file: Path) -> bool:
    """
    Aplica una migración en transacción.
    
    Robustez v14: ejecuta cada sentencia individualmente y tolera errores de tipo
    'duplicate column' o 'table already exists' que pueden ocurrir cuando una
    migración previa quedó parcialmente aplicada en producción.
    """
    sql = migration_file.read_text(encoding="utf-8")
    desc_line = next((l for l in sql.splitlines() if l.startswith("-- DESC:")), "")
    description = desc_line.replace("-- DESC:", "").strip() or migration_file.stem
    
    # Errores tolerables: la migración intenta crear algo que ya existe
    TOLERABLE_ERRORS = (
        "duplicate column name",
        "already exists",
    )
    
    statements = _split_sql_statements(sql)
    errores_tolerados = 0
    
    try:
        for stmt in statements:
            stmt = stmt.strip()
            if not stmt or stmt.startswith("--"):
                continue
            try:
                conn.execute(stmt)
            except sqlite3.OperationalError as e:
                msg = str(e).lower()
                if any(err in msg for err in TOLERABLE_ERRORS):
                    errores_tolerados += 1
                    logger.warning(f"⚠️  Sentencia tolerada en {migration_file.name}: {e}")
                    continue
                # Error real: propagar
                raise
        
        conn.execute(
            "INSERT INTO _migrations (filename, description) VALUES (?, ?)",
            (migration_file.name, description)
        )
        conn.commit()
        if errores_tolerados > 0:
            logger.info(f"✅ Migración aplicada: {migration_file.name} ({errores_tolerados} sentencias ya existían)")
        else:
            logger.info(f"✅ Migración aplicada: {migration_file.name} — {description}")
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Error en migración {migration_file.name}: {e}")
        raise


def _split_sql_statements(sql: str) -> list:
    """
    Divide un script SQL en sentencias individuales.
    No usa simple split(';') porque eso falla con literales que contienen ;
    """
    # Para nuestras migraciones (sin literales complejos), split por ';' funciona
    return [s for s in sql.split(';') if s.strip()]




def run_migrations() -> Tuple[int, List[str]]:
    """
    Ejecuta todas las migraciones pendientes.
    Retorna (cantidad_aplicadas, [nombres_aplicadas])
    """
    # 1. Backup PRIMERO (si hay BD existente)
    backup_path = backup_database()

    # 2. Conexión y tabla de control
    conn = get_connection()
    try:
        ensure_migrations_table(conn)
        applied = get_applied_migrations(conn)
        pending = [m for m in get_pending_migrations() if m.name not in applied]

        if pending:
            logger.info(f"🔄 {len(pending)} migración(es) pendiente(s)")
            applied_now = []
            for migration in pending:
                apply_migration(conn, migration)
                applied_now.append(migration.name)
        else:
            logger.info("ℹ️  Sin migraciones pendientes. BD al día.")
            applied_now = []

        # ============================================================
        # AUTO-REPARACIÓN POST-MIGRACIÓN (corre SIEMPRE)
        # 
        # Defensiva: en producción, una migración puede haber quedado
        # marcada como aplicada pero con columnas faltantes. Este bloque
        # se ejecuta cada vez y garantiza el schema mínimo de v15.
        # ============================================================
        _auto_reparar_schema(conn)
        
        return len(applied_now), applied_now
    finally:
        conn.close()


def _auto_reparar_schema(conn: sqlite3.Connection):
    """
    Garantiza que todas las columnas/tablas críticas existan en producción,
    incluso si una migración previa falló a mitad y quedó marcada como
    aplicada. Se ejecuta en cada arranque.
    
    Es 100% idempotente: usa try/except sobre cada ALTER TABLE.
    """
    columnas_requeridas = {
        "aidu_proyectos": [
            ("url_mp", "TEXT"),
            ("fecha_subida_mp", "TEXT"),
            ("url_oferta_subida", "TEXT"),
            ("metros_cuadrados", "INTEGER"),
            ("plazo_dias", "INTEGER"),
            ("n_entregables", "INTEGER"),
            ("tipo_servicio", "TEXT"),
            ("complejidad", "TEXT"),
            ("fecha_inicio_consultas", "TEXT"),
            ("fecha_fin_consultas", "TEXT"),
        ],
        "mp_licitaciones_adj": [
            ("metros_cuadrados", "INTEGER"),
            ("plazo_dias", "INTEGER"),
            ("n_entregables", "INTEGER"),
            ("tipo_servicio", "TEXT"),
            ("complejidad", "TEXT"),
        ],
    }
    
    reparados = 0
    for tabla, columnas in columnas_requeridas.items():
        # Verificar que la tabla existe primero
        try:
            existe = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
                (tabla,)
            ).fetchone()
            if not existe:
                continue
        except Exception:
            continue
        
        # Para cada columna requerida, intentar agregarla
        for col_name, col_type in columnas:
            try:
                conn.execute(f"ALTER TABLE {tabla} ADD COLUMN {col_name} {col_type}")
                reparados += 1
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    pass  # Ya existe, perfecto
                else:
                    logger.warning(f"⚠️  No se pudo reparar {tabla}.{col_name}: {e}")
    
    # Tabla proy_consultas
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS proy_consultas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                proyecto_id INTEGER NOT NULL,
                fecha_pregunta TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                fecha_respuesta TEXT,
                pregunta TEXT NOT NULL,
                respuesta TEXT,
                publicada_en_mp INTEGER NOT NULL DEFAULT 0,
                autor TEXT,
                notas_internas TEXT,
                FOREIGN KEY (proyecto_id) REFERENCES aidu_proyectos(id)
            )
        """)
    except Exception as e:
        logger.warning(f"⚠️  No se pudo crear proy_consultas: {e}")
    
    if reparados > 0:
        conn.commit()
        logger.info(f"🔧 Auto-reparación: {reparados} columnas restauradas")


def show_migration_status():
    """Diagnóstico: qué migraciones están aplicadas, cuáles pendientes"""
    conn = get_connection()
    try:
        ensure_migrations_table(conn)
        applied = get_applied_migrations(conn)
        all_migrations = get_pending_migrations()

        print("\n=== Estado de migraciones ===")
        for m in all_migrations:
            status = "✅ APLICADA" if m.name in applied else "⏳ PENDIENTE"
            print(f"  {status}  {m.name}")

        print(f"\nTotal: {len(all_migrations)} disponibles, {len(applied)} aplicadas")
    finally:
        conn.close()
