"""
S13.4.2 — Reclasificacion one-shot de inteligencia_precios contra el
diccionario nuevo (6 lineas + Otros, prioridad fija, excluyentes).

Logica:
  1. Carga todas las filas de inteligencia_precios via turso_http_client.
  2. Para cada item: aplica categorizar_linea(producto_descripcion).
  3. Si linea_nueva != linea_actual: UPDATE en batch de 50 con auditoria
     (linea_aidu_anterior, reclasificacion_fecha, reclasificacion_motivo,
     keywords_matched).
  4. Imprime resumen final con matriz de cambios linea_origen -> linea_destino.

Idempotente: re-ejecutar es no-op si la BD ya esta consistente con el
clasificador actual. Verificado en tests/test_reclasificacion_idempotente.py.

Uso (ejecutado desde workflow temporal _chore_reclasificar_lineas.yml):
  python -m scripts.s13_4_2_reclasificar_lineas
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
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.categorizador_aidu_fast import (
    categorizar_linea,
    cargar_catalogo_desde_csv,
    reset_cache,
    set_catalogo,
)
from app.db import turso_http_client
from app.db._hrana_types import arg_for_value

logger = logging.getLogger("s13.4.2.reclasificar")

BATCH_SIZE = 50
CSV_PATH = Path(__file__).resolve().parents[1] / "config" / "keywords_aidu_fast.csv"
MOTIVO = "S13.4.2: refactor a prioridad fija + lineas Salud + Construccion"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def main() -> int:
    _setup_logging()
    print("=" * 60)
    print("S13.4.2 - Reclasificacion de inteligencia_precios")
    print("=" * 60)

    if not turso_http_client.is_configured():
        print("ERROR: TURSO_DATABASE_URL + TURSO_AUTH_TOKEN no configurados")
        return 2

    # Cargar catalogo del CSV (source of truth + tabla SQL ya re-poblada
    # por mig 011). El runner aplica migraciones primero asi que tabla
    # y CSV estan en sync.
    reset_cache()
    set_catalogo(cargar_catalogo_desde_csv(CSV_PATH))

    # 1. SELECT todos los items
    print("Leyendo inteligencia_precios...")
    rows = turso_http_client.query_all(
        "SELECT id_item, producto_descripcion, linea_aidu FROM inteligencia_precios"
    )
    n_total = len(rows)
    print(f"  Total items: {n_total}")
    if n_total == 0:
        print("  Tabla vacia. Nada que reclasificar.")
        return 0

    # 2. Calcular cambios en memoria
    cambios = []  # list of (id_item, linea_anterior, linea_nueva, kws_matched)
    matriz = defaultdict(int)  # (origen, destino) -> n
    for row in rows:
        id_item = row[0]
        descripcion = row[1] or ""
        linea_actual = row[2] or "Otros"
        linea_nueva, kws = categorizar_linea(descripcion)
        if linea_nueva != linea_actual:
            cambios.append((id_item, linea_actual, linea_nueva, ",".join(kws)))
            matriz[(linea_actual, linea_nueva)] += 1

    n_cambios = len(cambios)
    print(f"  Items a reclasificar: {n_cambios}")
    print(f"  Items que NO cambian: {n_total - n_cambios}")

    # 3. Matriz origen -> destino
    print()
    print("Matriz de cambios (origen -> destino):")
    print(f"  {'Origen':25s} -> {'Destino':30s} {'N':>5}")
    print("  " + "-" * 65)
    for (origen, destino), n in sorted(matriz.items(), key=lambda x: -x[1]):
        print(f"  {origen:25s} -> {destino:30s} {n:5d}")

    if n_cambios == 0:
        print()
        print("OK: BD ya consistente con clasificador actual (idempotente).")
        return 0

    # 4. UPDATEs en batches de 50
    print()
    print(f"Aplicando UPDATEs en batches de {BATCH_SIZE}...")
    ahora = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    sql = (
        "UPDATE inteligencia_precios SET "
        "  linea_aidu = ?, "
        "  linea_aidu_anterior = ?, "
        "  reclasificacion_fecha = ?, "
        "  reclasificacion_motivo = ?, "
        "  keywords_matched = ? "
        "WHERE id_item = ?"
    )
    n_persistidos = 0
    for i in range(0, n_cambios, BATCH_SIZE):
        batch = cambios[i : i + BATCH_SIZE]
        statements = []
        for id_item, linea_ant, linea_new, kws_str in batch:
            args = [arg_for_value(v) for v in (
                linea_new, linea_ant, ahora, MOTIVO, kws_str, id_item,
            )]
            statements.append({"sql": sql, "args": args})
        try:
            turso_http_client.execute_pipeline(statements, timeout=60.0)
        except Exception as e:
            print(f"  ERROR en batch {i // BATCH_SIZE + 1}: {e}")
            return 3
        n_persistidos += len(batch)
        print(f"  Batch {i // BATCH_SIZE + 1}: +{len(batch)} cambios "
              f"(total {n_persistidos}/{n_cambios})")

    # 5. Resumen final
    print()
    print("=" * 60)
    print("RESUMEN")
    print("=" * 60)
    print(f"Total items procesados:   {n_total}")
    print(f"Items reclasificados:     {n_persistidos}")
    print(f"Items sin cambio:         {n_total - n_persistidos}")
    print()

    # Distribucion final por linea (re-leemos para verificar)
    print("Distribucion final por linea:")
    final_rows = turso_http_client.query_all(
        "SELECT linea_aidu, COUNT(*) AS n FROM inteligencia_precios "
        "GROUP BY linea_aidu ORDER BY n DESC"
    )
    for r in final_rows:
        print(f"  {r[0]!r:35s} {r[1]:5d}")

    print()
    print("OK: reclasificacion completa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
