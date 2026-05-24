"""
AIDU Op · Ingestor Inteligencia de Precios O'Higgins (S13)
============================================================
Descarga adjudicaciones L1 + LE + CO de la Region O'Higgins,
categoriza cada item y persiste en `inteligencia_precios`.

Reconocimiento operacional (hallazgos S13.0):
- El listado basico de /licitaciones.json solo trae 4 campos
  (CodigoExterno, Nombre, CodigoEstado, FechaCierre). Para filtrar por
  region hay que pegar el detalle de cada licitacion.
- Cubrir 90 dias × ~300 licitaciones nacionales / dia = ~27,000 detalles
  a 30 req/min = ~15 horas. Inviable como filtro ingenuo.
- Solucion: filtro pre-detalle por `unit_code` (primer segmento del
  CodigoExterno). El seed `config/organismos_ohiggins.csv` (41 unidades
  de compra al cierre de S13.0) cubre el grueso del mercado regional;
  la tabla `organismos_ohiggins_auto` se llena en runtime cuando el
  cron diario descubre unidades nuevas.

DEDUPE: por unit_code, NO por nombre_organismo.
Razon: la misma comuna (ej. Lituche) tiene multiples unidades de compra
con codigos distintos (1743 y 580075) — depto adquisiciones, salud
municipal, alcaldia, etc. Cada unit_code es una fuente de compra
distinta y queremos contarlos todos por separado. Ver
docs/sprints/AIDU_Op_S13_MVP_Inteligencia_Ohiggins.md (reporte de
reconnaissance, hallazgos del CSV semilla).

AUTO-DISCOVERY (OK-3 modificado por Director):
- Para el backfill (lote 1-4): `discovery_sample_size=0`. Solo se peg an
  detalles de unit_codes en el seed. Se acepta cobertura imperfecta.
- Para el cron diario: `discovery_sample_size=25`. De los listados
  diarios se sortean N codigos NO en el seed para pegar detalle. Si
  resultan O'Higgins, se agregan a organismos_ohiggins_auto y los
  ciclos siguientes los incluyen en el filtro.

Idempotencia: INSERT OR IGNORE por UNIQUE (codigo_mp, correlativo_item)
en `inteligencia_precios`. Re-ejecutar el mismo rango no duplica filas.

Tipos en scope (S13.0 hallazgo A: CA out-of-scope hasta resolver S13.1):
  ('L1', 'LE', 'CO').
"""
from __future__ import annotations

import csv
import logging
import random
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

from app.api.mercadopublico import MercadoPublicoClient
from app.db import turso_http_client
from app.db._hrana_types import arg_for_value
from app.core.categorizador_aidu_fast import (
    categorizar_linea,
    categorizar_tipo_objeto,
    es_ohiggins,
    get_catalogo,
)

logger = logging.getLogger(__name__)

# Tipos de licitacion in scope (S13 MVP).
# CA (AGIL) queda excluida hasta resolver S13.1 (hallazgo A).
TIPOS_SCOPE = ("L1", "LE", "CO")

# Batch size para persistencia Turso /v2/pipeline.
BATCH_SIZE_PERSIST = 50

# Rate efectivo conservador del cliente para estimar wall clock; usado
# solo para presentar ETA en el log de progreso, no para sleep.
RATE_REQ_PER_MIN_EFECTIVO = 25

# S13.5: precios USD por millon de tokens para sonnet-4-5 (input/output).
# Usado solo para cost guard del modo backfill semantico. NO se usa en
# el cron diario porque ese sigue lexical.
COST_INPUT_PER_MTOK = 3.0
COST_OUTPUT_PER_MTOK = 15.0
# Promedios observados en S13.4.3 (Run #2, 687 items): 450 input + 120 output.
PROMPT_TOKENS_AVG = 450
OUTPUT_TOKENS_AVG = 120


def _estimar_costo_claude(n_calls: int) -> float:
    """Costo proyectado en USD para N llamadas a `clasificar_via_claude`."""
    if n_calls <= 0:
        return 0.0
    input_cost = (PROMPT_TOKENS_AVG * n_calls / 1_000_000.0) * COST_INPUT_PER_MTOK
    output_cost = (OUTPUT_TOKENS_AVG * n_calls / 1_000_000.0) * COST_OUTPUT_PER_MTOK
    return input_cost + output_cost


