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
import os
import time
from pathlib import Path
from datetime import datetime
from typing import List, Optional, Tuple
from config.settings import DB_PATH, BACKUP_DIR
from app.db.exceptions import TursoUnavailableError

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"
MIGRATIONS_DIR.mkdir(exist_ok=True)


# ============================================================
# Capa de persistencia Turso (S12.1, endurecida en S12.2.1)
# ============================================================
# El contenedor de Streamlit Cloud borra /tmp en cada reboot, perdiendo la
# BD madre. Para fijarlo sin romper los ~80 callsites de get_connection(),
# usamos libsql-experimental en modo "embedded replica":
#   - Mantiene una réplica local del archivo SQLite en DB_PATH.
#   - Al arranque, hidrata DB_PATH desde la BD remota Turso.
#   - Después de cada commit local, pushea los cambios a Turso.
# Las queries y la API siguen pasando por sqlite3.Connection nativo, así que
# row_factory, sqlite3.Row, sqlite3.OperationalError y demás se comportan igual.
#
# Modos legítimos (S12.2.1):
#   1) Sin credenciales (TURSO_DATABASE_URL/TURSO_AUTH_TOKEN ausentes):
#      modo dev/CI/tests. get_connection() devuelve sqlite3.Connection puro
#      contra DB_PATH local. Comportamiento previo intacto.
#   2) Con credenciales y handshake OK: get_connection() devuelve un proxy
#      que pushea cada commit a Turso vía libsql sync.
#   3) Con credenciales pero handshake falla los N reintentos: se levanta
#      TursoUnavailableError. ANTES (pre-S12.2.1) caía silenciosamente al
#      SQLite local — patrón fatal en runners efímeros (Run #3 perdió 446
#      licitaciones de esa forma). Ahora se aborta para evitar pérdida.

# Política de reintentos del handshake con Turso. Tres intentos con backoff
# exponencial (1s, 4s, 16s = 21s total de espera) cubren las fallas
# transitorias típicas de red sin agotar el timeout de 25 min del workflow.
# Diseñado para tolerar el bug 'Invalid header bit 123 expected 0 or 1' del
# Run #3 si resulta intermitente; si es determinístico, igual aborta limpio.
_TURSO_HANDSHAKE_MAX_INTENTOS = 3
_TURSO_HANDSHAKE_BACKOFF_BASE_S = 1.0  # 1, 4, 16 segundos

_TURSO_CONN = None  # libsql.Connection persistente, solo para sync
_TURSO_AVAILABLE: Optional[bool] = None  # cache del último intento de conexión


def _read_turso_credentials() -> Optional[Tuple[str, str]]:
    """
    Lee TURSO_DATABASE_URL + TURSO_AUTH_TOKEN desde st.secrets (Streamlit Cloud)
    o variables de entorno (local). Devuelve (url, token) si ambas existen y no
    están vacías, o None si Turso no está configurado.
    """
    url, token = "", ""
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            url = (st.secrets.get("TURSO_DATABASE_URL", "") or "").strip()
            token = (st.secrets.get("TURSO_AUTH_TOKEN", "") or "").strip()
    except Exception:
        pass
    if not url:
        url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    if not token:
        token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if url and token:
        return url, token
    return None


