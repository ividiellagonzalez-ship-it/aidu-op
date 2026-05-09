"""
docs/migracion_inicial_turso.py
================================
Bootstrap one-shot S12.1.5: aplica el schema completo y vuelca el estado
inicial de datos hacia la BD remota Turso. Correr UNA SOLA VEZ post-merge.

Pre-requisitos:
- TURSO_DATABASE_URL y TURSO_AUTH_TOKEN como variables de entorno.
- requirements.txt instalado (incluye `requests`).
- Estar en la raíz del repo (las migraciones se leen de app/db/migrations/
  y la BD semilla de data_semilla/aidu_op.db).

Uso (PowerShell):
    $env:TURSO_DATABASE_URL = "libsql://aidu-op-prod-...turso.io"
    $env:TURSO_AUTH_TOKEN = "<token desde Streamlit Secrets>"
    python docs/migracion_inicial_turso.py

El script es idempotente:
- DDL: tolera 'already exists' / 'duplicate column' (relanzable sin daño).
- Datos: skipea cualquier tabla que ya tenga >0 filas en Turso.
- _migrations: usa INSERT OR IGNORE (filename UNIQUE).

Importa SEED_HOMOLOGACION desde app/core/homologacion.py (fuente canónica de
las 12 categorías AIDU). Esto cubre una brecha de la planificación original:
las 12 filas de aidu_homologacion_categoria no viven en data_semilla ni en
las migraciones, sino como constante en código. Se documenta como decisión
en el PR description.
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = REPO / "app" / "db" / "migrations"
SEED_DB = REPO / "data_semilla" / "aidu_op.db"

# Conteos esperados según criterio #2 del sprint S12.1.5
EXPECTED_COUNTS = {
    "mp_licitaciones_adj": 19,
    "aidu_homologacion_categoria": 12,
    "aidu_proyectos": 4,
}

TOLERABLE_ERRORS = ("already exists", "duplicate column name")
BATCH_SIZE = 50  # tamaño de batch para INSERTs masivos


# ============================================================
# Cliente HTTP /v2/pipeline
# ============================================================
def _endpoint() -> tuple[str, dict]:
    url = (os.environ.get("TURSO_DATABASE_URL") or "").strip()
    token = (os.environ.get("TURSO_AUTH_TOKEN") or "").strip()
    if not url or not token:
        sys.exit("❌ Faltan TURSO_DATABASE_URL o TURSO_AUTH_TOKEN en el entorno.")
    http_url = url.replace("libsql://", "https://", 1).rstrip("/") + "/v2/pipeline"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return http_url, headers


def _arg(value) -> dict:
    """
    Convierte un valor Python al formato {type, value} del protocolo Hrana
    (endpoint /v2/pipeline de Turso).

    Cuidado con los tipos JSON: el protocolo es estricto.
    - integer: `value` debe ser STRING (decimal). JSON no representa int64
      con precisión y Hrana lo serializa como string para evitar pérdida.
    - float:   `value` debe ser un NÚMERO JSON crudo (NO string). Si se manda
      como string Turso responde HTTP 400 'invalid type: string "1.0",
      expected f64' — bug que motivó S12.1.5.bis.
    - text:    `value` debe ser string.
    - null:    `value` debe ser null.
    - blob:    se envía bajo la clave `base64` (no `value`).
    """
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        # Número JSON crudo, NO string. json.dumps emite 1.0 sin comillas.
        return {"type": "float", "value": value}
    if isinstance(value, (bytes, bytearray)):
        import base64
        return {"type": "blob", "base64": base64.b64encode(bytes(value)).decode()}
    return {"type": "text", "value": str(value)}


def _coerce(value, sqlite_type: str):
    """
    Coerciona el valor Python al tipo afín de la columna SQLite/Turso destino.

    SQLite tiene tipado dinámico flexible: un row con un INTEGER en una columna
    REAL queda almacenado como int. Cuando ese mismo row se envía vía Hrana a
    Turso, va como `{"type":"integer","value":"X"}`, y Turso (más estricto)
    rechaza con HTTP 400 'expected f64'. Esta función normaliza al tipo de
    afinidad declarado en el schema antes de llamar a _arg.

    No coacciona NULL (NULL es válido para cualquier afinidad).
    Si la conversión falla (TypeError/ValueError) devuelve el valor original
    para que el error del servidor sea claro y diagnosticable.
    """
    if value is None:
        return None
    t = (sqlite_type or "").upper()
    if "INT" in t:
        try:
            return int(value)
        except (TypeError, ValueError):
            return value
    if "REAL" in t or "FLOA" in t or "DOUB" in t or "NUM" in t:
        try:
            return float(value)
        except (TypeError, ValueError):
            return value
    if "BLOB" in t:
        if isinstance(value, str):
            return value.encode("utf-8")
        return value
    # TEXT y todo lo demás: dejar como está
    return value


def _execute(http_url, headers, statements: list[dict]) -> list[dict]:
    """Envía una lista de statements en un solo pipeline. Devuelve los results."""
    payload = {
        "requests": [{"type": "execute", "stmt": s} for s in statements]
        + [{"type": "close"}]
    }
    r = requests.post(http_url, headers=headers, json=payload, timeout=120)
    if r.status_code >= 400:
        sys.exit(f"❌ HTTP {r.status_code} desde Turso:\n{r.text[:500]}")
    return r.json().get("results", [])


def _table_count(http_url, headers, table: str) -> int:
    """Devuelve el conteo de la tabla en Turso, o -1 si no existe / falla."""
    res = _execute(http_url, headers, [{"sql": f'SELECT COUNT(*) FROM "{table}"'}])[0]
    if res.get("type") == "ok":
        rows = res["response"]["result"]["rows"]
        return int(rows[0][0]["value"])
    return -1


def _table_exists(http_url, headers, table: str) -> bool:
    res = _execute(http_url, headers, [{
        "sql": "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        "args": [_arg(table)],
    }])[0]
    if res.get("type") == "ok":
        return len(res["response"]["result"]["rows"]) > 0
    return False


def _column_types(http_url, headers, table: str) -> dict:
    """
    Devuelve dict {nombre_columna: tipo_sqlite_upper} para las columnas de la
    tabla en Turso. Usa PRAGMA table_info contra la BD remota. Devuelve {} si
    la tabla no existe o falla la query.

    Necesario para coercer valores antes del INSERT: SQLite acepta tipos
    "afínes" (un INT en columna REAL queda como int), pero Hrana es estricto.
    """
    res = _execute(http_url, headers, [{"sql": f'PRAGMA table_info("{table}")'}])[0]
    if res.get("type") != "ok":
        return {}
    result = res.get("response", {}).get("result", {})
    rows = result.get("rows", [])
    types: dict = {}
    for row in rows:
        # PRAGMA table_info: cid, name, type, notnull, dflt_value, pk
        if len(row) < 3:
            continue
        name_cell = row[1] or {}
        type_cell = row[2] or {}
        name = name_cell.get("value")
        col_type = (type_cell.get("value") or "").upper()
        if name:
            types[name] = col_type
    return types


# ============================================================
# Paso 1: aplicar migraciones a Turso
# ============================================================
def _split_statements(sql_text: str) -> list[str]:
    return [s.strip() for s in sql_text.split(";") if s.strip()]


def _strip_leading_comments(stmt: str) -> str:
    """Quita líneas `--` y vacías al inicio. Sin esto, los chunks 'comentario
    + DDL' se descartan por entero al chequear startswith('--')."""
    lines = stmt.split("\n")
    while lines and (not lines[0].strip() or lines[0].lstrip().startswith("--")):
        lines.pop(0)
    return "\n".join(lines).strip()


