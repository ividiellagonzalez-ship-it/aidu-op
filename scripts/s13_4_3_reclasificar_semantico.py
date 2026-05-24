"""
S13.4.3 - Re-clasificacion semantica one-shot via Claude API.

Lee los ~685 items de inteligencia_precios desde Turso, llama a Claude
para cada uno, hace UPDATE en batches de 50.

Rate limit: max 5 req/s (mas conservador que el limite de Claude API).
Backoff exponencial 1s/4s/16s ante 429.

Costo estimado: ~$1.64 USD para 685 items con sonnet-4-5.

Idempotente: re-correr el script clasifica de nuevo, pero como sobreescribe
linea_aidu/confidence_score, el segundo run puede dar resultados levemente
distintos por variabilidad del modelo. El script siempre actualiza el
campo `reclasificacion_fecha` para que la auditoria sea clara.
"""
# Fix TD-01 (UTF-8 wrapper).
import sys
import io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import logging
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

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
COST_PROYECTADO_MAX_USD = 5.0  # tope per directiva Director
CSV_PATH = Path(__file__).resolve().parents[1] / "config" / "keywords_aidu_fast.csv"
MOTIVO = "S13.4.3: clasificador semantico via Claude API"

# Cost approximation: sonnet-4-5 ~ $3/Mtok input, $15/Mtok output.
# Prompt ~ 450 tokens + 200 max output = ~650 tokens/llamada.
# Cost por item ~ (450*3 + 200*15) / 1M = $0.00435 ... corrigiendo:
# ($3 * 450 + $15 * 200) / 1e6 = $1350/1e6 + $3000/1e6 = $0.00135 + $0.003 = $0.00435 input+output mezclado
# En realidad input y output van separados:
# input cost = 450 / 1M * $3 = $0.00135
# output cost = 150 (avg) / 1M * $15 = $0.00225
# total per llamada ~ $0.0036; *685 = $2.46 (peor caso)
# La estimacion del spec ($1.64) asume output 100 tok promedio.
COST_INPUT_PER_MTOK = 3.0  # USD per million tokens
COST_OUTPUT_PER_MTOK = 15.0


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def _estimar_costo_acumulado(n_calls: int, prompt_tokens_avg: int = 450,
                             output_tokens_avg: int = 120) -> float:
    """Costo proyectado para N llamadas con sonnet-4-5."""
    input_cost = (prompt_tokens_avg * n_calls / 1_000_000.0) * COST_INPUT_PER_MTOK
    output_cost = (output_tokens_avg * n_calls / 1_000_000.0) * COST_OUTPUT_PER_MTOK
    return input_cost + output_cost


def main() -> int:
    _setup_logging()
    print("=" * 60)
    print("S13.4.3 - Reclasificacion semantica via Claude API")
    print("=" * 60)

    if not turso_http_client.is_configured():
        print("ERROR: TURSO_DATABASE_URL + TURSO_AUTH_TOKEN no configurados")
        return 2

    # Pre-cargar catalogo lexical (fallback si Claude API falla mid-run).
    reset_cache()
    set_catalogo(cargar_catalogo_desde_csv(CSV_PATH))

    # 1. SELECT items a clasificar
    print("Leyendo inteligencia_precios...")
    rows = turso_http_client.query_all(
        "SELECT id_item, producto_descripcion, organismo_comprador, linea_aidu "
        "FROM inteligencia_precios ORDER BY id_item"
    )
    n_total = len(rows)
    print(f"  Total items: {n_total}")
    if n_total == 0:
        print("  Tabla vacia. Nada que clasificar.")
        return 0

    # 2. Iterar con rate limit + cost guard
    cambios: list = []  # (id, prev_linea, new_linea, granular, conf, razon)
    matriz: Counter = Counter()
    confidence_buckets = Counter({"alta": 0, "media": 0, "baja": 0})
    granular_count = Counter({"true": 0, "false": 0, "null": 0})
    metodo_count = Counter({"semantic": 0, "keyword": 0})

    n_fallidos_api = 0
    last_req_t = 0.0
    print("\nClasificando via Claude (rate limit 5 req/s)...")
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

        # Llamada con backoff manual + fallback lexical
        resultado = None
        try:
            resultado = clasificar_via_claude(descripcion, organismo)
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

        cambios.append((
            id_item, linea_actual, nueva_linea, g, conf,
            resultado.get("razon", ""), metodo_count["semantic"] > metodo_count["keyword"],
        ))

        # Cost guard: cada 50 items proyectamos
        if i % 50 == 0:
            costo_acumulado = _estimar_costo_acumulado(i)
            proyectado_total = costo_acumulado * (n_total / i)
            print(f"  [{i}/{n_total}] costo estimado acumulado=${costo_acumulado:.3f} "
                  f"proyectado total=${proyectado_total:.3f}")
            if proyectado_total > COST_PROYECTADO_MAX_USD:
                print(f"ABORT: costo proyectado ${proyectado_total:.2f} supera el "
                      f"tope ${COST_PROYECTADO_MAX_USD:.2f}.")
                return 4

    print(f"\nClasificacion completa: {n_total} items, "
          f"{n_fallidos_api} fallidos (fallback lexical).")
    costo_real_estimado = _estimar_costo_acumulado(metodo_count["semantic"])
    print(f"Costo Claude API estimado: ${costo_real_estimado:.3f} USD "
          f"({metodo_count['semantic']} llamadas semantic + "
          f"{metodo_count['keyword']} keyword)")

    # 3. UPDATE en batches
    print("\nAplicando UPDATEs en batches de 50...")
    ahora = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    sql = (
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
    n_persistidos = 0
    for i in range(0, len(cambios), BATCH_SIZE):
        batch = cambios[i:i + BATCH_SIZE]
        statements = []
        for id_item, prev_linea, new_linea, g, conf, razon, was_semantic in batch:
            granular_db = (1 if g is True else 0 if g is False else None)
            metodo = "semantic" if was_semantic else "keyword"
            args = [arg_for_value(v) for v in (
                new_linea, prev_linea, granular_db, conf, metodo,
                ahora, f"{MOTIVO}; {razon[:200]}",
                id_item,
            )]
            statements.append({"sql": sql, "args": args})
        try:
            turso_http_client.execute_pipeline(statements, timeout=60.0)
        except Exception as e:
            print(f"  ERROR en batch {i // BATCH_SIZE + 1}: {e}")
            return 3
        n_persistidos += len(batch)
        print(f"  Batch {i // BATCH_SIZE + 1}: +{len(batch)} (total {n_persistidos})")

    # 4. Resumen final
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

    # Distribucion final por linea
    print("\nDistribucion final por linea (desde Turso):")
    final = turso_http_client.query_all(
        "SELECT linea_aidu, COUNT(*) FROM inteligencia_precios "
        "GROUP BY linea_aidu ORDER BY COUNT(*) DESC"
    )
    for r in final:
        print(f"  {r[0]!r:35s} {r[1]:5d}")

    print("\nOK: reclasificacion semantica completa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
