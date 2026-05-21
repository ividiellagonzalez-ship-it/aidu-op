"""
AIDU Op · Orquestador de backfill MVP en 6 fases
==================================================
S12.3 v2.2 — Pobla el activo de inteligencia de mercado a partir de
licitaciones MP en una ventana histórica acotada. Reutiliza
`descarga_historica._persistir_licitaciones` con `use_http_client=True`
para escribir directo a Turso vía /v2/pipeline (S12.2.2), sin caer
al SQLite efímero del runner.

Diseño futuro
-------------
El orquestador NO está hardcodeado a "3 meses". Acepta cualquier
`fecha_desde`/`fecha_hasta` y se reutiliza tal cual en:
  - S12.3.1 (expansión a 6 meses).
  - S12.3.2 (expansión a 12 meses).
Cualquier hardcoding de ventana viola el principio del MVP.

Filosofía de fases
------------------
Las 6 fases del plan agrupan conceptos del activo, pero NO son 6
descargas HTTP independientes. La descarga real son 2 operaciones:
adjudicadas + vigentes. Las "fases" 2/3/4/5 son side effects de la 1
+ una agregación final de catálogos (mp_proveedores).

Cada fase escribe una fila en `mp_ingesta_log` con `tipo='backfill_mvp_3m'`
y `subtipo='fase_N_nombre'` para que el operador inspeccione el progreso
en una sola query post-corrida.
"""
from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Dict, List, Optional

from app.api.mercadopublico import MercadoPublicoClient
from app.core.descarga_historica import descargar_rango
from app.db import turso_http_client
from app.db._hrana_types import arg_for_value

logger = logging.getLogger(__name__)


# Mapeo código administrativo → nombre legible que matchea el filtro
# por substring de `filtrar_por_region`. Substring porque la API devuelve
# nombres largos ("Región Metropolitana de Santiago", "Región del
# Libertador General Bernardo O'Higgins") y el matcher es lowercase
# tolerante. S12.3.x candidato a mover a `config/settings.py` cuando
# haya más sprints que lo consuman.
REGIONES_CODIGO_A_NOMBRE: Dict[str, str] = {
    "II": "Antofagasta",
    "V": "Valparaíso",
    "RM": "Metropolitana",
    "VI": "O'Higgins",
    "X": "Los Lagos",
}

# Fases canónicas en orden de ejecución. El selector --fases del CLI
# subsetea estos nombres. Default = todas.
FASES_DEFAULT = (
    "cabecera", "items_producto", "items_servicio",
    "catalogos", "adj", "vigentes",
)

# Identificador de bitácora. Todas las filas escritas en `mp_ingesta_log`
# durante este orquestador llevan tipo='backfill_mvp_3m' para que el
# operador filtre el run completo con una sola query.
TIPO_BITACORA = "backfill_mvp_3m"


class BackfillMvpError(Exception):
    """Error fatal del orquestador (causa abort de fases posteriores)."""


def resolver_regiones(codigos: List[str]) -> List[str]:
    """
    Traduce códigos administrativos del MVP ('II','V','RM','VI','X') a
    nombres legibles para `filtrar_por_region`. Códigos desconocidos
    se devuelven literal (con un warning) para que el matcher por
    substring igual los intente.
    """
    out: List[str] = []
    for cod in codigos:
        nombre = REGIONES_CODIGO_A_NOMBRE.get(cod.strip().upper())
        if nombre:
            out.append(nombre)
        else:
            logger.warning(f"⚠️  Código de región desconocido: {cod!r}. "
                           "Se pasa literal al filtro por substring.")
            out.append(cod)
    return out