def apply_migrations(http_url, headers) -> None:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        sys.exit(f"❌ No se encontraron migraciones en {MIGRATIONS_DIR}")
    print(f"📂 Aplicando {len(files)} migración(es) a Turso...")

    # Asegurar tabla _migrations
    _execute(http_url, headers, [{"sql": """
        CREATE TABLE IF NOT EXISTS _migrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            checksum TEXT,
            description TEXT
        )
    """}])

    for f in files:
        sql_text = f.read_text(encoding="utf-8")
        desc_line = next((l for l in sql_text.splitlines() if l.startswith("-- DESC:")), "")
        description = desc_line.replace("-- DESC:", "").strip() or f.stem

        statements = [_strip_leading_comments(s) for s in _split_statements(sql_text)]
        statements = [s for s in statements if s]
        n_applied = 0
        n_tolerated = 0

        for stmt in statements:
            res = _execute(http_url, headers, [{"sql": stmt}])[0]
            if res.get("type") == "ok":
                n_applied += 1
                continue
            err = res.get("error", {}).get("message", "")
            if any(t in err.lower() for t in TOLERABLE_ERRORS):
                n_tolerated += 1
                continue
            sys.exit(f"❌ Falla en {f.name}:\n   stmt: {stmt[:80]}...\n   error: {err}")

        # Registrar como aplicada (idempotente)
        _execute(http_url, headers, [{
            "sql": "INSERT OR IGNORE INTO _migrations (filename, description) VALUES (?, ?)",
            "args": [_arg(f.name), _arg(description)],
        }])
        print(f"  ✅ {f.name}: {n_applied} aplicadas, {n_tolerated} ya existían")


