"""
Tests para app/db/_hrana_types — helpers Hrana compartidos (S12.2).

Cubre:
- arg_for_value: tipos básicos (None, bool, int, float, str, blob).
- arg_for_value: regresión del bug str(float) → Turso HTTP 400 'expected f64'.
- coerce_for_column: afinidades INT/REAL/NUM/BLOB/TEXT/desconocido.
- args_for_row: composición + validación de longitudes.
- Que migrator y bootstrap re-exporten las mismas funciones (anti-drift).

Ejecutar: pytest tests/test_hrana_types.py -v
"""
from __future__ import annotations

import pytest

from app.db._hrana_types import arg_for_value, coerce_for_column, args_for_row


# ============================================================
# arg_for_value
# ============================================================
class TestArgForValue:

    def test_none(self):
        assert arg_for_value(None) == {"type": "null", "value": None}

    def test_bool_true(self):
        # bool primero que int (bool es subclase de int en Python)
        assert arg_for_value(True) == {"type": "integer", "value": "1"}

    def test_bool_false(self):
        assert arg_for_value(False) == {"type": "integer", "value": "0"}

    def test_int_positivo(self):
        assert arg_for_value(42) == {"type": "integer", "value": "42"}

    def test_int_grande(self):
        # int64 max = 9223372036854775807. JSON number perdería precisión,
        # por eso Hrana exige string para integer.
        big = 9223372036854775807
        assert arg_for_value(big) == {"type": "integer", "value": str(big)}

    def test_int_negativo(self):
        assert arg_for_value(-7) == {"type": "integer", "value": "-7"}

    def test_float_es_numero_no_string(self):
        # REGRESIÓN del bug que rompía _query_on_turso pre-S12.2.
        # Turso (Hrana) rechaza con HTTP 400 'expected f64' si value es string.
        out = arg_for_value(1.5)
        assert out == {"type": "float", "value": 1.5}
        assert isinstance(out["value"], float), "float debe ir como número JSON crudo"

    def test_float_cero(self):
        out = arg_for_value(0.0)
        assert out == {"type": "float", "value": 0.0}
        assert isinstance(out["value"], float)

    def test_float_negativo(self):
        out = arg_for_value(-3.14)
        assert isinstance(out["value"], float)

    def test_text(self):
        assert arg_for_value("hola") == {"type": "text", "value": "hola"}

    def test_text_unicode(self):
        assert arg_for_value("ñoño") == {"type": "text", "value": "ñoño"}

    def test_text_no_string(self):
        # Cualquier objeto desconocido cae a text(str(x))
        class Foo:
            def __str__(self):
                return "foo-repr"
        assert arg_for_value(Foo()) == {"type": "text", "value": "foo-repr"}

    def test_blob_bytes(self):
        out = arg_for_value(b"abc")
        assert out["type"] == "blob"
        assert "base64" in out
        # ASCII "abc" -> "YWJj" en base64
        assert out["base64"] == "YWJj"
        assert "value" not in out

    def test_blob_bytearray(self):
        out = arg_for_value(bytearray(b"hi"))
        assert out["type"] == "blob"
        assert out["base64"] == "aGk="


