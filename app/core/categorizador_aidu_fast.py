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
#
# S13.4.2: ampliado a 6 lineas + Otros. Las 2 nuevas (Salud y Materiales
# de Construccion) entraron tras el diagnostico de calidad del Lote 1
# que mostro 270 items en 'Otros' que son insumos medicos no clasificados.

LINEAS_AIDU_FAST = [
    "Ferreteria",
    "Aseo",
    "Oficina",
    "Equipamiento",
    "Salud",
    "Materiales de Construccion",
]
LINEA_FALLBACK = "Otros"

# Lista canonica de TODAS las lineas que pueden aparecer en
# inteligencia_precios.linea_aidu (incluye el fallback Otros). El modulo
# de UI debe importar esta constante en lugar de mantener una copia
# hardcoded propia (S13.4.2 D4: unificar las dos listas duplicadas).
LINEAS_AIDU_FAST_CON_OTROS = LINEAS_AIDU_FAST + [LINEA_FALLBACK]

# Orden de prioridad descendente para el matching (S13.4.2 D3).
# La primera linea cuyo set de keywords (incluyentes) matchee Y cuyas
# excluyentes NO matcheen es la ganadora. Mas especifica primero.
#
# Racional del orden:
#   1. Salud: insumos medicos (cateter, sonda, jeringa) son lo mas
#      especifico semanticamente.
#   2. Materiales de Construccion: cemento/fierro/arido en contexto de
#      obra; mas especifico que ferreteria general.
#   3. Aseo: jabon/cloro/detergente; no se solapa con Salud salvo
#      casos como alcohol gel (manejados via excluyentes).
#   4. Oficina: papeleria/toner.
#   5. Ferreteria: herramientas y repuestos; mas general que Construccion.
#   6. Equipamiento: mobiliario, electrodomesticos; ultimo porque es
#      el mas amplio y captura cualquier item institucional sin pistas.
PRIORIDAD_LINEAS = [
    "Salud",
    "Materiales de Construccion",
    "Aseo",
    "Oficina",
    "Ferreteria",
    "Equipamiento",
]

