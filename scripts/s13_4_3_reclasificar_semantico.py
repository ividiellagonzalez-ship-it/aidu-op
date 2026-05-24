"""
S13.4.3 - Re-clasificacion semantica one-shot via Claude API.

S13.4.3.1 (robustez):
  - Persistencia INCREMENTAL: UPDATEs se flushean a Turso CADA BATCH_SIZE
    items procesados, no al final. Asi un timeout intermedio (como el
    Run 26365347283 que se cancelo a 600/685) no pierde trabajo.
  - Idempotente: el SELECT inicial salta items que ya tienen
    `clasificacion_metodo = 'semantic'`. Re-disparar el workflow continua
    desde donde quedo. Override con `--force` para reclasificar todo.
  - TIMEOUT del workflow aumentado a 60min con margen de seguridad.

Lee los items pendientes de inteligencia_precios desde Turso, llama a
Claude para cada uno, y hace UPDATE incremental.

Rate limit: max 5 req/s. Backoff exponencial implicito del SDK.
Costo estimado: ~$1.64-$2.00 USD para 685 items con sonnet-4-5.
Tope hard: $5 USD (aborta con exit 4 si proyeccion supera).
"""
import sys
import io

import argparse
import logging
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.claude_client import ClaudeApiUnavailableError
from app.core.categorizador_aidu_fast import (
    cargar_catalogo_desde_csv,
    reset_cache,
    set_catalogo,
    categorizar_linea,
)
from app.core.clasificador_semantico import clasificar_via_claude
from app.db import turso_http_client
from app.db._hrana_types import arg_for_value

logger = logging.getLogger("s13.4.3.reclasificar")

BATCH_SIZE = 50
RATE_LIMIT_REQ_PER_SEC = 5.0
MIN_INTERVAL_S = 1.0 / RATE_LIMIT_REQ_PER_SEC
COST_PROYECTADO_MAX_USD = 5.0
CSV_PATH = Path(__file__).resolve().parents[1] / "config" / "keywords_aidu_fast.csv"
MOTIVO = "S13.4.3: clasificador semantico via Claude API"

# Cost approximation: sonnet-4-5 ~ $3/Mtok input, $15/Mtok output.
COST_INPUT_PER_MTOK = 3.0
COST_OUTPUT_PER_MTOK = 15.0

# SQL UPDATE - definido una sola vez, reusado en cada flush.
_UPDATE_SQL = (
    "UPDATE inteligencia_precios SET "
    "  linea_aidu = ?, "
    "  linea_aidu_anterior = ?, "
    "  es_producto_granular = ?, "
    "  confidence_score = ?, "
    "  clasificacion_metodo = ?, "
    "  reclasificacion_fecha = ?, "
    "  reclasificacion_motivo = ? "
    "WHERE id_item = ?"
)

# Tupla de cambio: (id, prev_linea, new_linea, granular, conf, razon, metodo)
Cambio = Tuple[int, str, str, object, float, str, str]


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def _setup_utf8_stdout() -> None:
    """TD-01: en Windows / CI cp1252 envuelve stdout en UTF-8 para no
    crashear con tildes y emoji. Llamado solo desde main() para no
    romper la captura de stdout de pytest cuando se importa el modulo."""
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def _estimar_costo_acumulado(n_calls: int, prompt_tokens_avg: int = 450,
                             output_tokens_avg: int = 120) -> float:
    input_cost = (prompt_tokens_avg * n_calls / 1_000_000.0) * COST_INPUT_PER_MTOK
    output_cost = (output_tokens_avg * n_calls / 1_000_000.0) * COST_OUTPUT_PER_MTOK
    return input_cost + output_cost


def _flush_batch(cambios: List[Cambio], ahora: str) -> int:
    """Aplica un batch de UPDATEs a Turso via execute_pipeline.

    Devuelve la cantidad de statements enviados. Si falla, propaga la
    excepcion al caller (caller decide si abortar o continuar — en este
    script abortamos para no quedar con estado inconsistente entre Turso
    y los logs).
    """
    if not cambios:
        return 0
    statements = []
    for id_item, prev_linea, new_linea, g, conf, razon, metodo in cambios:
        granular_db = (1 if g is True else 0 if g is False else None)
        args = [arg_for_value(v) for v in (
            new_linea, prev_linea, granular_db, conf, metodo,
            ahora, f"{MOTIVO}; {razon[:200]}",
            id_item,
        )]
        statements.append({"sql": _UPDATE_SQL, "args": args})
    turso_http_client.execute_pipeline(statements, timeout=60.0)
    return len(statements)