# ============================================================
# Paso 2: volcar data_semilla → Turso
# ============================================================
SKIP_TABLES = {"_migrations"}  # gestionado por apply_migrations


def _build_dependency_graph(
    http_url, headers, tables: list[str]
) -> dict[str, list[str]]:
    """
    Para cada tabla en `tables`, consulta Turso (PRAGMA foreign_key_list) y
    devuelve {tabla: [tablas_padre_en_scope]}. Solo cuenta como dependencia un
    parent que también esté en `tables` (FKs hacia tablas fuera de scope no
    afectan el orden — por ejemplo si la seed no las trae). Self-references se
    descartan: una FK de la tabla a sí misma no condiciona el orden de carga
    entre filas de tablas distintas.
    """
    table_set = set(tables)
    graph: dict[str, list[str]] = {t: [] for t in tables}
    for tbl in tables:
        res = _execute(http_url, headers, [{"sql": f'PRAGMA foreign_key_list("{tbl}")'}])[0]
        if res.get("type") != "ok":
            continue
        rows = res.get("response", {}).get("result", {}).get("rows", [])
        parents: set[str] = set()
        for row in rows:
            # PRAGMA foreign_key_list cells: id, seq, table, from, to, on_update, on_delete, match
            if len(row) < 3:
                continue
            parent_cell = row[2] or {}
            parent = parent_cell.get("value")
            if parent and parent != tbl and parent in table_set:
                parents.add(parent)
        graph[tbl] = sorted(parents)
    return graph


def _topological_sort(graph: dict[str, list[str]]) -> list[str]:
    """
    Orden topológico (Kahn) con tie-break alfabético para determinismo. La
    entrada es {hijo: [padres]}; la salida es una lista en la que cada padre
    aparece antes que sus hijos. Lanza ValueError si detecta un ciclo.
    """
    from bisect import insort
    from collections import defaultdict

    in_degree: dict[str, int] = {t: len(graph.get(t, [])) for t in graph}
    children: dict[str, list[str]] = defaultdict(list)
    for child, parents in graph.items():
        for p in parents:
            children[p].append(child)

    ready = sorted([t for t, d in in_degree.items() if d == 0])
    order: list[str] = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for ch in sorted(children[node]):
            in_degree[ch] -= 1
            if in_degree[ch] == 0:
                insort(ready, ch)
    if len(order) != len(graph):
        unresolved = sorted(t for t in graph if t not in order)
        raise ValueError(
            f"Ciclo detectado en grafo de FKs. Tablas sin orden: {unresolved}"
        )
    return order


def dump_seed(http_url, headers) -> None:
    if not SEED_DB.exists():
        print(f"⚠️  No hay {SEED_DB.name}; skipeando dump.")
        return
    print(f"📦 Volcando seed desde {SEED_DB.name} → Turso...")
    conn = sqlite3.connect(SEED_DB)
    conn.row_factory = sqlite3.Row
    try:
        seed_tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()]
        seed_tables = [t for t in seed_tables if t not in SKIP_TABLES]

        # Orden topológico según FKs reales en Turso. Un order alfabético
        # rompe FK constraints (ej: mp_categorizacion_aidu antes que
        # mp_licitaciones_adj). El topo-sort respeta padre→hijo.
        graph = _build_dependency_graph(http_url, headers, seed_tables)
        ordered_tables = _topological_sort(graph)
        deps_summary = ", ".join(
            f"{t}<-[{','.join(graph[t])}]" if graph[t] else t
            for t in ordered_tables
        )
        print(f"  📐 Orden topológico ({len(ordered_tables)} tablas): {deps_summary}")

        for tbl in ordered_tables:
            if not _table_exists(http_url, headers, tbl):
                print(f"  ⏭️  {tbl}: no existe en Turso (no creada por migraciones), skip")
                continue
            n_remote = _table_count(http_url, headers, tbl)
            if n_remote > 0:
                print(f"  ⏭️  {tbl}: ya tiene {n_remote} filas en Turso, skip (idempotencia)")
                continue

            rows = conn.execute(f'SELECT * FROM "{tbl}"').fetchall()
            if not rows:
                print(f"  ➖ {tbl}: 0 filas en seed, skip")
                continue

            cols = list(rows[0].keys())
            col_list = ",".join(f'"{c}"' for c in cols)
            placeholders = ",".join("?" * len(cols))
            sql = f'INSERT INTO "{tbl}" ({col_list}) VALUES ({placeholders})'

            # Tipos de las columnas según el schema en Turso, para coercer
            # los valores Python al tipo afín antes de mandarlos a Hrana.
            col_types = _column_types(http_url, headers, tbl)

            n_total = 0
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                stmts = []
                for row in batch:
                    args = []
                    for col_name, value in zip(cols, row):
                        coerced = _coerce(value, col_types.get(col_name, ""))
                        args.append(_arg(coerced))
                    stmts.append({"sql": sql, "args": args})
                results = _execute(http_url, headers, stmts)
                for j, res in enumerate(results):
                    if res.get("type") == "error":
                        err = res.get("error", {}).get("message", "")
                        sys.exit(f"❌ INSERT en {tbl} (fila {i+j}): {err}")
                n_total += len(batch)
            print(f"  ✅ {tbl}: {n_total} filas insertadas")
    finally:
        conn.close()


