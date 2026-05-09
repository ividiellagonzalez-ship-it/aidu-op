"""
app/db/_hrana_types.py
=======================
Helpers para el protocolo Hrana (endpoint /v2/pipeline de Turso).

Centraliza la conversión Python → JSON-Hrana y la coerción al tipo afín
de la columna SQLite. Antes vivían duplicados en docs/migracion_inicial_turso.py
(bootstrap one-shot) y app/db/migrator.py (proxy DDL/DML del runtime).
S12.2 los unifica acá para evitar drift y arreglar de una el bug latente
de coerción de floats que tenía migrator (str(float) → HTTP 400 'expected f64').

Uso:
    from app.db._hrana_types import arg_for_value, coerce_for_column

    args = [arg_for_value(coerce_for_column(v, col_type)) for v in row_values]
    payload = {"sql": stmt, "args": args}

Convenciones del protocolo (referencia: hrana docs):
- integer: `value` debe ser STRING (decimal). JSON no representa int64
  con precisión y Hrana lo serializa como string para evitar pérdida.
- float:   `value` debe ser un NÚMERO JSON crudo (NO string). Si se manda
  como string Turso responde HTTP 400 'invalid type: string "1.0",
  expected f64'. Bug que motivó S12.1.5.bis y la unificación de S12.2.
- text:    `value` debe ser string.
- null:    `value` debe ser null.
- blob:    se envía bajo la clave `base64` (no `value`).
"""
from __future__ import annotations

import base64
from typing import Any


def arg_for_value(value: Any) -> dict:
    """
    Convierte un valor Python al formato {type, value} del protocolo Hrana.
    No coacciona — la coerción al tipo afín de la columna debe pasar por
    coerce_for_column antes de llegar acá si la query toca columnas tipadas.

    Tabla de mapeos:
        None              -> {"type": "null", "value": None}
        bool              -> {"type": "integer", "value": "0"|"1"}
        int               -> {"type": "integer", "value": str(int)}
        float             -> {"type": "float", "value": float}      # numero JSON crudo
        bytes / bytearray -> {"type": "blob", "base64": "..."}
        cualquier otro    -> {"type": "text", "value": str(value)}
    """
    if value is None:
        return {"type": "null", "value": None}
    # bool antes de int: en Python `bool` es subclase de `int`, así que
    # isinstance(True, int) == True. Si se chequea int primero, los booleanos
    # se tratan como ints arbitrarios y pierden semántica para el caller.
    if isinstance(value, bool):
        return {"type": "integer", "value": str(int(value))}
    if isinstance(value, int):
        return {"type": "integer", "value": str(value)}
    if isinstance(value, float):
        # Número JSON crudo. NO string. Esto es lo que rompía _query_on_turso
        # antes de S12.2: usaba str(p) y Turso devolvía HTTP 400.
        return {"type": "float", "value": value}
    if isinstance(value, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(bytes(value)).decode()}
    return {"type": "text", "value": str(value)}


def coerce_for_column(value: Any, sqlite_type: str) -> Any:
    """
    Coerciona el valor Python al tipo afín de la columna SQLite/Turso destino.

    SQLite tiene tipado dinámico flexible: una fila con un INTEGER en una
    columna REAL queda almacenada como int. Cuando ese mismo valor se envía
    vía Hrana a Turso, va como `{"type":"integer","value":"X"}`, y Turso (más
    estricto) rechaza con HTTP 400 'expected f64'. Esta función normaliza al
    tipo de afinidad declarado en el schema antes de construir el arg.

    No coacciona NULL (NULL es válido para cualquier afinidad).
    Si la conversión falla (TypeError/ValueError) devuelve el valor original
    para que el error del servidor sea claro y diagnosticable.

    Reglas SQLite type affinity (https://www.sqlite.org/datatype3.html):
        - "INT" en el nombre  -> INTEGER
        - "REAL"/"FLOA"/"DOUB" -> REAL
        - "NUM"               -> NUMERIC (tratado acá como REAL: coerce a float)
        - "BLOB"              -> BLOB
        - "TEXT"/"CHAR"/"CLOB" -> TEXT (sin coerción)
        - vacío / desconocido -> sin coerción
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
    # TEXT, CHAR, CLOB y desconocidos: dejar como está
    return value


def args_for_row(values: list, col_types: list[str] | None = None) -> list[dict]:
    """
    Conveniencia: construye la lista de args Hrana para una fila completa.
    Si col_types se provee (mismo largo que values), aplica coerce_for_column
    elemento a elemento antes de arg_for_value. Si no, manda los valores raw.

    Útil para INSERTs masivos donde ya tenés `PRAGMA table_info(<tabla>)`.
    """
    if col_types is None:
        return [arg_for_value(v) for v in values]
    if len(col_types) != len(values):
        raise ValueError(
            f"args_for_row: col_types ({len(col_types)}) y values ({len(values)}) "
            f"deben tener el mismo largo"
        )
    return [arg_for_value(coerce_for_column(v, t)) for v, t in zip(values, col_types)]
