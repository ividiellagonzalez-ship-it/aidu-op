"""
AIDU Op · Validación de integridad del schema (S12.1, ajustado en S12.1.5)
==========================================================================
Distinto de `app/core/salud_bd.py`: este módulo verifica EXISTENCIA de las
tablas core (integridad estructural del schema), no calidad/cobertura/frescura
de los datos. Es el chequeo que conviene correr al primer render para
distinguir "BD vacía pero sana" de "BD corrupta / migración no aplicada".

S12.1.5: cuando hay credenciales Turso, validate_db() valida directamente
contra la BD remota Turso (vía HTTP /v2/pipeline), no contra la réplica
local en /tmp. Esto detecta el caso en que el schema existe en /tmp pero
no en Turso (causa raíz del bug que motivó este sprint).

Uso típico:

    from app.db.health_check import validate_db
    health = validate_db()
    if health["status"] == "critical":
        st.error(f"BD corrupta: faltan {health['criticas_falta']}")
        st.stop()
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from app.db.migrator import (
    get_connection,
    run_migrations,
    _read_turso_credentials,
    _query_on_turso,
)

logger = logging.getLogger(__name__)


# Tablas críticas: la app no funciona sin estas. Coinciden con lo que
# crean las migraciones 001-007 y consume el resto del codebase.
TABLAS_CRITICAS: Tuple[str, ...] = (
    "_migrations",
    "aidu_parametros",
    "aidu_proyectos",
    "aidu_servicios_keywords",
    "mp_categorizacion_aidu",
    "mp_licitaciones_adj",
    "mp_licitaciones_vigentes",
)

# Tablas v18 / homologación: features avanzadas (inteligencia de mercado,
# homologación AIDU, historial de cambios) las requieren. Si faltan se
# considera schema "degradado" pero no "crítico".
TABLAS_V18: Tuple[str, ...] = (
    "mp_proveedores",
    "mp_organismos",
    "mp_licitaciones_items",
    "mp_adjudicaciones",
    "mp_fechas_clave",
    "mp_historial_cambios",
    "aidu_homologacion_categoria",
    "aidu_indicadores_extraidos",
)


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _table_count(conn, name: str) -> int:
    try:
        cur = conn.execute(f'SELECT COUNT(*) FROM "{name}"')
        n = cur.fetchone()[0]
        return int(n) if n is not None else 0
    except Exception:
        return -1


def _scan_local(conn, tables: Tuple[str, ...]) -> Tuple[List[str], List[str], Dict[str, int]]:
    presentes: List[str] = []
    faltantes: List[str] = []
    conteos: Dict[str, int] = {}
    for t in tables:
        if _table_exists(conn, t):
            presentes.append(t)
            conteos[t] = _table_count(conn, t)
        else:
            faltantes.append(t)
    return presentes, faltantes, conteos


def _scan_turso(tables: Tuple[str, ...]) -> Tuple[List[str], List[str], Dict[str, int]]:
    """
    Lista las tablas existentes en Turso vía HTTP en una sola query, luego
    cuenta filas para las presentes. Distinto de _scan_local porque la fuente
    de verdad declarada para producción es Turso, no la réplica.
    """
    presentes: List[str] = []
    faltantes: List[str] = []
    conteos: Dict[str, int] = {}
    rows = _query_on_turso("SELECT name FROM sqlite_master WHERE type='table'")
    existentes = {row[0] for row in rows}
    for t in tables:
        if t in existentes:
            presentes.append(t)
            try:
                count_rows = _query_on_turso(f'SELECT COUNT(*) FROM "{t}"')
                conteos[t] = int(count_rows[0][0]) if count_rows else 0
            except Exception:
                conteos[t] = -1
        else:
            faltantes.append(t)
    return presentes, faltantes, conteos


def _scan(tables: Tuple[str, ...], use_turso: bool) -> Tuple[List[str], List[str], Dict[str, int]]:
    """Despacha al backend correcto según haya credenciales Turso."""
    if use_turso:
        return _scan_turso(tables)
    conn = get_connection()
    try:
        return _scan_local(conn, tables)
    finally:
        conn.close()


def validate_db() -> Dict:
    """
    Valida que el schema esté completo. Si hay credenciales Turso, valida
    contra la BD remota (no contra la réplica local). Si faltan tablas
    críticas, intenta correr `run_migrations()` una sola vez antes de
    declarar fallo crítico.

    Devuelve un dict con:
        status:           'ok' | 'degraded' | 'critical'
        conexion_tipo:    'turso' | 'sqlite_local'
        criticas_ok:      list[str] — tablas críticas presentes
        criticas_falta:   list[str] — tablas críticas faltantes (post-repair)
        v18_ok:           list[str] — tablas avanzadas presentes
        v18_falta:        list[str] — tablas avanzadas faltantes (no bloquean)
        conteos:          dict[str, int] — count por tabla presente (-1 = error)
        intento_repair:   bool — si se ejecutó run_migrations() durante el chequeo
        errores:          list[str] — errores capturados durante el scan
    """
    errores: List[str] = []
    intento_repair = False
    use_turso = _read_turso_credentials() is not None
    conexion_tipo = "turso" if use_turso else "sqlite_local"

    # 1) Scan inicial
    try:
        criticas_ok, criticas_falta, conteos = _scan(TABLAS_CRITICAS, use_turso)
    except Exception as e:
        errores.append(f"Scan inicial: {e}")
        criticas_ok, criticas_falta, conteos = [], list(TABLAS_CRITICAS), {}

    # 2) Auto-repair: si faltan críticas, correr migraciones (idempotente) y re-escanear
    if criticas_falta:
        intento_repair = True
        try:
            run_migrations()
        except Exception as e:
            errores.append(f"run_migrations falló: {e}")
        try:
            criticas_ok, criticas_falta, conteos = _scan(TABLAS_CRITICAS, use_turso)
        except Exception as e:
            errores.append(f"Scan post-repair: {e}")

    # 3) Scan v18 (informativo, no bloquea status)
    try:
        v18_ok, v18_falta, v18_conteos = _scan(TABLAS_V18, use_turso)
        conteos.update(v18_conteos)
    except Exception as e:
        errores.append(f"Scan v18: {e}")
        v18_ok, v18_falta = [], list(TABLAS_V18)

    if criticas_falta:
        status = "critical"
    elif v18_falta:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "conexion_tipo": conexion_tipo,
        "criticas_ok": criticas_ok,
        "criticas_falta": criticas_falta,
        "v18_ok": v18_ok,
        "v18_falta": v18_falta,
        "conteos": conteos,
        "intento_repair": intento_repair,
        "errores": errores,
    }
