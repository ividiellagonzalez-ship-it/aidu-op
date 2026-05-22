"""
AIDU Op · Categorizador AIDU Fast (S13)
========================================
Asigna a cada item adjudicado dos etiquetas independientes:

1. linea_aidu   ∈ {'Ferreteria', 'Aseo', 'Oficina', 'Equipamiento', 'Otros'}
2. tipo_objeto  ∈ {'producto', 'servicio', 'hibrido'}

Diseño y decisiones (sprint S13):
- D1: convivencia con el catalogo AIDU Op existente (servicios CE/GP). Este
  modulo opera SOLO sobre tipo='aidu_fast' en aidu_servicios_keywords.
  NO comparte funciones con app/core/ingesta._calcular_match_aidu.
- D2: keywords viven en la tabla SQL (cod_servicio LIKE 'FAST-%' AND
  tipo='aidu_fast'). El CSV `config/keywords_aidu_fast.csv` es el source
  of truth declarativo, pero el modulo lee de la tabla en runtime.
- D7: tipo_objeto se calcula con heuristica del spec sec 3.3, NO se lee
  de mp_licitaciones_items.tipo_origen.

Algoritmo (spec sec 3.2):
- Match por substring case-insensitive sobre la descripcion normalizada.
- Si match con keywords de UNA linea, asigna esa linea.
- Si match con keywords de MULTIPLES lineas, prevalece la linea con mas
  keywords matcheadas. Empate -> primer match alfabetico (deterministico).
- Si NO hay match: 'Otros'.

Normalizacion (atiende hallazgos S13.0):
- Lower-case.
- Apostrofes Unicode no estandar: U+00B4 / U+2019 / U+2018 / U+0060 -> ASCII U+0027.
- Acentos: NFD + drop combining marks (para que "cañeria" matche "caneria" y
  viceversa). Las keywords en BD ya estan unaccented; las descripciones del
  API vienen con acentos.

Performance: el catalogo se cachea en memoria a la primera llamada.
La invalidacion explicita (`reset_cache()`) existe para tests.
"""
from __future__ import annotations

import csv
import logging
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTES PUBLICAS
# ============================================================

LINEAS_AIDU_FAST = ["Ferreteria", "Aseo", "Oficina", "Equipamiento"]
LINEA_FALLBACK = "Otros"

# Mapeo de cod_servicio (PK en aidu_servicios_keywords) -> linea_aidu
# legible. Coherente con seed de la migracion 009.
COD_SERVICIO_A_LINEA = {
    "FAST-FERRETERIA": "Ferreteria",
    "FAST-ASEO": "Aseo",
    "FAST-OFICINA": "Oficina",
    "FAST-EQUIPAMIENTO": "Equipamiento",
}

# Keywords de servicio (spec sec 3.3). Substring match insensible.
# La heuristica:
#   linea match + servicio match     -> tipo_objeto = 'hibrido'
#   solo servicio match              -> tipo_objeto = 'servicio'
#   solo linea match (sin servicio)  -> tipo_objeto = 'producto'
#   ningun match                     -> tipo_objeto = 'producto' (default)
KEYWORDS_SERVICIO = (
    "servicio",
    "consultoria",
    "consultor",
    "mantencion",
    "mantenimiento",
    "instalacion",
    "capacitacion",
    "asesoria",
    "arriendo",
    "alquiler",
    "soporte",
    "reparacion",
)


# ============================================================
# NORMALIZACION
# ============================================================

_APOSTROFE_MAP = str.maketrans({
    "´": "'",  # ACUTE ACCENT (hallazgo S13.0)
    "’": "'",  # RIGHT SINGLE QUOTATION MARK
    "‘": "'",  # LEFT SINGLE QUOTATION MARK
    "`": "'",  # GRAVE ACCENT
})


def _strip_accents(s: str) -> str:
    """NFD + descarta combining marks. 'cañería' -> 'caneria'."""
    if not s:
        return ""
    nfd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfd if unicodedata.category(c) != "Mn")


def normalizar_texto(s: Optional[str]) -> str:
    """Pipeline canonico para comparacion de keywords."""
    if not s:
        return ""
    s = s.translate(_APOSTROFE_MAP)
    s = _strip_accents(s)
    return s.lower().strip()