def _ensure_turso_replica() -> bool:
    """
    Garantiza que la réplica embebida con Turso esté lista. Idempotente:
    la primera llamada abre la libsql.Connection y sincroniza desde Turso;
    llamadas posteriores reutilizan la conexión y solo re-sincronizan.

    Política S12.2.1 (eliminado el fallback silencioso a SQLite):
      - Sin credenciales: devuelve False sin tocar la red. get_connection()
        usará SQLite local (modo dev/CI/tests). Comportamiento previo intacto.
      - Con credenciales y handshake exitoso: devuelve True (Turso activo).
      - Con credenciales y handshake fallido: reintenta hasta
        _TURSO_HANDSHAKE_MAX_INTENTOS con backoff exponencial. Si todos los
        intentos fallan, levanta TursoUnavailableError. Eso fuerza al
        callsite (CLI de descarga, app, etc.) a decidir explícitamente cómo
        reaccionar — antes el log "Turso no disponible, opero contra
        SQLite local" hacía que producción escribiera silenciosamente a un
        SQLite efímero sin schema y los datos se perdían (Run #3, S12.2).
    """
    global _TURSO_CONN, _TURSO_AVAILABLE
    if _TURSO_AVAILABLE is False:
        return False
    creds = _read_turso_credentials()
    if creds is None:
        # Sin credenciales: modo dev/CI/tests. NO es un error — es un modo
        # operativo legítimo, así que no se levanta excepción.
        _TURSO_AVAILABLE = False
        return False

    url, token = creds
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)

    ultimo_error: Optional[Exception] = None
    for intento in range(1, _TURSO_HANDSHAKE_MAX_INTENTOS + 1):
        try:
            if _TURSO_CONN is None:
                import libsql_experimental as libsql  # noqa: WPS433
                _TURSO_CONN = libsql.connect(
                    str(DB_PATH), sync_url=url, auth_token=token,
                )
            _TURSO_CONN.sync()
            _TURSO_AVAILABLE = True
            return True
        except Exception as e:  # noqa: BLE001 — re-emitido como TursoUnavailableError abajo
            ultimo_error = e
            # Reset de la conexión para que el próximo intento abra una nueva.
            _TURSO_CONN = None
            if intento < _TURSO_HANDSHAKE_MAX_INTENTOS:
                espera = _TURSO_HANDSHAKE_BACKOFF_BASE_S * (4 ** (intento - 1))
                logger.warning(
                    f"⚠️  Handshake con Turso falló (intento {intento}"
                    f"/{_TURSO_HANDSHAKE_MAX_INTENTOS}): {e}. "
                    f"Reintento en {espera:.0f}s."
                )
                time.sleep(espera)

    # Todos los reintentos fallaron. NO se cae a SQLite local: eso pierde
    # datos en runners efímeros (Run #3 escribió 446 licitaciones a un
    # SQLite sin schema y se perdieron). Levantar para que el CLI de
    # descarga termine con exit 2 y el operador investigue.
    _TURSO_AVAILABLE = False
    msg = (
        "Turso no disponible tras "
        f"{_TURSO_HANDSHAKE_MAX_INTENTOS} reintentos. "
        "Abortando para evitar fallback silencioso a SQLite local. "
        f"Último error: {ultimo_error}"
    )
    logger.error(f"❌ {msg}")
    raise TursoUnavailableError(
        msg,
        intentos=_TURSO_HANDSHAKE_MAX_INTENTOS,
        ultimo_error=str(ultimo_error) if ultimo_error else "",
    )


def sync_to_turso() -> bool:
    """
    Pushea cambios locales a Turso. Llamada automáticamente desde el proxy
    `_TursoConnectionProxy.commit()` y `__exit__()`. Silenciosa si Turso no
    está configurado. Devuelve True si el sync se ejecutó.
    """
    global _TURSO_CONN, _TURSO_AVAILABLE
    if not _TURSO_AVAILABLE or _TURSO_CONN is None:
        return False
    try:
        _TURSO_CONN.sync()
        return True
    except Exception as e:
        logger.warning(f"⚠️ sync→Turso falló: {e}")
        return False


class _TursoConnectionProxy:
    """
    Proxy fino sobre sqlite3.Connection que dispara `sync_to_turso()` después
    de cada `commit()` exitoso (y al salir limpio de un `with`). Solo se usa
    cuando hay credenciales Turso; en dev/CI `get_connection()` devuelve la
    sqlite3.Connection nativa sin envolver.

    No es un sqlite3.Connection real (sqlite3.Connection no admite subclassing
    limpio en CPython). Acceso por atributo y métodos no especiales se delegan
    via __getattr__. Si algún callsite hiciera `isinstance(conn, sqlite3.Connection)`
    fallaría — verificado: cero ocurrencias en el repo.
    """
    __slots__ = ("_conn",)

    def __init__(self, conn: sqlite3.Connection):
        object.__setattr__(self, "_conn", conn)

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def __setattr__(self, name, value):
        if name == "_conn":
            object.__setattr__(self, name, value)
        else:
            setattr(self._conn, name, value)

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        ret = self._conn.__exit__(exc_type, exc_val, exc_tb)
        if exc_type is None:
            sync_to_turso()
        return ret

    def commit(self):
        self._conn.commit()
        sync_to_turso()