def _registrar_bitacora_fase(
    *,
    subtipo: str,
    fecha_consultada: str,
    n_descargadas: int,
    n_nuevas: int,
    n_actualizadas: int,
    duracion_s: float,
    estado: str = "OK",
    error_msg: Optional[str] = None,
) -> None:
    """
    Escribe una fila en `mp_ingesta_log` con tipo=backfill_mvp_3m. Si
    Turso no está configurado (modo dry-run, test local), el caller no
    debería llamar a esta función — pero defensivamente, no levanta.
    """
    if not turso_http_client.is_configured():
        logger.info(
            f"📝 [dry-run / sin Turso] {subtipo}: "
            f"descargadas={n_descargadas} nuevas={n_nuevas} "
            f"actualizadas={n_actualizadas} {duracion_s:.1f}s estado={estado}"
        )
        return
    sql = (
        "INSERT INTO mp_ingesta_log "
        "(fecha_consultada, n_licitaciones_descargadas, n_nuevas, "
        " n_actualizadas, duracion_segundos, estado, error_msg, tipo, subtipo) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
    )
    args = [arg_for_value(v) for v in (
        fecha_consultada, n_descargadas, n_nuevas, n_actualizadas,
        round(duracion_s, 2), estado, error_msg, TIPO_BITACORA, subtipo,
    )]
    turso_http_client.execute_pipeline([{"sql": sql, "args": args}])


def _contar(sql: str, args: Optional[list] = None) -> int:
    """COUNT(*) vía HTTP. Devuelve 0 si Turso no está configurado."""
    if not turso_http_client.is_configured():
        return 0
    row = turso_http_client.query_one(sql, args=args)
    if not row or row[0] is None:
        return 0
    try:
        return int(row[0])
    except (ValueError, TypeError):
        return 0


