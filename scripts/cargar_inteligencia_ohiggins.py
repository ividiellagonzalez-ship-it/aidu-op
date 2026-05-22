"""
AIDU Op · CLI para carga de inteligencia_precios (S13)
========================================================
Disparado por el workflow GH Actions inteligencia_backfill_lote.yml o
manualmente para ad-hoc runs. Tambien lo invoca el cron diario
inteligencia_adjudicadas_diaria.yml con --discovery-sample-size 25.

USO
---
    python -m scripts.cargar_inteligencia_ohiggins \
        --fecha-desde 2026-04-30 \
        --fecha-hasta 2026-05-21 \
        --lote-id backfill_1 \
        --discovery-sample-size 0

EXIT CODES
----------
    0: ok
    1: error de configuracion (ticket, csv, etc)
    2: error de Turso al persistir
    3: error inesperado

LOGGING [PROGRESO]
-------------------
Cada 100 detalles procesados (configurable via --progress-every),
imprime una linea estructurada para monitoreo en tiempo real desde
la UI de GitHub Actions:

    [PROGRESO] Lote {lote_id} | dia X/Y (YYYY-MM-DD) | \
        detalles procesados: NNN | items en buffer/Turso: MMM | \
        tiempo transcurrido: HH:MM | eta restante: HH:MM

Si pasan > 10 min sin nueva linea [PROGRESO], se asume trabazon.
"""
# Fix A canonico de TD-01: UTF-8 wrapper antes de cualquier import.
import sys
import io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import argparse
import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict

# Path setup
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.ingesta_inteligencia_precios import (
    ingerir_rango,
    StatsCorrida,
    TIPOS_SCOPE,
)
from app.db import turso_http_client

logger = logging.getLogger("s13.cargar_inteligencia")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Carga inteligencia_precios para O'Higgins en un rango de fechas."
    )
    parser.add_argument(
        "--fecha-desde",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="ISO date YYYY-MM-DD. Default: hoy - 90.",
    )
    parser.add_argument(
        "--fecha-hasta",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        help="ISO date YYYY-MM-DD. Default: hoy.",
    )
    parser.add_argument(
        "--lote-id",
        default="manual",
        help="Tag para auditabilidad. Ej: backfill_1, cron_diario, cron_revision_7d.",
    )
    parser.add_argument(
        "--discovery-sample-size",
        type=int,
        default=0,
        help="Codigos NO en seed que se peguen por dia para auto-discovery. "
             "0 para backfill, 25 para cron diario.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=100,
        help="Frecuencia del log [PROGRESO]. Default cada 100 detalles.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="(deprecated; el ingestor usa BATCH_SIZE_PERSIST=50 fijo).",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Logging DEBUG."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Valida config + ticket + acceso Turso, NO ingiere.",
    )
    return parser.parse_args()


def _format_hhmm(seg: float) -> str:
    if seg < 0:
        seg = 0
    m, s = divmod(int(seg), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}"


def _hacer_progress_logger(total_dias: int, eta_baseline_seg_por_detalle: float = 2.4):
    """Crea callback que imprime [PROGRESO] estructurado. ETA se calcula
    asumiendo que los detalles restantes tardan lo mismo que el promedio
    observado en los procesados (mejor que un baseline fijo)."""
    def cb(p: Dict[str, int]) -> None:
        elapsed_s = max(p["elapsed_seg"], 1)
        n_procesados = max(p["n_detalles_pegados"], 1)
        sec_por_detalle = elapsed_s / n_procesados
        # Estimacion grosera: los detalles futuros = (n_total_listados - n_filtrados_no_pegados),
        # pero no sabemos la cantidad total con precision. Usamos progreso por dia:
        proporcion_dias = p["dia_idx"] / max(p["total_dias"], 1)
        if proporcion_dias > 0:
            total_seg_est = elapsed_s / proporcion_dias
            eta_seg = max(total_seg_est - elapsed_s, 0)
        else:
            eta_seg = elapsed_s * (p["total_dias"] - p["dia_idx"])

        sys.stdout.write(
            f"[PROGRESO] Lote {p['lote_id']} | "
            f"dia {p['dia_idx']}/{p['total_dias']} ({p['fecha_actual']}) | "
            f"detalles procesados: {p['n_detalles_pegados']} | "
            f"items categorizados: {p['n_items_categorizados']} | "
            f"tiempo transcurrido: {_format_hhmm(elapsed_s)} | "
            f"eta restante: {_format_hhmm(eta_seg)}\n"
        )
        sys.stdout.flush()
    return cb