# ============================================================
# Paso 3: SEED_HOMOLOGACION (no vive ni en migraciones ni en seed DB)
# ============================================================
def insert_homologacion(http_url, headers) -> None:
    sys.path.insert(0, str(REPO))
    from app.core.homologacion import SEED_HOMOLOGACION  # noqa: E402

    n_remote = _table_count(http_url, headers, "aidu_homologacion_categoria")
    if n_remote > 0:
        print(f"⏭️  aidu_homologacion_categoria: ya tiene {n_remote} filas en Turso, skip")
        return
    print(f"🌱 Insertando {len(SEED_HOMOLOGACION)} categorías AIDU en aidu_homologacion_categoria...")
    cols = ["cod_servicio_aidu", "nombre_servicio", "linea", "hh_tipicas",
            "plazo_dias_tipico", "entregables_tipicos", "aplica_m2",
            "m2_referencia", "notas"]
    sql = f"""
        INSERT INTO aidu_homologacion_categoria ({",".join(cols)})
        VALUES ({",".join("?" * len(cols))})
    """
    # Coerción defensiva contra el schema (las claves de SEED_HOMOLOGACION son
    # int Python, las columnas son INTEGER — coincide, pero la coerción
    # protege ante futuros valores agregados con tipo distinto).
    col_types = _column_types(http_url, headers, "aidu_homologacion_categoria")
    stmts = []
    for item in SEED_HOMOLOGACION:
        raw_values = [
            item["cod"], item["nombre"], item["linea"],
            item["hh"], item["plazo"],
            item["entregables"], item["aplica_m2"],
            item["m2_ref"], item["notas"],
        ]
        args = [_arg(_coerce(v, col_types.get(c, ""))) for c, v in zip(cols, raw_values)]
        stmts.append({"sql": sql, "args": args})
    results = _execute(http_url, headers, stmts)
    for j, res in enumerate(results):
        if res.get("type") == "error":
            sys.exit(f"❌ INSERT homologación (item {j}): {res.get('error')}")
    print(f"  ✅ {len(stmts)} categorías insertadas")


# ============================================================
# Paso 4: verificación de criterios de éxito S12.1.5
# ============================================================
def verify(http_url, headers) -> bool:
    print("\n🔍 Verificación final (criterios S12.1.5)...")
    rows = _execute(http_url, headers, [{
        "sql": "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    }])[0]
    n_tables = int(rows["response"]["result"]["rows"][0][0]["value"]) if rows.get("type") == "ok" else -1
    print(f"  📊 Tablas totales en Turso: {n_tables}")

    all_ok = True
    for tbl, expected in EXPECTED_COUNTS.items():
        actual = _table_count(http_url, headers, tbl)
        ok = actual == expected
        all_ok = all_ok and ok
        emoji = "✅" if ok else "❌"
        print(f"  {emoji} {tbl}: esperado {expected}, en Turso {actual}")
    return all_ok


def main() -> None:
    http_url, headers = _endpoint()
    print(f"🌐 Endpoint Turso: {http_url}\n")
    apply_migrations(http_url, headers)
    print()
    # aidu_homologacion_categoria primero: 12 filas críticas que alimentan
    # toda la inteligencia de precios. Si algo falla más adelante, al menos
    # la operación con homologación queda lista. No tiene FKs entrantes ni
    # salientes, así que el orden no compite con dump_seed.
    insert_homologacion(http_url, headers)
    print()
    dump_seed(http_url, headers)
    ok = verify(http_url, headers)
    if not ok:
        print("\n⚠️  Bootstrap completado con discrepancias. Revisar conteos arriba.")
        sys.exit(2)
    print("\n✨ Bootstrap completado. Turso listo para producción.")


if __name__ == "__main__":
    main()
