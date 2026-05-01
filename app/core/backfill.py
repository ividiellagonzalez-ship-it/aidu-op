"""
AIDU Op · Backfill y actualización incremental
================================================
Estrategias:
1. BACKFILL: descarga inicial 24 meses al instalar (proceso largo, una sola vez)
2. INCREMENTAL: actualización diaria automática de últimos 7 días
3. RECONSTRUCCIÓN: re-procesar desde cache local (sin pegar API)
"""
import logging
import time
from datetime import date, timedelta
from typing import Optional

from config.settings import BACKFILL_MONTHS, INCREMENTAL_DAYS_LOOKBACK
from app.api.mercadopublico import MercadoPublicoClient
from app.core.ingesta import ingestar_lote
from app.db.migrator import get_connection

logger = logging.getLogger(__name__)


def _set_param(clave: str, valor: str):
    """Helper para actualizar parámetros del sistema"""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO aidu_parametros (clave, valor)
            VALUES (?, ?)
            ON CONFLICT(clave) DO UPDATE SET
                valor = excluded.valor,
                fecha_modificacion = datetime('now', 'localtime')
        """, (clave, valor))
        conn.commit()
    finally:
        conn.close()


def _get_param(clave: str, default: str = "") -> str:
    conn = get_connection()
    try:
        row = conn.execute("SELECT valor FROM aidu_parametros WHERE clave = ?", (clave,)).fetchone()
        return row["valor"] if row else default
    finally:
        conn.close()


def ejecutar_backfill_dias(dias: int = 14, fecha_fin: Optional[date] = None):
    """
    Backfill MVP: descarga últimos N días.
    Más rápido y barato que backfill 24m completo.
    Útil para arrancar y validar el sistema con datos reales mínimos.
    """
    fecha_fin = fecha_fin or date.today()
    fecha_inicio = fecha_fin - timedelta(days=dias)

    logger.info(f"📥 Backfill MVP · {fecha_inicio} → {fecha_fin} ({dias} días)")

    client = MercadoPublicoClient()
    inicio = time.time()
    total_descargadas = 0
    total_nuevas = 0
    dias_procesados = 0

    actual = fecha_inicio
    while actual <= fecha_fin:
        # Skip si ya tenemos datos completos de ese día
        conn = get_connection()
        ya_procesado = conn.execute("""
            SELECT 1 FROM mp_ingesta_log
            WHERE fecha_consultada = ? AND estado = 'OK'
            LIMIT 1
        """, (actual.isoformat(),)).fetchone()
        conn.close()

        if ya_procesado:
            logger.debug(f"Skip {actual} (ya procesado)")
            actual += timedelta(days=1)
            dias_procesados += 1
            continue

        try:
            licitaciones = client.listar_adjudicadas_por_fecha(actual)
            stats = ingestar_lote(licitaciones, fecha=actual)
            total_descargadas += stats["total"]
            total_nuevas += stats["nuevas"]

            if stats["total"] > 0:
                logger.info(
                    f"✅ {actual} · {stats['total']} desc · "
                    f"{stats['nuevas']} nuevas · {stats['duracion']}s"
                )
        except Exception as e:
            logger.error(f"❌ Error en {actual}: {e}")

        actual += timedelta(days=1)
        dias_procesados += 1

    duracion_total = time.time() - inicio
    logger.info(f"✅ Backfill MVP completado")
    logger.info(f"   Total: {total_descargadas} licitaciones · {duracion_total/60:.1f} min")

    _set_param("ultima_ingesta", date.today().isoformat())

    return {
        "dias_procesados": dias_procesados,
        "total_descargadas": total_descargadas,
        "nuevas": total_nuevas,
        "duracion_minutos": round(duracion_total / 60, 1)
    }


def ejecutar_backfill(meses: int = BACKFILL_MONTHS, fecha_fin: Optional[date] = None):
    """
    Backfill agresivo de últimos N meses.
    PROCESO LARGO: puede tomar varios días con rate limit conservador.

    Cada día se procesa independientemente — si se interrumpe,
    se puede reanudar sin problemas (UPSERT idempotente).
    """
    fecha_fin = fecha_fin or date.today()
    fecha_inicio = fecha_fin - timedelta(days=meses * 30)

    logger.info(f"🚀 Iniciando BACKFILL · {fecha_inicio} → {fecha_fin}")
    logger.info(f"   Días a procesar: ~{(fecha_fin - fecha_inicio).days}")

    client = MercadoPublicoClient()
    inicio = time.time()
    total_descargadas = 0
    total_nuevas = 0

    actual = fecha_inicio
    dias_procesados = 0

    while actual <= fecha_fin:
        # Skip si ya tenemos datos completos de ese día
        conn = get_connection()
        ya_procesado = conn.execute("""
            SELECT 1 FROM mp_ingesta_log
            WHERE fecha_consultada = ? AND estado = 'OK'
            LIMIT 1
        """, (actual.isoformat(),)).fetchone()
        conn.close()

        if ya_procesado:
            logger.debug(f"Skip {actual} (ya procesado)")
            actual += timedelta(days=1)
            dias_procesados += 1
            continue

        try:
            licitaciones = client.listar_adjudicadas_por_fecha(actual)
            stats = ingestar_lote(licitaciones, fecha=actual)
            total_descargadas += stats["total"]
            total_nuevas += stats["nuevas"]

            if stats["total"] > 0:
                logger.info(
                    f"✅ {actual} · {stats['total']} desc · "
                    f"{stats['nuevas']} nuevas · {stats['duracion']}s"
                )
        except Exception as e:
            logger.error(f"❌ Error en {actual}: {e}")

        actual += timedelta(days=1)
        dias_procesados += 1

        # Progreso cada 30 días
        if dias_procesados % 30 == 0:
            duracion_min = (time.time() - inicio) / 60
            logger.info(
                f"📊 Progreso: {dias_procesados} días · "
                f"{total_descargadas} licitaciones · {duracion_min:.1f} min"
            )

    duracion_total = time.time() - inicio
    logger.info(f"✅ BACKFILL COMPLETO")
    logger.info(f"   Total licitaciones descargadas: {total_descargadas}")
    logger.info(f"   Nuevas en BD: {total_nuevas}")
    logger.info(f"   Duración: {duracion_total/60:.1f} minutos")

    _set_param("backfill_completado", "1")
    _set_param("ultima_ingesta", date.today().isoformat())

    return {
        "dias_procesados": dias_procesados,
        "total_descargadas": total_descargadas,
        "nuevas": total_nuevas,
        "duracion_minutos": round(duracion_total / 60, 1)
    }


def actualizacion_incremental(dias_lookback: int = INCREMENTAL_DAYS_LOOKBACK):
    """
    Actualización incremental: revisa últimos N días.
    Útil ejecutar diariamente vía scheduler.
    """
    fecha_fin = date.today()
    fecha_inicio = fecha_fin - timedelta(days=dias_lookback)

    logger.info(f"🔄 Actualización incremental · {fecha_inicio} → {fecha_fin}")

    client = MercadoPublicoClient()
    total = 0
    nuevas = 0

    actual = fecha_inicio
    while actual <= fecha_fin:
        try:
            licitaciones = client.listar_adjudicadas_por_fecha(actual)
            stats = ingestar_lote(licitaciones, fecha=actual)
            total += stats["total"]
            nuevas += stats["nuevas"]
        except Exception as e:
            logger.error(f"Error en {actual}: {e}")
        actual += timedelta(days=1)

    _set_param("ultima_ingesta", date.today().isoformat())
    logger.info(f"✅ Incremental: {total} revisadas, {nuevas} nuevas")

    return {"total": total, "nuevas": nuevas}


def estado_actual():
    """Reporte rápido del estado de la BD"""
    conn = get_connection()
    try:
        n_licitaciones = conn.execute("SELECT COUNT(*) c FROM mp_licitaciones_adj").fetchone()["c"]
        n_proyectos = conn.execute("SELECT COUNT(*) c FROM aidu_proyectos").fetchone()["c"]
        n_ingestas = conn.execute("SELECT COUNT(*) c FROM mp_ingesta_log").fetchone()["c"]
        n_categorizadas = conn.execute(
            "SELECT COUNT(DISTINCT codigo_externo) c FROM mp_categorizacion_aidu"
        ).fetchone()["c"]

        ultima = conn.execute("""
            SELECT fecha_consultada, n_licitaciones_descargadas
            FROM mp_ingesta_log ORDER BY id DESC LIMIT 1
        """).fetchone()

        backfill = _get_param("backfill_completado", "0") == "1"

        return {
            "licitaciones_historicas": n_licitaciones,
            "proyectos_cartera": n_proyectos,
            "categorizadas_aidu": n_categorizadas,
            "ingestas_ejecutadas": n_ingestas,
            "ultima_ingesta": ultima["fecha_consultada"] if ultima else None,
            "backfill_completado": backfill,
        }
    finally:
        conn.close()