def ejecutar_backfill_mvp(
    *,
    fecha_desde: date,
    fecha_hasta: date,
    regiones_codigos: List[str],
    tipos: List[str],
    fases: Optional[List[str]] = None,
    dry_run: bool = False,
    save_raw: bool = False,
) -> Dict:
    """
    Orquesta el backfill MVP en 6 fases. Reutilizable para S12.3.1 (6m)
    y S12.3.2 (12m) sin cambios — todo parametrizado.

    Args:
        fecha_desde: primer día (inclusive).
        fecha_hasta: último día (inclusive).
        regiones_codigos: lista de códigos administrativos
            (ej: ['II','V','RM','VI','X']). Se traducen a nombres.
        tipos: lista de tipos OCDS (ej: ['CA','L1','LE']). 'CA' se
            mapea a 'AGIL' internamente (alias del plan).
        fases: subset de FASES_DEFAULT. None = todas.
        dry_run: si True, no escribe a Turso, solo loggea volumen estimado.
        save_raw: si True, el cliente MP guarda JSON crudo en data/raw/.
            El MVP usa False para no llenar el filesystem.

    Returns:
        Dict con stats por fase + agregados. Schema:
        {
            'fase_1_cabecera': {'nuevas': N, 'actualizadas': N, 'items': N, ...},
            'fase_2_items_producto': {'count_post': N, ...},
            ...
            'agregado': {'duracion_s': N, 'fases_ok': N, 'fases_fallidas': N},
        }
    """
    fases_set = set(fases or FASES_DEFAULT)
    regiones_nombres = resolver_regiones(regiones_codigos)

    inicio_total = time.time()
    stats: Dict[str, Dict] = {}
    fases_fallidas: List[str] = []

    if dry_run:
        logger.info(
            f"🌵 DRY-RUN backfill MVP — sin escritura: "
            f"{fecha_desde}→{fecha_hasta}, {len(regiones_codigos)} regiones, "
            f"tipos={tipos}, fases={sorted(fases_set)}"
        )

    # ============================================================
    # FASE 1 — Cabecera CA+L1+LE adjudicadas
    # ============================================================
    if "cabecera" in fases_set:
        sub = "fase_1_cabecera"
        t0 = time.time()
        try:
            if dry_run:
                res = {"nuevas": 0, "actualizadas": 0, "fallidas": 0,
                       "items": 0, "adjudicaciones": 0, "organismos": 0,
                       "total_vigentes": 0, "total_adjudicadas": 0, "total_agiles": 0}
            else:
                res = descargar_rango(
                    fecha_inicio=fecha_desde,
                    fecha_fin=fecha_hasta,
                    incluir_adjudicadas=True,
                    incluir_vigentes=False,
                    incluir_agiles=True,
                    saltar_descargados=False,
                    use_http_client=True,
                    filtro_tipos=tipos,
                    filtro_regiones=regiones_nombres,
                    save_raw=save_raw,
                )
            stats[sub] = res
            duracion = time.time() - t0
            n_total = res.get("total_adjudicadas", 0) + res.get("total_agiles", 0)
            n_nuevas = res.get("total_adjudicadas", 0) + res.get("total_agiles", 0)
            if not dry_run:
                _registrar_bitacora_fase(
                    subtipo=sub,
                    fecha_consultada=fecha_desde.isoformat(),
                    n_descargadas=n_total,
                    n_nuevas=n_nuevas,
                    n_actualizadas=0,
                    duracion_s=duracion,
                )
        except Exception as e:
            fases_fallidas.append(sub)
            stats[sub] = {"error": str(e)}
            duracion = time.time() - t0
            if not dry_run:
                try:
                    _registrar_bitacora_fase(
                        subtipo=sub, fecha_consultada=fecha_desde.isoformat(),
                        n_descargadas=0, n_nuevas=0, n_actualizadas=0,
                        duracion_s=duracion, estado="ERROR", error_msg=str(e)[:200],
                    )
                except Exception:
                    pass
            raise BackfillMvpError(
                f"Fase 1 (cabecera) falló: {e}. Fases posteriores NO ejecutan."
            ) from e

    # ============================================================
    # FASE 2 — Items PRODUCTO (side effect de Fase 1, sólo conteo)
    # ============================================================
    if "items_producto" in fases_set and "cabecera" in fases_set:
        sub = "fase_2_items_producto"
        t0 = time.time()
        count = (0 if dry_run else _contar(
            "SELECT COUNT(*) FROM mp_licitaciones_items WHERE tipo_origen='producto'"
        ))
        stats[sub] = {"count_post": count}
        duracion = time.time() - t0
        if not dry_run:
            _registrar_bitacora_fase(
                subtipo=sub, fecha_consultada=fecha_desde.isoformat(),
                n_descargadas=0, n_nuevas=count, n_actualizadas=0,
                duracion_s=duracion,
            )

    # ============================================================
    # FASE 3 — Items SERVICIO (side effect de Fase 1, sólo conteo)
    # ============================================================
    if "items_servicio" in fases_set and "cabecera" in fases_set:
        sub = "fase_3_items_servicio"
        t0 = time.time()
        count = (0 if dry_run else _contar(
            "SELECT COUNT(*) FROM mp_licitaciones_items WHERE tipo_origen='servicio'"
        ))
        stats[sub] = {"count_post": count}
        duracion = time.time() - t0
        if not dry_run:
            _registrar_bitacora_fase(
                subtipo=sub, fecha_consultada=fecha_desde.isoformat(),
                n_descargadas=0, n_nuevas=count, n_actualizadas=0,
                duracion_s=duracion,
            )

    # ============================================================
    # FASE 4 — Catálogos: recalcular mp_proveedores desde mp_adjudicaciones
    # ============================================================
    if "catalogos" in fases_set:
        sub = "fase_4_catalogos"
        t0 = time.time()
        try:
            if dry_run:
                n_prov, n_org = 0, 0
            else:
                n_prov = _recalcular_proveedores_via_http()
                n_org = _contar("SELECT COUNT(*) FROM mp_organismos")
            stats[sub] = {"proveedores": n_prov, "organismos": n_org}
            duracion = time.time() - t0
            if not dry_run:
                _registrar_bitacora_fase(
                    subtipo=sub, fecha_consultada=fecha_desde.isoformat(),
                    n_descargadas=0, n_nuevas=n_prov + n_org,
                    n_actualizadas=0, duracion_s=duracion,
                )
        except Exception as e:
            fases_fallidas.append(sub)
            stats[sub] = {"error": str(e)}
            logger.error(f"Fase 4 (catálogos) falló: {e}. Continúo.")

    # ============================================================
    # FASE 5 — Resoluciones detalladas (side effect, conteo)
    # ============================================================
    if "adj" in fases_set and "cabecera" in fases_set:
        sub = "fase_5_adj"
        t0 = time.time()
        count = (0 if dry_run else _contar(
            "SELECT COUNT(*) FROM mp_adjudicaciones"
        ))
        stats[sub] = {"count_post": count}
        duracion = time.time() - t0
        if not dry_run:
            _registrar_bitacora_fase(
                subtipo=sub, fecha_consultada=fecha_desde.isoformat(),
                n_descargadas=0, n_nuevas=count, n_actualizadas=0,
                duracion_s=duracion,
            )

    # ============================================================
    # FASE 6 — Vigentes (independiente, no requiere Fase 1)
    # ============================================================
    if "vigentes" in fases_set:
        sub = "fase_6_vigentes"
        t0 = time.time()
        try:
            if dry_run:
                res = {"total_vigentes": 0, "total_agiles": 0}
            else:
                res = descargar_rango(
                    fecha_inicio=fecha_desde,
                    fecha_fin=fecha_hasta,
                    incluir_adjudicadas=False,
                    incluir_vigentes=True,
                    incluir_agiles=True,
                    saltar_descargados=False,
                    use_http_client=True,
                    filtro_tipos=tipos,
                    filtro_regiones=regiones_nombres,
                    save_raw=save_raw,
                )
            stats[sub] = res
            duracion = time.time() - t0
            n_total = res.get("total_vigentes", 0) + res.get("total_agiles", 0)
            if not dry_run:
                _registrar_bitacora_fase(
                    subtipo=sub, fecha_consultada=fecha_desde.isoformat(),
                    n_descargadas=n_total, n_nuevas=n_total,
                    n_actualizadas=0, duracion_s=duracion,
                )
        except Exception as e:
            fases_fallidas.append(sub)
            stats[sub] = {"error": str(e)}
            logger.error(f"Fase 6 (vigentes) falló: {e}.")

    stats["agregado"] = {
        "duracion_s": round(time.time() - inicio_total, 2),
        "fases_ok": len([k for k in stats if k.startswith("fase_") and "error" not in stats[k]]),
        "fases_fallidas": fases_fallidas,
        "fases_ejecutadas": sorted(fases_set),
    }
    return stats


