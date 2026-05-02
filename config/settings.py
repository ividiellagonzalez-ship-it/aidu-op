"""
AIDU Op · Configuración central
================================
Define paths, parámetros del sistema y configuración de API.

REGLA CRÍTICA: este archivo NO contiene secretos.
Las claves API se leen desde ~/AIDU_Op/config/secrets.env
"""
from pathlib import Path
import os
from datetime import datetime

# ============================================================
# PATHS - Separación estricta código vs datos
# ============================================================
# El código puede actualizarse libremente, pero los datos
# viven fuera del directorio de código (en home del usuario).
# Esto garantiza que un `git pull` o reemplazo de la app
# nunca afecte la base de datos.

HOME_DIR = Path.home()

# Detectar si corremos en Streamlit Community Cloud
# En cloud, $HOME es efímero — usamos un dir persistente
IS_STREAMLIT_CLOUD = (
    os.path.exists("/mount/src") or
    os.environ.get("STREAMLIT_RUNTIME_MODE") == "cloud" or
    os.environ.get("HOSTNAME", "").startswith("streamlit-")
)

if IS_STREAMLIT_CLOUD:
    AIDU_HOME = Path("/tmp/AIDU_Op")
else:
    AIDU_HOME = HOME_DIR / "AIDU_Op"

# Directorio de datos (INTOCABLE por updates de app)
DATA_DIR = AIDU_HOME / "data"
DB_DIR = DATA_DIR / "db"
RAW_DIR = DATA_DIR / "raw"          # XML/JSON crudos del API
BACKUP_DIR = DATA_DIR / "backups"   # Snapshots automáticos
LOGS_DIR = DATA_DIR / "logs"

# Directorio de configuración (incluye secrets.env)
CONFIG_DIR = AIDU_HOME / "config"

# Archivos clave
DB_PATH = DB_DIR / "aidu_op.db"
SECRETS_FILE = CONFIG_DIR / "secrets.env"
LOG_FILE = LOGS_DIR / f"aidu_{datetime.now():%Y%m}.log"
VERSION_FILE = AIDU_HOME / "VERSION_INSTALADA"  # Versión de la BD/app instalada

# Crear estructura si no existe (idempotente, no destruye nada)
for d in [AIDU_HOME, DATA_DIR, DB_DIR, RAW_DIR, BACKUP_DIR, LOGS_DIR, CONFIG_DIR]:
    d.mkdir(parents=True, exist_ok=True)


# Cold start en Streamlit Cloud: restaurar BD persistente desde el repo
# La BD `data_semilla/aidu_op.db` se mantiene actualizada por el cron diario
# de GitHub Actions (descarga_mp_diaria.yml) que hace commit-back con las
# licitaciones nuevas. En cada cold start, restauramos desde ahí.
if IS_STREAMLIT_CLOUD and not DB_PATH.exists():
    import shutil
    REPO_ROOT = Path(__file__).parent.parent
    
    # Prioridad 1: BD persistente actualizada por el cron
    bd_persistente = REPO_ROOT / "data_semilla" / "aidu_op.db"
    # Prioridad 2: BD demo de respaldo
    bd_demo = REPO_ROOT / "data_semilla" / "aidu_op_demo.db"
    
    if bd_persistente.exists():
        shutil.copy2(bd_persistente, DB_PATH)
    elif bd_demo.exists():
        shutil.copy2(bd_demo, DB_PATH)


# ============================================================
# API MERCADO PÚBLICO
# ============================================================
def _load_env():
    """Carga variables desde:
    1. st.secrets si está corriendo en Streamlit Cloud (PRIORIDAD MÁXIMA)
    2. secrets.env local (formato KEY=VALUE) si es instalación local
    """
    # Intento 1: Streamlit Cloud secrets (FUERZA sobrescribir)
    try:
        import streamlit as st
        if hasattr(st, "secrets"):
            for k in ["MP_TICKET", "ANTHROPIC_API_KEY"]:
                try:
                    val = st.secrets.get(k)
                    if val:
                        # Asignación directa (sobrescribe siempre)
                        os.environ[k] = str(val).strip()
                except Exception:
                    pass
    except ImportError:
        pass
    except Exception:
        pass  # st.secrets falla cuando no estamos en contexto Streamlit
    
    # Intento 2: archivo local (modo desarrollo, sin sobrescribir cloud)
    if not SECRETS_FILE.exists():
        return
    for line in SECRETS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        # Limpiar comillas si las hay
        val = v.strip().strip('"').strip("'")
        os.environ.setdefault(k.strip(), val)

_load_env()


# ============================================================
# Funciones lazy para leer secretos (Streamlit Cloud safe)
# st.secrets puede no estar disponible al momento del primer import
# ============================================================
def get_mp_ticket() -> str:
    """Lee MP_TICKET fresco; re-intenta cargar si está vacío."""
    val = os.environ.get("MP_TICKET", "").strip()
    if not val:
        _load_env()
        val = os.environ.get("MP_TICKET", "").strip()
    return val


def get_anthropic_api_key() -> str:
    """Lee ANTHROPIC_API_KEY fresco; re-intenta cargar si está vacío."""
    val = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not val:
        _load_env()
        val = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return val


MP_API_BASE = "https://api.mercadopublico.cl/servicios/v1/publico"
MP_TICKET = os.getenv("MP_TICKET", "")  # legacy; preferir get_mp_ticket()
MP_TICKET_DEMO = "F8537A18-6766-4DEF-9E59-426B4FEE2844"  # Fallback público

# Rate limiting: conservador para no quemar el ticket
MP_REQUESTS_PER_MINUTE = 30
MP_REQUEST_TIMEOUT = 30  # segundos
MP_MAX_RETRIES = 3
MP_RETRY_BACKOFF = 5     # segundos entre retries

# Backfill
BACKFILL_MONTHS = 24  # legacy, no usado por defecto
BACKFILL_DIAS_DEFAULT = 14  # MVP: solo 2 semanas para empezar (~30 min)
INCREMENTAL_DAYS_LOOKBACK = 7  # Cada actualización diaria revisa últimos 7d


# ============================================================
# CLAUDE API
# ============================================================
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-5"  # Modelo balance costo/calidad


# ============================================================
# AIDU OP - Parámetros del negocio
# ============================================================
UF_VALOR_DEFAULT = 39000  # Se actualiza desde mindicador.cl en runtime
TARIFA_HORA_UF = 2
OVERHEAD_PCT = 0.18

REGION_BASE = "O'Higgins"
COSTO_VIAJE = {
    "O'Higgins": 100_000,
    "Metropolitana": 250_000,
    "Maule": 250_000,
    "Valparaíso": 350_000,
    "Otros": 600_000,
}


# ============================================================
# Helpers
# ============================================================
def get_version():
    """Lee versión actual del archivo VERSION del código"""
    here = Path(__file__).parent.parent
    vfile = here / "VERSION"
    if vfile.exists():
        return vfile.read_text().strip()
    return "0.0.0"


def get_installed_version():
    """Lee versión instalada en datos del usuario"""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text().strip()
    return None


def write_installed_version(version: str):
    """Marca la versión actualmente instalada"""
    VERSION_FILE.write_text(version)
