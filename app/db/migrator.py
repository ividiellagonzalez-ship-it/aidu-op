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
    Si falla, rollback completo y propaga el error.
    """
    sql = migration_file.read_text(encoding="utf-8")
    desc_line = next((l for l in sql.splitlines() if l.startswith("-- DESC:")), "")
    description = desc_line.replace("-- DESC:", "").strip() or migration_file.stem

    try:
        # SQLite ejecuta múltiples statements con executescript
        conn.executescript(sql)
        conn.execute(
            "INSERT INTO _migrations (filename, description) VALUES (?, ?)",
            (migration_file.name, description)
        )
        conn.commit()
        logger.info(f"✅ Migración aplicada: {migration_file.name} — {description}")
        return True
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Error en migración {migration_file.name}: {e}")
        raise


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

        if not pending:
            logger.info("ℹ️  Sin migraciones pendientes. BD al día.")
            return 0, []

        logger.info(f"🔄 {len(pending)} migración(es) pendiente(s)")
        applied_now = []
        for migration in pending:
            apply_migration(conn, migration)
            applied_now.append(migration.name)

        return len(applied_now), applied_now
    finally:
        conn.close()


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