def _recalcular_proveedores_via_http() -> int:
    """
    Reconstruye `mp_proveedores` desde `mp_adjudicaciones` vía HTTP.

    Idempotente: DELETE + INSERT batch. La query base agrega por RUT,
    cuenta adjudicaciones, suma montos, calcula primera/última fecha.
    Diseño espeja `enriquecimiento._recalcular_proveedores` pero usando
    el transporte HTTP en lugar de SQLite local.

    Returns:
        Cantidad de proveedores únicos insertados.
    """
    sql_agg = """
        SELECT
            a.rut_proveedor AS rut,
            MAX(a.nombre_proveedor) AS nombre,
            COUNT(DISTINCT a.codigo_externo) AS n_adj,
            COALESCE(SUM(a.monto_linea), 0) AS monto_total
        FROM mp_adjudicaciones a
        WHERE a.rut_proveedor IS NOT NULL AND a.rut_proveedor <> ''
        GROUP BY a.rut_proveedor
    """
    rows = turso_http_client.query_all(sql_agg)
    if not rows:
        return 0

    # DELETE previo para idempotencia (mantiene paridad con
    # `enriquecimiento._recalcular_proveedores`).
    turso_http_client.execute_pipeline([{"sql": "DELETE FROM mp_proveedores"}])

    sql_ins = (
        "INSERT OR REPLACE INTO mp_proveedores "
        "(rut, nombre, n_adjudicaciones, monto_total_adjudicado) "
        "VALUES (?, ?, ?, ?)"
    )
    CHUNK = 50
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i:i + CHUNK]
        statements = [
            {"sql": sql_ins, "args": [arg_for_value(v) for v in (
                r[0], r[1] or "", int(r[2] or 0), int(r[3] or 0),
            )]}
            for r in chunk
        ]
        turso_http_client.execute_pipeline(statements)
    return len(rows)