# Mapeo de cod_servicio (PK en aidu_servicios_keywords) -> linea_aidu
# legible. S13.4.2: ampliado a 6 lineas. Coherente con mig 011.
COD_SERVICIO_A_LINEA = {
    "FAST-FERRETERIA": "Ferreteria",
    "FAST-ASEO": "Aseo",
    "FAST-OFICINA": "Oficina",
    "FAST-EQUIPAMIENTO": "Equipamiento",
    "FAST-SALUD": "Salud",
    "FAST-CONSTRUCCION": "Materiales de Construccion",
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
#
# S13.4.2: el tipo `KeywordsCatalog` ahora mapea linea -> (incluyentes,
# excluyentes). Las excluyentes vienen de la columna `keywords_excluyentes`
# (existe desde mig 001 pero no se leia hasta S13.4.2). Una linea NO
# matchea si alguna de sus excluyentes esta en la descripcion, aunque
# alguna incluyente si matchee.
#
# Las claves del dict son los nombres legibles (Ferreteria, Aseo, etc).

# Estructura por linea: tuple (incluyentes, excluyentes).
KeywordsLinea = Tuple[List[str], List[str]]
KeywordsCatalog = Dict[str, KeywordsLinea]

_CACHED_CATALOG: Optional[KeywordsCatalog] = None


def _split_keywords(raw: str) -> List[str]:
    """Parsea la columna `keywords` de aidu_servicios_keywords (CSV inline).
    Aplica normalizacion canonica a cada keyword."""
    if not raw:
        return []
    return [normalizar_texto(k) for k in raw.split(",") if k.strip()]


def _empty_catalog() -> KeywordsCatalog:
    return {linea: ([], []) for linea in LINEAS_AIDU_FAST}


def cargar_catalogo_desde_conn(conn) -> KeywordsCatalog:
    """Carga {linea: (incluyentes, excluyentes)} desde una conexion
    SQLite/Turso-like. `conn` debe soportar `execute(sql).fetchall()`.

    S13.4.2: lee tanto `keywords` como `keywords_excluyentes`. Si la
    columna `keywords_excluyentes` no existe (esquema viejo), degrada a
    excluyentes=[] sin romper.
    """
    catalog = _empty_catalog()
    sql_full = (
        "SELECT cod_servicio, keywords, keywords_excluyentes "
        "FROM aidu_servicios_keywords WHERE tipo = 'aidu_fast'"
    )
    sql_fallback = (
        "SELECT cod_servicio, keywords FROM aidu_servicios_keywords "
        "WHERE tipo = 'aidu_fast'"
    )
    rows = None
    try:
        cur = conn.execute(sql_full)
        rows = cur.fetchall()
        has_excl_col = True
    except Exception as e1:
        # La columna no existe (mig 001 muy vieja, antes del schema definitivo)
        # o el SELECT fallo por otra causa. Probamos sin excluyentes.
        try:
            cur = conn.execute(sql_fallback)
            rows = cur.fetchall()
            has_excl_col = False
            logger.warning(
                "cargar_catalogo_desde_conn: keywords_excluyentes no disponible (%s); "
                "uso solo keywords incluyentes.", e1
            )
        except Exception as e2:
            logger.warning(
                "cargar_catalogo_desde_conn: SELECT fallo (%s). "
                "Catalogo AIDU Fast vacio - migracion 009/011 puede no estar aplicada.",
                e2,
            )
            return catalog

    for row in rows or []:
        cod_servicio = row[0] if not hasattr(row, "keys") else row["cod_servicio"]
        keywords_raw = row[1] if not hasattr(row, "keys") else row["keywords"]
        excl_raw = ""
        if has_excl_col:
            excl_raw = (
                row[2] if not hasattr(row, "keys") else row["keywords_excluyentes"]
            ) or ""
        linea = COD_SERVICIO_A_LINEA.get(cod_servicio)
        if not linea:
            logger.warning(
                "cod_servicio %r tipo='aidu_fast' no esta en COD_SERVICIO_A_LINEA; ignorando.",
                cod_servicio,
            )
            continue
        catalog[linea] = (_split_keywords(keywords_raw), _split_keywords(excl_raw))
    return catalog


def cargar_catalogo_desde_csv(csv_path: Path) -> KeywordsCatalog:
    """Fallback: carga el catalogo desde config/keywords_aidu_fast.csv.

    S13.4.2: lee la nueva columna `excluyente` (0/1 flag). Si la columna
    no existe (CSV viejo), todas las keywords se consideran incluyentes.

    Util en contextos donde no hay conexion SQL (tests unitarios puros,
    o carga ad-hoc fuera del pipeline). Lee solo filas con activo=1.
    """
    catalog = _empty_catalog()
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
        "salud": "Salud",
        "materiales de construccion": "Materiales de Construccion",
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
            if not kw:
                continue
            is_excl = row.get("excluyente", "0").strip() in ("1", "true", "True")
            incl, excl = catalog[linea]
            (excl if is_excl else incl).append(kw)
    return catalog


def set_catalogo(catalog: KeywordsCatalog) -> None:
    """Inyecta un catalogo explicito (para tests). Pisa el cache.

    S13.4.2: acepta tanto la forma nueva
    `{linea: (incluyentes, excluyentes)}` como la vieja
    `{linea: [keywords]}` (backward-compat para tests preexistentes).
    Normaliza internamente al shape nuevo.
    """
    global _CACHED_CATALOG
    normalized: KeywordsCatalog = {}
    for linea, kws in catalog.items():
        if (
            isinstance(kws, tuple)
            and len(kws) == 2
            and isinstance(kws[0], list)
            and isinstance(kws[1], list)
        ):
            normalized[linea] = (list(kws[0]), list(kws[1]))
        elif isinstance(kws, list):
            # Forma vieja: lista plana de keywords incluyentes, sin excluyentes
            normalized[linea] = (list(kws), [])
        else:
            normalized[linea] = ([], [])
    _CACHED_CATALOG = normalized


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

    Algoritmo (S13.4.2 D3 - prioridad fija):
      1. Normaliza la descripcion (lower + strip accents + apostrofe-fix).
      2. Recorre las lineas en orden PRIORIDAD_LINEAS (Salud > Construccion >
         Aseo > Oficina > Ferreteria > Equipamiento).
      3. Para la linea actual: si alguna keyword EXCLUYENTE aparece en el
         texto, descarta esta linea (ej. 'cemento dental' descarta
         Construccion porque 'cemento dental' es excluyente).
      4. Si la linea no quedo descartada y alguna keyword INCLUYENTE aparece
         en el texto, esta linea gana. Devuelve la lista de incluyentes
         que matchearon.
      5. Si ninguna linea gana -> 'Otros' + [].

    Cambio respecto a S13: antes ganaba "la linea con mas keywords
    matcheadas, empate alfabetico". Ahora gana "la primera linea en orden
    de prioridad que matchee y no quede excluida".
    """
    if catalog is None:
        catalog = get_catalogo(conn=conn)
    texto = normalizar_texto(descripcion)
    if not texto:
        return LINEA_FALLBACK, []

    for linea in PRIORIDAD_LINEAS:
        kws_linea = catalog.get(linea)
        if not kws_linea:
            continue
        incluyentes, excluyentes = kws_linea
        # Excluyente match: descarta esta linea aunque incluyente matchee.
        if any(e and e in texto for e in excluyentes):
            continue
        matched = [kw for kw in incluyentes if kw and kw in texto]
        if matched:
            return linea, matched

    return LINEA_FALLBACK, []


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

    # S13.4.2: el catalog ahora mapea linea -> (incluyentes, excluyentes).
    # Para "has_producto" solo nos interesan las incluyentes (.0 del tuple);
    # las excluyentes no son evidencia de producto.
    has_producto = False
    for linea_keywords in catalog.values():
        # Backward-compat con catalogos viejos: si el valor es lista plana,
        # tratarlo como incluyentes. Si es tuple, tomar .0.
        if isinstance(linea_keywords, tuple) and len(linea_keywords) == 2:
            incluyentes = linea_keywords[0]
        else:
            incluyentes = linea_keywords
        if any(kw and kw in texto for kw in incluyentes):
            has_producto = True
            break

    if has_servicio and has_producto:
        return "hibrido"
    if has_servicio:
        return "servicio"
    return "producto"
