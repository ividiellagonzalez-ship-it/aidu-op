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

def categorizar_item(item: dict, catalog=None) -> dict:
    """Mutates `item` adding linea_aidu, tipo_objeto, keywords_matched.
    Devuelve el dict (para encadenar)."""
    descripcion = item.get("producto_descripcion") or ""
    linea, kws = categorizar_linea(descripcion, catalog=catalog)
    tipo_obj = categorizar_tipo_objeto(descripcion, catalog=catalog)
    item["linea_aidu"] = linea
    item["tipo_objeto"] = tipo_obj
    item["keywords_matched"] = ",".join(kws) if kws else ""
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
                    categorizar_item(it, catalog=catalogo)
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
    return stats