def normalizar_region(s: Optional[str]) -> str:
    """Misma normalizacion que `normalizar_texto`, expuesta con nombre
    explicito para callers que filtran por region (ingestor, tests)."""
    return normalizar_texto(s)


def es_ohiggins(region_raw: Optional[str]) -> bool:
    """Confirma si la region matchea O'Higgins (todas las variantes)."""
    n = normalizar_region(region_raw)
    return ("o'higgins" in n) or ("libertador" in n)


# ============================================================
# CARGA DEL CATALOGO DE KEYWORDS
# ============================================================
# El catalogo se carga desde la tabla SQL al primer uso, y se cachea.
# `KeywordsCatalog` es un diccionario {linea_aidu: [keywords_normalizadas]}.
# Las claves del dict son los nombres legibles (Ferreteria, Aseo, etc).

KeywordsCatalog = Dict[str, List[str]]

_CACHED_CATALOG: Optional[KeywordsCatalog] = None


def _split_keywords(raw: str) -> List[str]:
    """Parsea la columna `keywords` de aidu_servicios_keywords (CSV inline).
    Aplica normalizacion canonica a cada keyword."""
    if not raw:
        return []
    return [normalizar_texto(k) for k in raw.split(",") if k.strip()]


def cargar_catalogo_desde_conn(conn) -> KeywordsCatalog:
    """Carga {linea: [keywords]} desde una conexion SQLite/Turso-like.
    `conn` debe soportar `execute(sql).fetchall()`.

    Lee solo filas tipo='aidu_fast'. Si la columna `tipo` no existe (mig
    009 no aplicada todavia), retorna catalogo vacio y loggea WARNING
    explicito para que el ingestor pueda continuar sin crash.
    """
    catalog: KeywordsCatalog = {linea: [] for linea in LINEAS_AIDU_FAST}
    try:
        cur = conn.execute(
            "SELECT cod_servicio, keywords FROM aidu_servicios_keywords "
            "WHERE tipo = 'aidu_fast'"
        )
        rows = cur.fetchall()
    except Exception as e:
        logger.warning(
            "cargar_catalogo_desde_conn: SELECT fallo (%s). "
            "Catalogo AIDU Fast vacio - migracion 009 puede no estar aplicada.",
            e,
        )
        return catalog

    for row in rows:
        cod_servicio = row[0] if not hasattr(row, "keys") else row["cod_servicio"]
        keywords_raw = row[1] if not hasattr(row, "keys") else row["keywords"]
        linea = COD_SERVICIO_A_LINEA.get(cod_servicio)
        if not linea:
            logger.warning(
                "cod_servicio %r tipo='aidu_fast' no esta en COD_SERVICIO_A_LINEA; ignorando.",
                cod_servicio,
            )
            continue
        catalog[linea] = _split_keywords(keywords_raw)
    return catalog


def cargar_catalogo_desde_csv(csv_path: Path) -> KeywordsCatalog:
    """Fallback: carga el catalogo desde config/keywords_aidu_fast.csv.

    Util en contextos donde no hay conexion SQL (tests unitarios puros,
    o carga ad-hoc fuera del pipeline). Lee solo filas con activo=1.
    """
    catalog: KeywordsCatalog = {linea: [] for linea in LINEAS_AIDU_FAST}
    if not csv_path.exists():
        logger.warning("CSV de keywords no existe: %s", csv_path)
        return catalog
    # Aliases para tolerar diferencias de slug en la columna `linea` del CSV
    # (ej. 'Ferreteria y Construccion' vs 'Ferreteria').
    aliases = {
        "ferreteria": "Ferreteria",
        "ferreteria y construccion": "Ferreteria",
        "aseo": "Aseo",
        "oficina": "Oficina",
        "equipamiento": "Equipamiento",
    }
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("activo", "1").strip() not in ("1", "true", "True"):
                continue
            raw_linea = normalizar_texto(row.get("linea", ""))
            linea = aliases.get(raw_linea)
            if not linea:
                continue
            kw = normalizar_texto(row.get("keyword", ""))
            if kw:
                catalog[linea].append(kw)
    return catalog