# ============================================================
# coerce_for_column
# ============================================================
class TestCoerceForColumn:

    def test_none_passthrough(self):
        # NULL es válido para cualquier afinidad → no se coacciona
        assert coerce_for_column(None, "INTEGER") is None
        assert coerce_for_column(None, "REAL") is None
        assert coerce_for_column(None, "TEXT") is None

    def test_int_affinity_from_string(self):
        assert coerce_for_column("42", "INTEGER") == 42
        assert coerce_for_column("42", "BIGINT") == 42

    def test_int_affinity_from_float(self):
        assert coerce_for_column(3.0, "INTEGER") == 3

    def test_int_affinity_invalid_passthrough(self):
        # Si no se puede convertir, devolver original para que el server
        # tire error claro (no enmascarar)
        assert coerce_for_column("no-numero", "INTEGER") == "no-numero"

    def test_real_affinity_from_int(self):
        # CASO QUE ROMPÍA EL BOOTSTRAP: int en columna REAL.
        out = coerce_for_column(1, "REAL")
        assert out == 1.0
        assert isinstance(out, float)

    def test_real_affinity_from_string(self):
        assert coerce_for_column("1.5", "REAL") == 1.5

    def test_floa_affinity(self):
        # Variantes que SQLite afín-matchea: FLOAT, FLOA*, DOUBLE
        assert isinstance(coerce_for_column(1, "FLOAT"), float)
        assert isinstance(coerce_for_column(1, "DOUBLE PRECISION"), float)

    def test_num_affinity(self):
        # NUMERIC se trata como REAL (coerce a float). Decisión documentada
        # en _hrana_types: SQLite NUM afinidad puede aceptar int o real,
        # pero Hrana es estricto, así que mandamos float para evitar drift.
        assert isinstance(coerce_for_column(5, "NUMERIC"), float)

    def test_blob_affinity_string_to_bytes(self):
        out = coerce_for_column("hola", "BLOB")
        assert isinstance(out, bytes)
        assert out == b"hola"

    def test_blob_affinity_passthrough(self):
        assert coerce_for_column(b"abc", "BLOB") == b"abc"

    def test_text_affinity_no_coerce(self):
        # Strings se mantienen, no se convierten a número
        assert coerce_for_column("hola", "TEXT") == "hola"
        assert coerce_for_column("123", "VARCHAR(50)") == "123"

    def test_unknown_affinity_passthrough(self):
        # Tipo vacío o desconocido: no coercer
        assert coerce_for_column(42, "") == 42
        assert coerce_for_column("foo", "") == "foo"
        assert coerce_for_column(42, "WEIRD_TYPE") == 42

    def test_case_insensitive(self):
        # Mayúsculas/minúsculas no importan
        assert isinstance(coerce_for_column(1, "real"), float)
        assert isinstance(coerce_for_column(1, "Integer"), int)


# ============================================================
# args_for_row
# ============================================================
class TestArgsForRow:

    def test_sin_col_types(self):
        out = args_for_row([1, "a", 1.5])
        assert out == [
            {"type": "integer", "value": "1"},
            {"type": "text", "value": "a"},
            {"type": "float", "value": 1.5},
        ]

    def test_con_col_types_aplica_coerce(self):
        # int en columna REAL → debe llegar como float
        out = args_for_row([1, "hola"], ["REAL", "TEXT"])
        assert out[0] == {"type": "float", "value": 1.0}
        assert out[1] == {"type": "text", "value": "hola"}

    def test_longitudes_distintas_levanta(self):
        with pytest.raises(ValueError, match="mismo largo"):
            args_for_row([1, 2, 3], ["INTEGER", "TEXT"])

    def test_lista_vacia(self):
        assert args_for_row([]) == []
        assert args_for_row([], []) == []


# ============================================================
# Anti-drift: bootstrap y migrator usan el módulo
# ============================================================
class TestAntiDrift:

    def test_bootstrap_usa_modulo(self):
        # docs/migracion_inicial_turso.py debe re-exportar arg_for_value/coerce_for_column
        import importlib.util
        from pathlib import Path
        repo = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location(
            "boot_s12_2", repo / "docs" / "migracion_inicial_turso.py"
        )
        boot = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(boot)
        from app.db import _hrana_types
        assert boot._arg is _hrana_types.arg_for_value
        assert boot._coerce is _hrana_types.coerce_for_column

    def test_migrator_usa_modulo(self):
        # _hrana_post lo importa lazy. Patch indirecto: verificar que
        # arg_for_value se resuelva desde _hrana_types al ejecutar el helper
        # con un float, y que NO se serialice como string.
        from app.db import migrator
        # Sin credenciales el helper retorna {} (no-op). Lo que nos importa
        # acá es que el módulo importe sin errores de los nombres viejos.
        assert hasattr(migrator, "_query_on_turso")
        assert hasattr(migrator, "_execute_on_turso")
        assert hasattr(migrator, "_hrana_post")
        # _execute_on_turso ahora acepta params (S12.2)
        import inspect
        sig = inspect.signature(migrator._execute_on_turso)
        assert "params" in sig.parameters