# ============================================================
# ESTADISTICAS DE CORRIDA
# ============================================================

@dataclass
class StatsCorrida:
    """Stats acumulados que devuelve el ingestor al CLI/cron."""
    fecha_desde: str = ""
    fecha_hasta: str = ""
    dias_procesados: int = 0
    n_listados_total: int = 0          # suma de listados nacionales descargados
    n_filtrados_por_unit: int = 0      # entradas que pasaron el filtro unit_code
    n_detalles_pegados: int = 0
    n_items_categorizados: int = 0     # items efectivamente persistidos en bd
    n_descartados_no_ohiggins: int = 0 # detalles cuya region no era O'Higgins
    n_descartados_tipo: int = 0        # detalles fuera de TIPOS_SCOPE
    n_descartados_sin_items: int = 0   # detalles sin items adjudicados
    n_lotes_persistidos: int = 0
    n_filas_insert_or_ignore_skipped: int = 0  # estimado por (intentos - efectivos)
    n_organismos_descubiertos: int = 0
    distribucion_por_linea: Dict[str, int] = field(default_factory=dict)
    distribucion_por_tipo: Dict[str, int] = field(default_factory=dict)
    tiempo_total_seg: float = 0.0
    # S13.5: nuevos contadores para modo backfill con idempotencia + semantico.
    n_skip_idempotente: int = 0       # codigos_mp ya presentes en BD (SKIP antes de pegar detalle)
    n_llamadas_semanticas: int = 0    # items que se clasificaron via Claude API (no fallback lexical)
    costo_claude_usd: float = 0.0     # estimacion en USD; recalculado al cierre desde n_llamadas_semanticas
    aborted_cost_guard: bool = False  # True si cost guard freno la corrida


# ============================================================
# CARGA DE UNIT_CODES VALIDOS (CSV + tabla auto)
# ============================================================

def cargar_unit_codes_csv(csv_path: Optional[Path] = None) -> Set[str]:
    """Lee config/organismos_ohiggins.csv → set de unit_codes.
    Tolera ausencia del archivo (devuelve set vacio + WARNING)."""
    path = csv_path or _default_csv_path()
    if not path.exists():
        logger.warning("CSV de organismos no existe: %s", path)
        return set()
    out: Set[str] = set()
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uc = (row.get("unit_code") or "").strip()
            if uc:
                out.add(uc)
    return out


def _default_csv_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "organismos_ohiggins.csv"


def cargar_unit_codes_auto() -> Set[str]:
    """Lee organismos_ohiggins_auto desde Turso. Tolera tabla inexistente
    (mig 009 no aplicada en local dev) devolviendo set vacio."""
    if not turso_http_client.is_configured():
        logger.info("Turso no configurado; organismos_ohiggins_auto = vacio.")
        return set()
    try:
        rows = turso_http_client.query_all(
            "SELECT unit_code FROM organismos_ohiggins_auto"
        )
    except Exception as e:
        logger.warning("organismos_ohiggins_auto SELECT fallo: %s", e)
        return set()
    return {(r[0] or "").strip() for r in rows if r and r[0]}


def cargar_unit_codes_validos(csv_path: Optional[Path] = None) -> Set[str]:
    """Union de CSV semilla + tabla auto."""
    return cargar_unit_codes_csv(csv_path) | cargar_unit_codes_auto()


# ============================================================
# S13.5: CARGA DE CODIGOS_MP YA EN BD (idempotencia de backfill)
# ============================================================