def _print_stats_final(stats: StatsCorrida) -> None:
    print()
    print("=" * 60)
    print("STATS FINALES")
    print("=" * 60)
    print(f"Rango:                  {stats.fecha_desde} .. {stats.fecha_hasta}")
    print(f"Dias procesados:        {stats.dias_procesados}")
    print(f"Listados nacionales:    {stats.n_listados_total}")
    print(f"Filtrados por unit:     {stats.n_filtrados_por_unit}")
    print(f"Detalles pegados:       {stats.n_detalles_pegados}")
    print(f"Descartados no-O'Higg:  {stats.n_descartados_no_ohiggins}")
    print(f"Descartados por tipo:   {stats.n_descartados_tipo}")
    print(f"Descartados sin items:  {stats.n_descartados_sin_items}")
    print(f"Items categorizados:    {stats.n_items_categorizados}")
    print(f"Lotes persistidos:      {stats.n_lotes_persistidos}")
    print(f"Organismos descubiertos: {stats.n_organismos_descubiertos}")
    print(f"Tiempo total:           {_format_hhmm(stats.tiempo_total_seg)}")
    print()
    print("Distribucion por linea_aidu:")
    for linea, n in sorted(stats.distribucion_por_linea.items()):
        print(f"  {linea:15s}  {n}")
    print()
    print("Distribucion por tipo_objeto:")
    for tipo_, n in sorted(stats.distribucion_por_tipo.items()):
        print(f"  {tipo_:15s}  {n}")


def main() -> int:
    args = _parse_args()
    _setup_logging(args.verbose)

    hoy = date.today()
    fecha_hasta = args.fecha_hasta or hoy
    fecha_desde = args.fecha_desde or (fecha_hasta - timedelta(days=90))

    if fecha_desde > fecha_hasta:
        logger.error("fecha-desde > fecha-hasta")
        return 1

    print(f"Lote: {args.lote_id}")
    print(f"Rango: {fecha_desde.isoformat()} .. {fecha_hasta.isoformat()} "
          f"({(fecha_hasta - fecha_desde).days + 1} dias)")
    print(f"Tipos en scope: {TIPOS_SCOPE} (CA fuera por S13.1)")
    print(f"Discovery sample size: {args.discovery_sample_size}")
    print(f"Progreso cada: {args.progress_every} detalles")

    # Pre-checks
    if not turso_http_client.is_configured():
        logger.error(
            "Turso NO configurado. TURSO_DATABASE_URL + TURSO_AUTH_TOKEN "
            "deben estar en env (o st.secrets en Streamlit Cloud)."
        )
        return 1
    from config.settings import get_mp_ticket
    ticket = get_mp_ticket()
    if not ticket or ticket.startswith("tu-ticket"):
        logger.error("MP_TICKET no cargado o placeholder.")
        return 1

    if args.dry_run:
        print()
        print("[DRY-RUN] Config OK. No se ingirio nada.")
        return 0

    total_dias = (fecha_hasta - fecha_desde).days + 1
    progress_cb = _hacer_progress_logger(total_dias)

    try:
        stats = ingerir_rango(
            fecha_desde=fecha_desde,
            fecha_hasta=fecha_hasta,
            lote_id=args.lote_id,
            discovery_sample_size=args.discovery_sample_size,
            progress_callback=progress_cb,
            progress_every=args.progress_every,
        )
    except Exception as e:
        logger.exception("Error inesperado durante la ingestion: %s", e)
        return 3

    _print_stats_final(stats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