def set_catalogo(catalog: KeywordsCatalog) -> None:
    """Inyecta un catalogo explicito (para tests). Pisa el cache."""
    global _CACHED_CATALOG
    _CACHED_CATALOG = {linea: list(kws) for linea, kws in catalog.items()}


def reset_cache() -> None:
    """Invalida el cache del catalogo (tests + recargas en runtime)."""
    global _CACHED_CATALOG
    _CACHED_CATALOG = None


def get_catalogo(conn=None, csv_path: Optional[Path] = None) -> KeywordsCatalog:
    """Devuelve el catalogo cacheado. Si no hay cache:
       - Si `conn` provista, carga de la tabla SQL.
       - Si no, carga del CSV (path por defecto: config/keywords_aidu_fast.csv).
    """
    global _CACHED_CATALOG
    if _CACHED_CATALOG is not None:
        return _CACHED_CATALOG
    if conn is not None:
        _CACHED_CATALOG = cargar_catalogo_desde_conn(conn)
    else:
        path = csv_path or _default_csv_path()
        _CACHED_CATALOG = cargar_catalogo_desde_csv(path)
    return _CACHED_CATALOG


def _default_csv_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "keywords_aidu_fast.csv"


# ============================================================
# CATEGORIZACION DIM 1: LINEA AIDU FAST
# ============================================================

def categorizar_linea(
    descripcion: str,
    catalog: Optional[KeywordsCatalog] = None,
    conn=None,
) -> Tuple[str, List[str]]:
    """Asigna linea_aidu a partir de la descripcion del item.

    Devuelve (linea, keywords_matcheadas). `keywords_matcheadas` es la
    lista de keywords (post-normalizacion) que dispararon la asignacion;
    se persiste en inteligencia_precios.keywords_matched para
    auditabilidad y mejora iterativa del diccionario.

    Algoritmo:
      1. Normaliza la descripcion (lower + strip accents + apostrofe-fix).
      2. Para cada linea, cuenta cuantas keywords aparecen como substring.
      3. La linea con MAS matches gana. Empate -> primera alfabetica.
      4. Si todas tienen 0 matches -> 'Otros' + [].
    """
    if catalog is None:
        catalog = get_catalogo(conn=conn)
    texto = normalizar_texto(descripcion)
    if not texto:
        return LINEA_FALLBACK, []

    scores: Dict[str, List[str]] = {linea: [] for linea in LINEAS_AIDU_FAST}
    for linea, keywords in catalog.items():
        for kw in keywords:
            if not kw:
                continue
            if kw in texto:
                scores[linea].append(kw)

    # Buscar la linea con mas matches
    best_linea = LINEA_FALLBACK
    best_count = 0
    for linea in sorted(scores.keys()):  # alfabetico para desempate deterministico
        count = len(scores[linea])
        if count > best_count:
            best_count = count
            best_linea = linea
    if best_count == 0:
        return LINEA_FALLBACK, []
    return best_linea, scores[best_linea]


# ============================================================
# CATEGORIZACION DIM 2: TIPO_OBJETO
# ============================================================

def categorizar_tipo_objeto(
    descripcion: str,
    catalog: Optional[KeywordsCatalog] = None,
    conn=None,
) -> str:
    """Asigna tipo_objeto: 'producto' | 'servicio' | 'hibrido'.

    Heuristica del spec sec 3.3:
      - servicio AND producto -> 'hibrido'
      - solo servicio          -> 'servicio'
      - solo producto, o ningun match -> 'producto' (default)

    Donde:
      'producto' = match con cualquier keyword del catalogo AIDU Fast.
      'servicio' = match con cualquier keyword de KEYWORDS_SERVICIO.

    El "default 'producto'" del spec captura items sin contexto claro
    como compras de bienes implicitos.
    """
    texto = normalizar_texto(descripcion)
    if not texto:
        return "producto"

    if catalog is None:
        catalog = get_catalogo(conn=conn)

    has_servicio = any(s in texto for s in KEYWORDS_SERVICIO)

    has_producto = False
    for linea_keywords in catalog.values():
        if any(kw and kw in texto for kw in linea_keywords):
            has_producto = True
            break

    if has_servicio and has_producto:
        return "hibrido"
    if has_servicio:
        return "servicio"
    return "producto"