def cargar_codigos_existentes(
    fecha_desde: date,
    fecha_hasta: date,
    *,
    buffer_days: int = 30,
) -> Set[str]:
    """Trae el set de `codigo_mp` ya presentes en `inteligencia_precios`
    cuya `fecha_adjudicacion` cae en [fecha_desde - buffer, fecha_hasta + buffer].

    Usado por `ingerir_rango(usar_semantico=True, ...)` para SKIP idempotente:
    si el codigo ya esta en BD, no se vuelve a pegar a la API MP ni se
    paga la clasificacion Claude.

    El buffer +/- N dias cubre edge cases de licitaciones publicadas un
    mes y adjudicadas el mes siguiente (o viceversa). Default 30 dias
    aprobado por Director (S13.5 ajustes finos).

    Tolera Turso no configurado o tabla faltante: devuelve set vacio +
    log WARNING. Esto degrada el modo backfill a "no-idempotente" pero
    NO crashea el run (defensa en profundidad, igual que el cron diario).
    """
    if not turso_http_client.is_configured():
        logger.info("cargar_codigos_existentes: Turso no configurado; set vacio.")
        return set()
    desde = (fecha_desde - timedelta(days=buffer_days)).isoformat()
    hasta = (fecha_hasta + timedelta(days=buffer_days)).isoformat()
    try:
        rows = turso_http_client.query_all(
            "SELECT DISTINCT codigo_mp FROM inteligencia_precios "
            "WHERE fecha_adjudicacion >= ? AND fecha_adjudicacion <= ?",
            [arg_for_value(desde), arg_for_value(hasta)],
        )
    except Exception as e:
        logger.warning(
            "cargar_codigos_existentes SELECT fallo: %s. "
            "El modo backfill correra sin SKIP idempotente (puede re-pagar Claude API).",
            e,
        )
        return set()
    out = {(r[0] or "").strip() for r in rows if r and r[0]}
    logger.info(
        "cargar_codigos_existentes: %d codigos_mp ya en BD para ventana %s..%s "
        "(buffer +/-%d dias).",
        len(out), desde, hasta, buffer_days,
    )
    return out


# ============================================================
# FILTRO PRE-DETALLE POR UNIT_CODE
# ============================================================

def extraer_unit_code(codigo_externo: str) -> str:
    """1620-9-LE26 -> '1620'. Util tanto para filtro como para dedupe."""
    if not codigo_externo or not isinstance(codigo_externo, str):
        return ""
    return codigo_externo.split("-", 1)[0].strip()


def _filtrar_listado(
    listado: List[dict],
    unit_codes_validos: Set[str],
    discovery_sample_size: int,
    rng: random.Random,
) -> Tuple[List[dict], List[dict]]:
    """Particiona el listado en (matched, sampled_for_discovery).

    `matched`: entradas cuyo unit_code esta en `unit_codes_validos`.
    `sampled_for_discovery`: hasta N entradas random NO matched (auto-discovery).
    """
    matched, no_match = [], []
    for lic in listado:
        uc = extraer_unit_code(lic.get("CodigoExterno", ""))
        if uc in unit_codes_validos:
            matched.append(lic)
        else:
            no_match.append(lic)
    if discovery_sample_size > 0 and no_match:
        sample = rng.sample(no_match, min(discovery_sample_size, len(no_match)))
    else:
        sample = []
    return matched, sample


# ============================================================
# EXTRACCION DE ITEMS DESDE EL DETALLE
# ============================================================

def _entry_de_detalle(det: Optional[dict]) -> Optional[dict]:
    """API devuelve {Listado: [entry]} o entry directo. Devolver entry."""
    if not isinstance(det, dict):
        return None
    if "Listado" in det and isinstance(det["Listado"], list) and det["Listado"]:
        e = det["Listado"][0]
        return e if isinstance(e, dict) else None
    return det


def _safe_float(x) -> Optional[float]:
    try:
        if x is None or x == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _safe_int(x) -> Optional[int]:
    try:
        if x is None or x == "":
            return None
        return int(x)
    except (TypeError, ValueError):
        return None