# ============================================================
# Propagación de DDL → Turso (S12.1.5)
# ============================================================
# Bug encontrado en validación post-deploy de S12.1: el proxy de arriba
# propaga DML automáticamente al hacer commit (libsql sync), pero las
# páginas de schema (CREATE/ALTER/INDEX/DROP) NO viajan por sync. Resultado:
# las migraciones del repo dejaban schema en /tmp/AIDU_Op pero Turso quedaba
# vacío. La app aparentaba funcionar por el fallback data_semilla → /tmp.
#
# Fix: cuando hay credenciales Turso, los statements DDL viajan por canal
# separado (HTTP /v2/pipeline) además de aplicarse al SQLite local. DML
# sigue viajando por sync vía el proxy (sin cambios). Sin credenciales,
# todos los helpers de abajo son no-op silenciosos.

# Errores tolerables: la migración intenta crear algo que ya existe.
# Compartido entre apply_migration, _auto_reparar_schema y los helpers DDL
# para que la idempotencia funcione uniforme contra local y contra Turso.
TOLERABLE_ERRORS = (
    "duplicate column name",
    "already exists",
)

_DDL_PREFIXES = ("CREATE ", "ALTER ", "DROP ", "REINDEX ")


def _is_ddl(stmt: str) -> bool:
    """
    Heurística: la primera palabra significativa indica DDL. Suficientemente
    precisa para los statements del repo (CREATE TABLE, ALTER TABLE, CREATE
    INDEX, DROP INDEX). Falso para INSERT/UPDATE/DELETE/SELECT.
    """
    head = stmt.lstrip().upper()
    return any(head.startswith(p) for p in _DDL_PREFIXES)


