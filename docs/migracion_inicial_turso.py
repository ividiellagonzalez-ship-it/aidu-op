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
    """Convierte un valor Python al formato {type, value} de Turso."""
    if value is None:
        return {"type": "null", "value": None}
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        return {"type": "float", "value": str(value)}
    if isinstance(value, (bytes, bytearray)):
        import base64
        return {"type": "blob", "base64": base64.b64encode(bytes(value)).decode()}
    return {"type": "text", "value": str(value)}


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


def dump_seed(http_url, headers) -> None:
    if not SEED_DB.exists():
        print(f"⚠️  No hay {SEED_DB.name}; skipeando dump.")
        return
    print(f"📦 Volcando seed desde {SEED_DB.name} → Turso...")
    conn = sqlite3.connect(SEED_DB)
    conn.row_factory = sqlite3.Row
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()]

        for tbl in tables:
            if tbl in SKIP_TABLES:
                print(f"  ⏭️  {tbl}: skip (gestión separada)")
                continue
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

            cols = rows[0].keys()
            col_list = ",".join(f'"{c}"' for c in cols)
            placeholders = ",".join("?" * len(cols))
            sql = f'INSERT INTO "{tbl}" ({col_list}) VALUES ({placeholders})'

            n_total = 0
            for i in range(0, len(rows), BATCH_SIZE):
                batch = rows[i:i + BATCH_SIZE]
                stmts = [{"sql": sql, "args": [_arg(v) for v in row]} for row in batch]
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
    sql = """
        INSERT INTO aidu_homologacion_categoria
        (cod_servicio_aidu, nombre_servicio, linea, hh_tipicas, plazo_dias_tipico,
         entregables_tipicos, aplica_m2, m2_referencia, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    stmts = []
    for item in SEED_HOMOLOGACION:
        args = [
            _arg(item["cod"]), _arg(item["nombre"]), _arg(item["linea"]),
            _arg(item["hh"]), _arg(item["plazo"]),
            _arg(item["entregables"]), _arg(item["aplica_m2"]),
            _arg(item["m2_ref"]), _arg(item["notas"]),
        ]
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
    dump_seed(http_url, headers)
    print()
    insert_homologacion(http_url, headers)
    ok = verify(http_url, headers)
    if not ok:
        print("\n⚠️  Bootstrap completado con discrepancias. Revisar conteos arriba.")
        sys.exit(2)
    print("\n✨ Bootstrap completado. Turso listo para producción.")


if __name__ == "__main__":
    main()