def expandir_items(
    detalle: dict,
    *,
    fecha_adjudicacion: Optional[str] = None,
) -> List[dict]:
    """Toma el detalle de UNA licitacion y devuelve una lista de items
    normalizados listos para categorizar + persistir. NO filtra ni
    categoriza aca.

    Cada item tiene shape:
      {
        'codigo_mp', 'correlativo_item', 'fecha_adjudicacion',
        'tipo_licitacion', 'organismo_comprador', 'unit_code',
        'organismo_region', 'region_entrega', 'producto_descripcion',
        'unidad_medida', 'cantidad', 'precio_unitario', 'monto_total',
        'proveedor_nombre', 'proveedor_rut', 'n_oferentes',
      }
    """
    entry = _entry_de_detalle(detalle)
    if not entry:
        return []

    codigo_mp = entry.get("CodigoExterno") or ""
    tipo_lic = (entry.get("Tipo") or "").upper()
    comprador = entry.get("Comprador") if isinstance(entry.get("Comprador"), dict) else {}
    organismo_nombre = comprador.get("NombreOrganismo") or ""
    region = comprador.get("RegionUnidad") or ""
    unit_code = extraer_unit_code(codigo_mp)

    # Region de entrega: a veces vive en una direccion declarada separada.
    direccion_entrega = entry.get("DireccionEntrega") if isinstance(entry.get("DireccionEntrega"), dict) else {}
    region_entrega = direccion_entrega.get("RegionUnidad") or region

    # N oferentes vive en Adjudicacion (top-level) en algunos shapes.
    adj_top = entry.get("Adjudicacion") if isinstance(entry.get("Adjudicacion"), dict) else {}
    n_oferentes = _safe_int(adj_top.get("NumeroOferentes"))

    fecha_adj = fecha_adjudicacion or (
        (adj_top.get("Fecha") or entry.get("FechaAdjudicacion") or "")[:10] or None
    )

    items_obj = entry.get("Items") or {}
    items_listado = items_obj.get("Listado", []) if isinstance(items_obj, dict) else []

    out: List[dict] = []
    for it in items_listado:
        if not isinstance(it, dict):
            continue
        correlativo = _safe_int(it.get("Correlativo")) or 0
        descripcion = (
            it.get("Descripcion")
            or it.get("NombreProducto")
            or it.get("Categoria")
            or ""
        )
        unidad_medida = it.get("UnidadMedida") or ""
        cantidad = _safe_float(it.get("Cantidad"))
        adj_item = it.get("Adjudicacion") if isinstance(it.get("Adjudicacion"), dict) else None
        precio_unitario = None
        monto_total = None
        proveedor_nombre = ""
        proveedor_rut = ""
        if adj_item:
            precio_unitario = _safe_float(
                adj_item.get("MontoUnitario") or adj_item.get("montoUnitario")
            )
            cantidad_adj = _safe_float(adj_item.get("Cantidad")) or cantidad
            if precio_unitario is not None and cantidad_adj is not None:
                monto_total = precio_unitario * cantidad_adj
                cantidad = cantidad_adj  # preferimos cantidad adjudicada vs solicitada
            proveedor_nombre = adj_item.get("NombreProveedor") or ""
            proveedor_rut = adj_item.get("RutProveedor") or ""

        out.append({
            "codigo_mp": codigo_mp,
            "correlativo_item": correlativo,
            "fecha_adjudicacion": fecha_adj,
            "tipo_licitacion": tipo_lic,
            "organismo_comprador": organismo_nombre,
            "unit_code": unit_code,
            "organismo_region": region,
            "region_entrega": region_entrega,
            "producto_descripcion": descripcion,
            "unidad_medida": unidad_medida,
            "cantidad": cantidad,
            "precio_unitario": precio_unitario,
            "monto_total": monto_total,
            "proveedor_nombre": proveedor_nombre,
            "proveedor_rut": proveedor_rut,
            "n_oferentes": n_oferentes,
        })
    return out


# ============================================================
# CATEGORIZACION (envuelve el modulo categorizador)
# ============================================================

