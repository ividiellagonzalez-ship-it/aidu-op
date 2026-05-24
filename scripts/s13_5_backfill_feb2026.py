"""S13.5 - Backfill Febrero 2026 en O'Higgins (TEMPORAL, one-shot).

Modo backfill: usa Claude API para clasificacion semantica desde el
origen, NO requiere reclasificacion post-hoc. Es el PRIMER sprint de la
serie S13.5 .. S13.14 de backfill mensual hacia atras hasta mayo 2025.

Idempotente por codigo_mp: SELECT bulk al inicio del set de codigos ya
en BD (+/- 30 dias de buffer sobre el rango). Re-dispatchar el workflow
varias veces converge al mismo estado final SIN re-pagar Claude.

Cost guard: $3 USD. Si la proyeccion supera el tope, aborta con exit 4
y persiste lo procesado (idempotencia hace que el proximo run continue).

Persistencia incremental: cada 50 items se flushea a Turso. Patron
heredado de S13.4.3.1 (un timeout intermedio NO pierde trabajo ya pagado).

USO
---
    python -m scripts.s13_5_backfill_feb2026

EXIT CODES
----------
    0: OK
    1: error de configuracion (Turso / MP_TICKET / ANTHROPIC_API_KEY)
    3: error inesperado en la ingestion
    4: cost guard activado, run abortado por proyeccion > $3 USD
"""
from __future__ import annotations

import io
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _setup_utf8_stdout() -> None:
    """TD-01: en Windows / CI cp1252 envolver stdout en UTF-8."""
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def _format_hhmm(seg: float) -> str:
    if seg < 0:
        seg = 0
    m, s = divmod(int(seg), 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}"


# Parametros del sprint S13.5 (hardcoded, NO CLI args para evitar drift
# operacional entre sprints encadenados S13.6 .. S13.14).
FECHA_DESDE = date(2026, 2, 1)
FECHA_HASTA = date(2026, 2, 28)
LOTE_ID = "backfill_feb2026"
COST_GUARD_MAX_USD = 3.0
REGION_NOMBRE = "O'Higgins"
REGION_CODIGO_INFO = "VI"  # solo informativo en logs; la API MP no acepta filtro


def main() -> int:
    _setup_utf8_stdout()
    _setup_logging()

    # Imports diferidos para que setup_utf8 corra primero.
    from app.core.ingesta_inteligencia_precios import ingerir_rango
    from app.db import turso_http_client
    from config.settings import get_mp_ticket
    import os

    print("=" * 60)
    print(f"S13.5 - Backfill {FECHA_DESDE.isoformat()} a {FECHA_HASTA.isoformat()}")
    print(f"Region: {REGION_NOMBRE} (codigo info: {REGION_CODIGO_INFO})")
    print(f"Lote ID: {LOTE_ID}")
    print(f"Cost guard: ${COST_GUARD_MAX_USD:.2f} USD")
    print(f"Modo: SEMANTICO (Claude API) + IDEMPOTENTE por codigo_mp")
    print("=" * 60)

    # Pre-checks de config.
    if not turso_http_client.is_configured():
        print("ERROR: TURSO_DATABASE_URL + TURSO_AUTH_TOKEN no configurados.",
              file=sys.stderr)
        return 1
    ticket = get_mp_ticket()
    if not ticket or ticket.startswith("tu-ticket"):
        print("ERROR: MP_TICKET no cargado o placeholder.", file=sys.stderr)
        return 1
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY no configurada (necesaria para modo semantico).",
              file=sys.stderr)
        return 1

    # Aplicar migraciones a Turso defensivamente (mismo patron que el workflow
    # de backfill por lotes y el cron diario).
    try:
        from app.db.migrator import run_migrations
        n, applied = run_migrations()
        print(f"Migraciones aplicadas: {n}")
        for m in applied:
            print(f"  - {m}")
    except Exception as e:
        print(f"WARNING: run_migrations() fallo: {e} (continuamos por defensa).")

    # Progreso simple sin formato structurado (no necesitamos [PROGRESO] del
    # cron; aca el workflow imprime stats al cierre).
    def _progress(p):
        print(f"  [dia {p['dia_idx']}/{p['total_dias']} {p['fecha_actual']}] "
              f"detalles={p['n_detalles_pegados']} items={p['n_items_categorizados']} "
              f"elapsed={_format_hhmm(p['elapsed_seg'])}")

    try:
        stats = ingerir_rango(
            fecha_desde=FECHA_DESDE,
            fecha_hasta=FECHA_HASTA,
            lote_id=LOTE_ID,
            discovery_sample_size=0,        # backfill: NO discovery (estable)
            usar_semantico=True,            # Claude API desde el origen
            cost_guard_max_usd=COST_GUARD_MAX_USD,
            codigos_existentes_buffer_days=30,
            progress_callback=_progress,
            progress_every=50,
        )
    except Exception as e:
        logging.exception("Error inesperado durante la ingesta: %s", e)
        return 3

    # Reporte final estructurado (5 ajustes finos del Director).
    print()
    print("=" * 60)
    print("STATS FINALES S13.5")
    print("=" * 60)
    n_listados = stats.n_listados_total
    n_filtrados = stats.n_filtrados_por_unit
    ratio_cobertura = (n_filtrados / n_listados) if n_listados else 0.0
    print(f"Rango:                  {stats.fecha_desde} .. {stats.fecha_hasta}")
    print(f"Dias procesados:        {stats.dias_procesados}")
    print(f"n_listados (API MP):    {n_listados}")
    print(f"n_filtrados (unit_code): {n_filtrados}")
    print(f"n_skip_idempotente:     {stats.n_skip_idempotente}")
    print(f"n_detalles_pegados:     {stats.n_detalles_pegados}")
    print(f"n_procesados (items):   {stats.n_items_categorizados}")
    print(f"n_llamadas_semanticas:  {stats.n_llamadas_semanticas}")
    print(f"costo_claude_usd:       ${stats.costo_claude_usd:.3f}")
    print(f"ratio_cobertura:        {ratio_cobertura:.3f} "
          f"(filtrados/listados — alerta TD-05 si <0.50 del baseline)")
    print(f"tiempo_total:           {_format_hhmm(stats.tiempo_total_seg)}")
    print()
    print("Distribucion por linea_aidu:")
    for linea, n in sorted(stats.distribucion_por_linea.items(),
                            key=lambda kv: -kv[1]):
        print(f"  {linea:30s}  {n}")
    print()
    print("Distribucion por tipo_objeto:")
    for tipo_, n in sorted(stats.distribucion_por_tipo.items()):
        print(f"  {tipo_:15s}  {n}")

    if stats.aborted_cost_guard:
        print()
        print(f"COST GUARD ACTIVADO: corrida abortada por proyeccion > "
              f"${COST_GUARD_MAX_USD:.2f} USD. Items procesados ya estan "
              f"persistidos. Re-dispatchar el workflow continua donde quedo "
              f"(idempotencia por codigo_mp).")
        return 4

    print()
    print("OK: backfill febrero 2026 completo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