def _hrana_post(sql: str, params: Optional[list] = None) -> dict:
    """
    POST a /v2/pipeline contra Turso con un único statement. Helper privado
    de migrator: construye payload, parametriza args via _hrana_types,
    devuelve el body JSON. None si no hay credenciales (modo dev/CI).

    Conversión Hrana centralizada en app/db/_hrana_types (S12.2). Antes,
    _query_on_turso construía args inline y serializaba floats como string
    -- bug que rompía cualquier query con parámetro float (HTTP 400 'expected
    f64'). Ahora ambos helpers (_execute_on_turso y _query_on_turso) tiran
    del mismo arg_for_value que ya validó el bootstrap S12.1.5.
    """
    from app.db._hrana_types import arg_for_value  # noqa: WPS433

    creds = _read_turso_credentials()
    if creds is None:
        return {}
    url, token = creds
    http_url = url.replace("libsql://", "https://", 1).rstrip("/") + "/v2/pipeline"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    stmt: dict = {"sql": sql}
    if params:
        stmt["args"] = [arg_for_value(p) for p in params]
    payload = {
        "requests": [
            {"type": "execute", "stmt": stmt},
            {"type": "close"},
        ]
    }
    try:
        import requests  # noqa: WPS433
        r = requests.post(http_url, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
    except Exception as e:
        raise sqlite3.OperationalError(f"Turso HTTP: {e}")
    return r.json()


def _execute_on_turso(sql: str, params: Optional[list] = None) -> bool:
    """
    Ejecuta un statement contra Turso vía HTTP /v2/pipeline. No-op silencioso
    si no hay credenciales (modo dev/CI).

    Errores remotos se mapean a sqlite3.OperationalError para que el caller
    use su tolerancia existente (TOLERABLE_ERRORS) sin distinguir local/remoto.
    Devuelve True si la llamada se ejecutó (con o sin éxito tolerable).

    S12.2: agrega soporte opcional de `params` para parametrizar DDL/DML
    (antes solo SQL crudo). Pasa por arg_for_value para que floats viajen
    como número JSON crudo, no como string.
    """
    body = _hrana_post(sql, params)
    if not body:
        return False
    for result in body.get("results", []):
        if result.get("type") == "error":
            err = result.get("error", {}).get("message", "Turso error")
            raise sqlite3.OperationalError(err)
    return True


def _query_on_turso(sql: str, params: Optional[list] = None) -> list:
    """
    Ejecuta SELECT contra Turso vía HTTP. Devuelve lista de tuplas con los
    valores ya extraídos del formato `{type, value}` del endpoint /v2/pipeline.
    Retorna [] si no hay credenciales. Errores remotos → sqlite3.OperationalError.

    S12.2: la construcción de args delega en app/db/_hrana_types.arg_for_value.
    Esto fixea un bug latente que serializaba floats como string causando
    HTTP 400 'expected f64' — el mismo bug que rompía el bootstrap antes
    del fix de S12.1.5.bis. Único call site externo conocido: app/db/health_check.py
    (solo passes ints/strings, así que el bug nunca se disparó en producción).
    """
    body = _hrana_post(sql, params)
    if not body:
        return []
    rows: list = []
    for result in body.get("results", []):
        if result.get("type") == "error":
            raise sqlite3.OperationalError(
                result.get("error", {}).get("message", "Turso error")
            )
        if result.get("type") == "ok":
            response = result.get("response", {}).get("result", {})
            for row in response.get("rows", []):
                rows.append(tuple(cell.get("value") for cell in row))
    return rows


def _apply_ddl_idempotent(conn: sqlite3.Connection, stmt: str) -> bool:
    """
    Aplica un statement DDL al SQLite local Y a Turso (si hay credenciales).
    Tolera 'already exists' / 'duplicate column' (idempotencia de migraciones).

    Devuelve True si alguno de los lados toleró el error (statement ya
    aplicado previamente). Levanta sqlite3.OperationalError ante errores
    no-tolerables, dejando al caller decidir qué hacer.
    """
    tolerated = False
    try:
        conn.execute(stmt)
    except sqlite3.OperationalError as e:
        if any(t in str(e).lower() for t in TOLERABLE_ERRORS):
            tolerated = True
        else:
            raise
    try:
        _execute_on_turso(stmt)
    except sqlite3.OperationalError as e:
        if any(t in str(e).lower() for t in TOLERABLE_ERRORS):
            tolerated = True
        else:
            raise
    return tolerated


def get_connection():
    """
    Conexión SQLite con foreign keys activas y row_factory dict-like.

    Comportamiento:
    - Sin TURSO_DATABASE_URL/TURSO_AUTH_TOKEN: sqlite3.connect(DB_PATH) puro
      (modo dev/CI, idéntico al comportamiento previo a S12.1).
    - Con credenciales Turso: hidrata DB_PATH desde la BD remota vía
      libsql-experimental antes de abrir, y devuelve un proxy que pushea a
      Turso después de cada commit. Esto fija la pérdida de datos en cold
      starts del contenedor Streamlit Cloud.
    - Con credenciales pero handshake fallido tras N reintentos:
      levanta TursoUnavailableError y NO devuelve conexión local. El
      callsite de runtime debe propagarla para evitar el fallback
      silencioso que costó las 446 licitaciones del Run #3 (S12.2.1).

    El tipo devuelto es sqlite3.Connection o un proxy con la misma API
    (__getattr__ delega al sqlite3.Connection subyacente).
    """
    turso_active = _ensure_turso_replica()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if not turso_active:
        # WAL es incompatible con la réplica embebida de libsql sobre el
        # mismo archivo (libsql usa su propio walhook). En modo Turso lo
        # saltamos; en SQLite local lo mantenemos por concurrencia.
        conn.execute("PRAGMA journal_mode = WAL")

    if turso_active:
        return _TursoConnectionProxy(conn)
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

    statements = _split_sql_statements(sql)
    errores_tolerados = 0

    try:
        for stmt in statements:
            stmt = _strip_leading_comments(stmt)
            if not stmt:
                continue
            if _is_ddl(stmt):
                # DDL: local + Turso (canal HTTP). Tolerancia compartida.
                try:
                    if _apply_ddl_idempotent(conn, stmt):
                        errores_tolerados += 1
                except sqlite3.OperationalError as e:
                    logger.warning(f"⚠️  DDL no aplicado en {migration_file.name}: {e}")
                    raise
            else:
                # DML: solo local. La sincronización a Turso ocurre en commit() vía proxy.
                try:
                    conn.execute(stmt)
                except sqlite3.OperationalError as e:
                    msg = str(e).lower()
                    if any(err in msg for err in TOLERABLE_ERRORS):
                        errores_tolerados += 1
                        logger.warning(f"⚠️  Sentencia tolerada en {migration_file.name}: {e}")
                        continue
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


def _strip_leading_comments(stmt: str) -> str:
    """
    Quita líneas de comentario `--` y líneas vacías al inicio de un chunk.

    Necesario porque _split_sql_statements solo separa por `;`, dejando
    los comentarios pegados al statement que les sigue. Si no se limpia,
    `stmt.startswith("--")` da true y el statement entero queda descartado
    junto con sus comentarios — bug pre-existente que en producción no se
    notaba porque data_semilla ya traía el schema aplicado, pero sí rompe
    el camino "migrar contra una BD vacía" que es exactamente lo que
    necesita el bootstrap de S12.1.5.
    """
    lines = stmt.split("\n")
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
        lines.pop(0)
    return "\n".join(lines).strip()




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
            ("url_mp_canonica", "TEXT"),
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
            ("url_mp_canonica", "TEXT"),
            # Trazabilidad v18:
            ("hash_raw_json", "TEXT"),
            ("fuente", "TEXT"),
            ("version_api", "TEXT"),
        ],
        "mp_licitaciones_vigentes": [
            ("url_mp_canonica", "TEXT"),
            ("metros_cuadrados", "INTEGER"),
            ("plazo_dias", "INTEGER"),
            ("n_entregables", "INTEGER"),
            ("tipo_servicio", "TEXT"),
            ("complejidad", "TEXT"),
            # Trazabilidad v18:
            ("hash_raw_json", "TEXT"),
            ("fuente", "TEXT"),
            ("version_api", "TEXT"),
        ],
        # S12.3 v2.2 — respaldo idempotente de la migración 008.
        # tipo_origen distingue items SKU (producto, CA+L1) de headers
        # de servicio (servicio LE) sobre la misma tabla. Default
        # 'producto' preserva semántica de filas pre-mig 008.
        "mp_licitaciones_items": [
            ("tipo_origen", "TEXT DEFAULT 'producto'"),
        ],
        # tipo+subtipo permiten distinguir entradas del backfill MVP
        # ('backfill_mvp_3m' / 'fase_N_*') del cron diario sin pisarse.
        "mp_ingesta_log": [
            ("tipo", "TEXT"),
            ("subtipo", "TEXT"),
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
        
        # Para cada columna requerida, intentar agregarla (local + Turso)
        for col_name, col_type in columnas:
            stmt = f"ALTER TABLE {tabla} ADD COLUMN {col_name} {col_type}"
            try:
                tolerated = _apply_ddl_idempotent(conn, stmt)
                if not tolerated:
                    reparados += 1
            except sqlite3.OperationalError as e:
                logger.warning(f"⚠️  No se pudo reparar {tabla}.{col_name}: {e}")

    # Tabla proy_consultas (local + Turso)
    try:
        _apply_ddl_idempotent(conn, """
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
    
    # ============================================================
    # Tablas v18 - modelo relacional (BD como activo estratégico)
    # ============================================================
    tablas_v18 = [
        ("mp_proveedores", """
            CREATE TABLE IF NOT EXISTS mp_proveedores (
                rut TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                n_adjudicaciones INTEGER DEFAULT 0,
                monto_total_adjudicado INTEGER DEFAULT 0,
                primera_adjudicacion TEXT,
                ultima_adjudicacion TEXT,
                regiones_operacion TEXT,
                categorias_aidu_principales TEXT,
                fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """),
        ("mp_organismos", """
            CREATE TABLE IF NOT EXISTS mp_organismos (
                codigo TEXT PRIMARY KEY,
                nombre TEXT NOT NULL,
                region TEXT,
                comuna TEXT,
                n_licitaciones INTEGER DEFAULT 0,
                monto_total_comprado INTEGER DEFAULT 0,
                ticket_promedio INTEGER DEFAULT 0,
                n_proveedores_distintos INTEGER DEFAULT 0,
                primera_licitacion TEXT,
                ultima_licitacion TEXT,
                proveedor_favorito_rut TEXT,
                proveedor_favorito_n_veces INTEGER DEFAULT 0,
                fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """),
        ("mp_licitaciones_items", """
            CREATE TABLE IF NOT EXISTS mp_licitaciones_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_externo TEXT NOT NULL,
                correlativo INTEGER,
                codigo_unspsc TEXT,
                codigo_categoria TEXT,
                categoria_nombre TEXT,
                nombre_producto TEXT NOT NULL,
                descripcion TEXT,
                unidad_medida TEXT,
                cantidad REAL,
                fecha_extraccion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """),
        ("mp_adjudicaciones", """
            CREATE TABLE IF NOT EXISTS mp_adjudicaciones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_externo TEXT NOT NULL,
                item_correlativo INTEGER,
                rut_proveedor TEXT NOT NULL,
                nombre_proveedor TEXT,
                cantidad_adjudicada REAL,
                monto_unitario INTEGER,
                monto_linea INTEGER,
                fecha_extraccion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """),
        ("mp_fechas_clave", """
            CREATE TABLE IF NOT EXISTS mp_fechas_clave (
                codigo_externo TEXT PRIMARY KEY,
                fecha_creacion TEXT,
                fecha_publicacion TEXT,
                fecha_cierre TEXT,
                fecha_inicio_foro TEXT,
                fecha_final_foro TEXT,
                fecha_pub_respuestas TEXT,
                fecha_acto_apertura_tecnica TEXT,
                fecha_acto_apertura_economica TEXT,
                fecha_estimada_adjudicacion TEXT,
                fecha_adjudicacion TEXT,
                fecha_visita_terreno TEXT,
                fecha_entrega_antecedentes TEXT,
                fecha_estimada_firma TEXT,
                fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """),
        ("mp_historial_cambios", """
            CREATE TABLE IF NOT EXISTS mp_historial_cambios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                codigo_externo TEXT NOT NULL,
                fecha_cambio TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
                campo TEXT NOT NULL,
                valor_anterior TEXT,
                valor_nuevo TEXT,
                hash_anterior TEXT,
                hash_nuevo TEXT,
                fuente_cambio TEXT
            )
        """),
    ]
    
    for nombre_tabla, sql_create in tablas_v18:
        try:
            _apply_ddl_idempotent(conn, sql_create)
        except Exception as e:
            logger.warning(f"⚠️  No se pudo crear {nombre_tabla}: {e}")

    # Índices v18 (local + Turso)
    indices_v18 = [
        "CREATE INDEX IF NOT EXISTS idx_proveedores_nombre ON mp_proveedores(nombre)",
        "CREATE INDEX IF NOT EXISTS idx_proveedores_monto ON mp_proveedores(monto_total_adjudicado DESC)",
        "CREATE INDEX IF NOT EXISTS idx_organismos_nombre ON mp_organismos(nombre)",
        "CREATE INDEX IF NOT EXISTS idx_organismos_region ON mp_organismos(region)",
        "CREATE INDEX IF NOT EXISTS idx_items_codigo ON mp_licitaciones_items(codigo_externo)",
        "CREATE INDEX IF NOT EXISTS idx_items_unspsc ON mp_licitaciones_items(codigo_unspsc)",
        "CREATE INDEX IF NOT EXISTS idx_adj_codigo ON mp_adjudicaciones(codigo_externo)",
        "CREATE INDEX IF NOT EXISTS idx_adj_proveedor ON mp_adjudicaciones(rut_proveedor)",
        "CREATE INDEX IF NOT EXISTS idx_hist_codigo ON mp_historial_cambios(codigo_externo)",
        "CREATE INDEX IF NOT EXISTS idx_hist_fecha ON mp_historial_cambios(fecha_cambio DESC)",
    ]
    for sql_idx in indices_v18:
        try:
            _apply_ddl_idempotent(conn, sql_idx)
        except Exception:
            pass
    
    # ============================================================
    # Tablas v18 sprint 10 - homologacion AIDU
    # ============================================================
    tablas_homologacion = [
        ("aidu_homologacion_categoria", """
            CREATE TABLE IF NOT EXISTS aidu_homologacion_categoria (
                cod_servicio_aidu TEXT PRIMARY KEY,
                nombre_servicio TEXT NOT NULL,
                linea TEXT,
                hh_tipicas INTEGER DEFAULT 80,
                plazo_dias_tipico INTEGER DEFAULT 30,
                entregables_tipicos TEXT,
                aplica_m2 INTEGER DEFAULT 0,
                m2_referencia INTEGER DEFAULT 0,
                notas TEXT,
                fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """),
        ("aidu_indicadores_extraidos", """
            CREATE TABLE IF NOT EXISTS aidu_indicadores_extraidos (
                codigo_externo TEXT PRIMARY KEY,
                plazo_dias INTEGER,
                plazo_fuente TEXT,
                metros_cuadrados INTEGER,
                m2_fuente TEXT,
                n_entregables INTEGER,
                entregables_lista TEXT,
                entregables_fuente TEXT,
                hh_estimadas_aidu INTEGER,
                hh_fuente TEXT,
                fecha_extraccion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """),
    ]
    for nombre_tabla, sql_create in tablas_homologacion:
        try:
            _apply_ddl_idempotent(conn, sql_create)
        except Exception as e:
            logger.warning(f"⚠️  No se pudo crear {nombre_tabla}: {e}")
    
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