def categorizar_item(item: dict, catalog=None, *, usar_semantico: bool = False) -> dict:
    """Mutates `item` adding linea_aidu, tipo_objeto, keywords_matched.

    S13.4.3: nuevo parametro opt-in `usar_semantico`. Cuando es True
    intenta primero el clasificador semantico (Claude API) y SOLO cae al
    lexical si la API falla. Cuando es False (default), comportamiento
    historico: solo lexical. Esto permite que el cron diario y el script
    de re-clasificacion activen semantico via env var/flag, mientras los
    tests existentes siguen ejecutando lexical sin cambios.

    Campos agregados al item:
      - linea_aidu, tipo_objeto, keywords_matched (siempre)
      - es_producto_granular, confidence_score, clasificacion_metodo
        (solo cuando usar_semantico=True; el lexical los deja en None,
        0.0, 'keyword').

    Devuelve el dict (para encadenar).
    """
    descripcion = item.get("producto_descripcion") or ""
    organismo = item.get("organismo_comprador") or ""

    # Path lexical (default). Defensivo: las claves nuevas tambien se
    # setean para mantener shape consistente.
    linea, kws = categorizar_linea(descripcion, catalog=catalog)
    tipo_obj = categorizar_tipo_objeto(descripcion, catalog=catalog)
    item["linea_aidu"] = linea
    item["tipo_objeto"] = tipo_obj
    item["keywords_matched"] = ",".join(kws) if kws else ""
    item.setdefault("es_producto_granular", None)
    item.setdefault("confidence_score", 0.0)
    item.setdefault("clasificacion_metodo", "keyword")

    if not usar_semantico:
        return item

    # Path semantico: intento Claude API. Si falla, ya tenemos los
    # campos lexicales seteados arriba como fallback.
    try:
        # Import diferido: evitar pegar la API en imports de tests.
        from app.core.clasificador_semantico import clasificar_via_claude
        from app.api.claude_client import ClaudeApiUnavailableError
        try:
            resultado = clasificar_via_claude(descripcion, organismo)
        except ClaudeApiUnavailableError as e:
            logger.warning(
                "categorizar_item(usar_semantico=True): Claude API fallo "
                "para item %s: %s. Conservo clasificacion lexical.",
                item.get("codigo_mp"), e,
            )
            return item

        item["linea_aidu"] = resultado.get("linea", linea)
        item["es_producto_granular"] = resultado.get("es_producto_granular")
        item["confidence_score"] = float(resultado.get("confidence", 0.0))
        item["clasificacion_metodo"] = "semantic"
        # keywords_matched conserva el matching lexical como auditoria
        # secundaria; razon de la decision semantica va en otro lado si
        # el caller la guarda.
    except Exception as e:
        logger.warning(
            "categorizar_item(usar_semantico=True): error inesperado (%s); "
            "conservo clasificacion lexical.", e,
        )
    return item


# ============================================================
# PERSISTENCIA (Turso /v2/pipeline, batches de 50, INSERT OR IGNORE)
# ============================================================