def _leer_pendientes(force: bool) -> List:
    """Devuelve los items a procesar. Default: solo los que aun no fueron
    clasificados semanticamente. Con --force: TODOS los items.

    El filtro `clasificacion_metodo IS NULL OR clasificacion_metodo !=
    'semantic'` permite re-correr el script tras un timeout intermedio
    sin re-procesar items que ya quedaron en Turso con metodo='semantic'.
    """
    if force:
        sql = (
            "SELECT id_item, producto_descripcion, organismo_comprador, linea_aidu "
            "FROM inteligencia_precios ORDER BY id_item"
        )
    else:
        sql = (
            "SELECT id_item, producto_descripcion, organismo_comprador, linea_aidu "
            "FROM inteligencia_precios "
            "WHERE clasificacion_metodo IS NULL OR clasificacion_metodo != 'semantic' "
            "ORDER BY id_item"
        )
    return turso_http_client.query_all(sql)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reclasificacion semantica via Claude API (S13.4.3)"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-clasifica TODOS los items, ignorando clasificacion_metodo "
             "previa. Por defecto solo se procesan items que aun no fueron "
             "clasificados semanticamente (idempotencia post-timeout).",
    )
    args = parser.parse_args()

    _setup_utf8_stdout()
    _setup_logging()
    print("=" * 60)
    print("S13.4.3 - Reclasificacion semantica via Claude API")
    if args.force:
        print("MODO: --force (reclasifica TODOS los items)")
    else:
        print("MODO: incremental (solo items no clasificados semanticamente)")
    print("=" * 60)

    if not turso_http_client.is_configured():
        print("ERROR: TURSO_DATABASE_URL + TURSO_AUTH_TOKEN no configurados")
        return 2

    # Pre-cargar catalogo lexical (fallback si Claude API falla mid-run).
    reset_cache()
    set_catalogo(cargar_catalogo_desde_csv(CSV_PATH))

    # 1. SELECT items a clasificar (con filtro de idempotencia por defecto)
    print("Leyendo inteligencia_precios...")
    rows = _leer_pendientes(args.force)
    n_total = len(rows)
    print(f"  Items pendientes: {n_total}")
    if n_total == 0:
        print("  Nada que clasificar. Todos los items ya tienen "
              "clasificacion_metodo='semantic'. Use --force para reclasificar.")
        return 0

    # 2. Iterar: clasificar + UPDATEs incrementales cada BATCH_SIZE
    matriz: Counter = Counter()
    confidence_buckets = Counter({"alta": 0, "media": 0, "baja": 0})
    granular_count = Counter({"true": 0, "false": 0, "null": 0})
    metodo_count = Counter({"semantic": 0, "keyword": 0})

    cambios_pendientes: List[Cambio] = []
    n_persistidos = 0
    n_fallidos_api = 0
    last_req_t = 0.0
    ahora = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    print(f"\nClasificando + persistiendo cada {BATCH_SIZE} items "
          f"(rate limit {RATE_LIMIT_REQ_PER_SEC} req/s)...")
    for i, row in enumerate(rows, start=1):
        id_item = row[0]
        descripcion = row[1] or ""
        organismo = row[2] or ""
        linea_actual = row[3] or "Otros"

        # Rate limit
        elapsed = time.time() - last_req_t
        if elapsed < MIN_INTERVAL_S:
            time.sleep(MIN_INTERVAL_S - elapsed)
        last_req_t = time.time()

        # Clasificacion con fallback lexical individual
        try:
            resultado = clasificar_via_claude(descripcion, organismo)
            metodo = "semantic"
            metodo_count["semantic"] += 1
        except ClaudeApiUnavailableError as e:
            n_fallidos_api += 1
            logger.warning("item %s: Claude fallo (%s), fallback lexical", id_item, e)
            linea_lex, _ = categorizar_linea(descripcion)
            resultado = {
                "linea": linea_lex,
                "es_producto_granular": None,
                "confidence": 0.0,
                "razon": "fallback lexical por fallo API",
            }
            metodo = "keyword"
            metodo_count["keyword"] += 1

        # Buckets de confidence
        conf = float(resultado.get("confidence", 0.0))
        if conf >= 0.8:
            confidence_buckets["alta"] += 1
        elif conf >= 0.5:
            confidence_buckets["media"] += 1
        else:
            confidence_buckets["baja"] += 1

        # Granular distribution
        g = resultado.get("es_producto_granular")
        if g is True:
            granular_count["true"] += 1
        elif g is False:
            granular_count["false"] += 1
        else:
            granular_count["null"] += 1

        nueva_linea = resultado.get("linea", linea_actual)
        if nueva_linea != linea_actual:
            matriz[(linea_actual, nueva_linea)] += 1

        cambios_pendientes.append((
            id_item, linea_actual, nueva_linea, g, conf,
            resultado.get("razon", ""), metodo,
        ))

        # Flush incremental cada BATCH_SIZE items
        if len(cambios_pendientes) >= BATCH_SIZE:
            try:
                _flush_batch(cambios_pendientes, ahora)
            except Exception as e:
                print(f"  ERROR en flush a item {i}: {e}")
                # Si llegamos aca con cambios sin persistir, los items
                # quedan en la BD sin metodo='semantic' y la proxima
                # corrida los reintenta automaticamente (gracias a la
                # idempotencia del SELECT). Abortamos con exit 3.
                return 3
            n_persistidos += len(cambios_pendientes)
            print(f"  [{i}/{n_total}] flush +{len(cambios_pendientes)} "
                  f"(total persistido {n_persistidos})")
            cambios_pendientes.clear()

        # Cost guard cada 50 items
        if i % 50 == 0:
            costo_acumulado = _estimar_costo_acumulado(metodo_count["semantic"])
            proyectado_total = costo_acumulado * (n_total / max(i, 1))
            print(f"  [{i}/{n_total}] costo estimado acumulado=${costo_acumulado:.3f} "
                  f"proyectado total=${proyectado_total:.3f}")
            if proyectado_total > COST_PROYECTADO_MAX_USD:
                # Flush lo pendiente antes de abortar para no perder
                # trabajo ya pagado.
                if cambios_pendientes:
                    try:
                        _flush_batch(cambios_pendientes, ahora)
                        n_persistidos += len(cambios_pendientes)
                    except Exception:
                        pass
                print(f"ABORT: costo proyectado ${proyectado_total:.2f} supera el "
                      f"tope ${COST_PROYECTADO_MAX_USD:.2f}. "
                      f"Items persistidos hasta aqui: {n_persistidos}.")
                return 4

    # Flush remanente al cierre del loop
    if cambios_pendientes:
        try:
            _flush_batch(cambios_pendientes, ahora)
        except Exception as e:
            print(f"  ERROR en flush final: {e}")
            return 3
        n_persistidos += len(cambios_pendientes)
        print(f"  Flush final: +{len(cambios_pendientes)} (total {n_persistidos})")
        cambios_pendientes.clear()

    print(f"\nClasificacion completa: {n_total} items procesados, "
          f"{n_persistidos} persistidos, {n_fallidos_api} fallidos API.")
    costo_real_estimado = _estimar_costo_acumulado(metodo_count["semantic"])
    print(f"Costo Claude API estimado: ${costo_real_estimado:.3f} USD "
          f"({metodo_count['semantic']} llamadas semantic + "
          f"{metodo_count['keyword']} keyword)")

    # 3. Resumen final
    print()
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Items procesados:           {n_total}")
    print(f"Items con UPDATE:           {n_persistidos}")
    print(f"Llamadas semanticas OK:     {metodo_count['semantic']}")
    print(f"Fallback lexical (API):     {metodo_count['keyword']}")
    print(f"Costo Claude API estimado:  ${costo_real_estimado:.3f} USD")
    print()
    print("Distribucion confidence_score:")
    for bucket, n in sorted(confidence_buckets.items()):
        pct = 100.0 * n / max(n_total, 1)
        print(f"  {bucket:8s}  {n:5d}  ({pct:.1f}%)")
    print()
    print("Distribucion es_producto_granular:")
    for k, n in sorted(granular_count.items()):
        pct = 100.0 * n / max(n_total, 1)
        print(f"  {k:8s}  {n:5d}  ({pct:.1f}%)")
    print()
    print("Matriz de cambios (top 20 origen->destino):")
    for (origen, destino), n in matriz.most_common(20):
        print(f"  {origen:30s} -> {destino:30s}  {n:4d}")

    print("\nDistribucion final por linea (desde Turso):")
    final = turso_http_client.query_all(
        "SELECT linea_aidu, COUNT(*) FROM inteligencia_precios "
        "GROUP BY linea_aidu ORDER BY COUNT(*) DESC"
    )
    for r in final:
        # Defensive: Turso/Hrana devuelve COUNT(*) como string. Coerce
        # explicitamente a int antes del format spec :d (mismo patron que
        # _safe_int en app/ui/inteligencia_mercado.py).
        try:
            count_int = int(r[1])
        except (TypeError, ValueError):
            count_int = 0
        print(f"  {r[0]!r:35s} {count_int:5d}")

    print("\nOK: reclasificacion semantica completa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