_INSERT_INTELIGENCIA_SQL = (
    "INSERT OR IGNORE INTO inteligencia_precios "
    "(codigo_mp, correlativo_item, fecha_adjudicacion, tipo_licitacion, "
    " organismo_comprador, unit_code, organismo_region, region_entrega, "
    " producto_descripcion, unidad_medida, cantidad, precio_unitario, "
    " monto_total, proveedor_nombre, proveedor_rut, n_oferentes, "
    " linea_aidu, tipo_objeto, keywords_matched, lote_id) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)

_INSERT_ORG_AUTO_SQL = (
    "INSERT OR IGNORE INTO organismos_ohiggins_auto "
    "(unit_code, codigo_organismo, nombre_organismo, region_raw, "
    " primera_licitacion) "
    "VALUES (?, ?, ?, ?, ?)"
)


def persistir_lote(items: List[dict], *, lote_id: str) -> int:
    """Envia items en batches via execute_pipeline. Devuelve n statements
    enviados (no n filas efectivamente nuevas — INSERT OR IGNORE oculta
    los duplicados a nivel statement).
    """
    if not items:
        return 0
    statements_enviados = 0
    for i in range(0, len(items), BATCH_SIZE_PERSIST):
        batch = items[i : i + BATCH_SIZE_PERSIST]
        statements = []
        for it in batch:
            args = [arg_for_value(v) for v in (
                it.get("codigo_mp"),
                it.get("correlativo_item"),
                it.get("fecha_adjudicacion"),
                it.get("tipo_licitacion"),
                it.get("organismo_comprador"),
                it.get("unit_code"),
                it.get("organismo_region"),
                it.get("region_entrega"),
                it.get("producto_descripcion"),
                it.get("unidad_medida"),
                it.get("cantidad"),
                it.get("precio_unitario"),
                it.get("monto_total"),
                it.get("proveedor_nombre"),
                it.get("proveedor_rut"),
                it.get("n_oferentes"),
                it.get("linea_aidu"),
                it.get("tipo_objeto"),
                it.get("keywords_matched"),
                lote_id,
            )]
            statements.append({"sql": _INSERT_INTELIGENCIA_SQL, "args": args})
        turso_http_client.execute_pipeline(statements, timeout=90.0)
        statements_enviados += len(statements)
    return statements_enviados


def persistir_descubrimientos(descubrimientos: List[dict]) -> int:
    """Persiste filas nuevas en organismos_ohiggins_auto. Idempotente."""
    if not descubrimientos:
        return 0
    statements = []
    for d in descubrimientos:
        args = [arg_for_value(v) for v in (
            d["unit_code"],
            d.get("codigo_organismo", ""),
            d["nombre_organismo"],
            d["region_raw"],
            d.get("primera_licitacion", ""),
        )]
        statements.append({"sql": _INSERT_ORG_AUTO_SQL, "args": args})
    turso_http_client.execute_pipeline(statements, timeout=60.0)
    return len(statements)


# ============================================================
# PIPELINE PRINCIPAL: ingerir_rango
# ============================================================

ProgressCallback = Callable[[Dict[str, int]], None]


def ingerir_rango(
    fecha_desde: date,
    fecha_hasta: date,
    *,
    lote_id: str = "manual",
    discovery_sample_size: int = 0,
    progress_callback: Optional[ProgressCallback] = None,
    progress_every: int = 100,
    cliente: Optional[MercadoPublicoClient] = None,
    csv_organismos: Optional[Path] = None,
    rng_seed: Optional[int] = None,
    # S13.5: nuevos parametros para modo backfill historico.
    usar_semantico: bool = False,
    cost_guard_max_usd: Optional[float] = None,
    codigos_existentes_buffer_days: int = 30,
    codigos_existentes_override: Optional[Set[str]] = None,
) -> StatsCorrida:
    """Descarga, filtra, categoriza y persiste adjudicaciones O'Higgins
    en el rango [fecha_desde, fecha_hasta].

    Args:
        fecha_desde, fecha_hasta: limites inclusivos. fecha_desde <= fecha_hasta.
        lote_id: tag que va a inteligencia_precios.lote_id (audit).
        discovery_sample_size: cuantos codigos NO en seed se pegan para
            descubrimiento (default 0 = backfill, sin discovery; 25 cron).
        progress_callback: invocada cada `progress_every` detalles con el
            dict de progreso. CLI lo formatea como [PROGRESO] ...
        progress_every: cada cuantos detalles llamar el callback.
        cliente: para inyeccion en tests. Default: nueva instancia.
        csv_organismos: override de la ruta del seed CSV (tests).
        rng_seed: semilla del RNG para discovery sampling (tests).
        usar_semantico: opt-in modo backfill. Cuando True clasifica via
            Claude API por cada item (con fallback lexical individual ante
            ClaudeApiUnavailableError). Cuando False (default) mantiene el
            comportamiento del cron diario: solo lexical, costo Claude $0.
        cost_guard_max_usd: si no es None, aborta el run cuando la proyeccion
            de costo Claude (basada en items semanticos procesados y dias
            restantes) excede el tope. La corrida graba stats.aborted_cost_guard.
            Solo aplica si usar_semantico=True.
        codigos_existentes_buffer_days: para idempotencia, expande la
            ventana de fecha del SELECT de codigos ya en BD en +/- N dias
            (cubre licitaciones publicadas un mes y adjudicadas otro).
            Default 30. Solo se usa si usar_semantico=True (modo backfill).
        codigos_existentes_override: para tests, set explicito de codigos
            que se consideran "ya en BD" en lugar de pegar a Turso.
    """
    if fecha_desde > fecha_hasta:
        raise ValueError(
            f"fecha_desde {fecha_desde} > fecha_hasta {fecha_hasta}"
        )

    stats = StatsCorrida(
        fecha_desde=fecha_desde.isoformat(),
        fecha_hasta=fecha_hasta.isoformat(),
    )
    rng = random.Random(rng_seed)
    cli = cliente or MercadoPublicoClient(save_raw=False)
    catalogo = get_catalogo()
    unit_codes_validos = cargar_unit_codes_validos(csv_organismos)
    if not unit_codes_validos:
        logger.warning(
            "Sin unit_codes validos (CSV+auto vacios). El filtro pre-detalle "
            "descartara todo. Verificar config/organismos_ohiggins.csv."
        )

    # S13.5: en modo backfill semantico, precargar codigos_mp ya en BD
    # para hacer SKIP antes de pegar detalle (ahorra cuota MP + Claude $).
    # En modo cron diario (usar_semantico=False), no aplica: la
    # idempotencia ya vive en INSERT OR IGNORE y el costo Claude es $0.
    if codigos_existentes_override is not None:
        codigos_existentes: Set[str] = set(codigos_existentes_override)
    elif usar_semantico:
        codigos_existentes = cargar_codigos_existentes(
            fecha_desde, fecha_hasta,
            buffer_days=codigos_existentes_buffer_days,
        )
    else:
        codigos_existentes = set()

    items_buffer: List[dict] = []
    descubrimientos_buffer: List[dict] = []
    t_inicio = time.time()

    dias = []
    d = fecha_desde
    while d <= fecha_hasta:
        dias.append(d)
        d = d + timedelta(days=1)
    total_dias = len(dias)

    for dia_idx, dia in enumerate(dias, start=1):
        logger.info("Procesando dia %s (%d/%d)", dia.isoformat(), dia_idx, total_dias)
        try:
            listado = cli.listar_adjudicadas_por_fecha(dia) or []
        except Exception as e:
            logger.error("Listado fallo dia %s: %s", dia, e)
            listado = []
        stats.n_listados_total += len(listado)

        matched, sample_discovery = _filtrar_listado(
            listado, unit_codes_validos, discovery_sample_size, rng
        )
        stats.n_filtrados_por_unit += len(matched)

        # Procesar primero matched (seguro O'Higgins), luego sample_discovery.
        for source_tag, codigos_a_pegar in (("matched", matched), ("discovery", sample_discovery)):
            for lic in codigos_a_pegar:
                codigo = lic.get("CodigoExterno", "")
                if not codigo:
                    continue
                # S13.5: SKIP idempotente ANTES de pegar detalle.
                # Codigos ya en BD no se vuelven a procesar: ahorra cuota
                # API MP + costo Claude. Aplica solo si el set se cargo.
                if codigo in codigos_existentes:
                    stats.n_skip_idempotente += 1
                    continue
                try:
                    det = cli.detalle_licitacion(codigo)
                except Exception as e:
                    logger.warning("detalle %s fallo: %s", codigo, e)
                    continue
                stats.n_detalles_pegados += 1

                entry = _entry_de_detalle(det)
                if not entry:
                    continue
                comprador = entry.get("Comprador") if isinstance(entry.get("Comprador"), dict) else {}
                region_raw = comprador.get("RegionUnidad") or ""

                # Filtro 1: region O'Higgins (defense in depth; el seed
                # CSV deberia garantizarlo pero discovery puede arrojar otra region).
                if not es_ohiggins(region_raw):
                    stats.n_descartados_no_ohiggins += 1
                    continue

                # Si veniamos de discovery y resulta O'Higgins, registrar
                # como descubrimiento para que el cron siguiente lo incluya.
                if source_tag == "discovery":
                    uc = extraer_unit_code(codigo)
                    if uc and uc not in unit_codes_validos:
                        descubrimientos_buffer.append({
                            "unit_code": uc,
                            "codigo_organismo": (comprador.get("CodigoOrganismo") or ""),
                            "nombre_organismo": (comprador.get("NombreOrganismo") or ""),
                            "region_raw": region_raw,
                            "primera_licitacion": codigo,
                        })
                        # Lo agregamos al set in-memory para no re-descubrir en el mismo run.
                        unit_codes_validos.add(uc)
                        stats.n_organismos_descubiertos += 1

                # Filtro 2: tipo en scope.
                tipo_lic = (entry.get("Tipo") or "").upper()
                if tipo_lic not in TIPOS_SCOPE:
                    stats.n_descartados_tipo += 1
                    continue

                # Expandir items y categorizar.
                items = expandir_items(det, fecha_adjudicacion=dia.isoformat())
                if not items:
                    stats.n_descartados_sin_items += 1
                    continue
                for it in items:
                    categorizar_item(it, catalog=catalogo, usar_semantico=usar_semantico)
                    # S13.5: contar llamadas Claude exitosas (cuando metodo
                    # quedo 'semantic'; si Claude fallo y cayo a lexical el
                    # metodo es 'keyword' y NO se cuenta para costo).
                    if it.get("clasificacion_metodo") == "semantic":
                        stats.n_llamadas_semanticas += 1
                    stats.distribucion_por_linea[it["linea_aidu"]] = (
                        stats.distribucion_por_linea.get(it["linea_aidu"], 0) + 1
                    )
                    stats.distribucion_por_tipo[it["tipo_objeto"]] = (
                        stats.distribucion_por_tipo.get(it["tipo_objeto"], 0) + 1
                    )
                items_buffer.extend(items)
                stats.n_items_categorizados += len(items)

                # Progress callback cada N detalles
                if progress_callback and stats.n_detalles_pegados % progress_every == 0:
                    progress_callback({
                        "lote_id": lote_id,
                        "dia_idx": dia_idx,
                        "total_dias": total_dias,
                        "fecha_actual": dia.isoformat(),
                        "n_detalles_pegados": stats.n_detalles_pegados,
                        "n_items_categorizados": stats.n_items_categorizados,
                        "elapsed_seg": int(time.time() - t_inicio),
                    })

                # Flush buffer a Turso cada BATCH_SIZE_PERSIST items
                if len(items_buffer) >= BATCH_SIZE_PERSIST:
                    persistir_lote(items_buffer, lote_id=lote_id)
                    stats.n_lotes_persistidos += 1
                    items_buffer.clear()

                    # S13.5: cost guard. Evaluamos al cierre de cada flush
                    # para amortizar el overhead. Proyectamos al fin del
                    # rango usando proporcion de dias procesados.
                    if (cost_guard_max_usd is not None
                            and usar_semantico
                            and stats.n_llamadas_semanticas > 0):
                        costo_acumulado = _estimar_costo_claude(stats.n_llamadas_semanticas)
                        proporcion_dias = dia_idx / max(total_dias, 1)
                        proyectado = costo_acumulado / max(proporcion_dias, 0.01)
                        if proyectado > cost_guard_max_usd:
                            stats.aborted_cost_guard = True
                            stats.costo_claude_usd = costo_acumulado
                            logger.error(
                                "ABORT cost guard: costo acumulado $%.3f USD "
                                "proyectado $%.3f USD supera tope $%.2f USD. "
                                "Items semanticos hasta aqui: %d. Flush ya "
                                "persistido.",
                                costo_acumulado, proyectado, cost_guard_max_usd,
                                stats.n_llamadas_semanticas,
                            )
                            stats.dias_procesados = dia_idx
                            stats.tiempo_total_seg = time.time() - t_inicio
                            # Flush ultima tanda de descubrimientos antes de salir.
                            if descubrimientos_buffer:
                                persistir_descubrimientos(descubrimientos_buffer)
                                descubrimientos_buffer.clear()
                            return stats

        # Al fin de cada dia: flush buffers (no esperamos al limite del batch)
        if items_buffer:
            persistir_lote(items_buffer, lote_id=lote_id)
            stats.n_lotes_persistidos += 1
            items_buffer.clear()
        if descubrimientos_buffer:
            persistir_descubrimientos(descubrimientos_buffer)
            descubrimientos_buffer.clear()

    stats.dias_procesados = total_dias
    stats.tiempo_total_seg = time.time() - t_inicio
    # S13.5: estimacion final de costo Claude. Es estimacion, no medicion
    # real (la API no devuelve el costo). Basada en n llamadas exitosas a
    # clasificar_via_claude * tokens promedio observados en S13.4.3.
    stats.costo_claude_usd = _estimar_costo_claude(stats.n_llamadas_semanticas)
    return stats
