"""Tests del ingestor de inteligencia_precios (S13.5).

Cubre:
- expandir_items con shapes reales de la API (1 item, multiples items,
  MontoUnitario NULL).
- Filtro pre-detalle por unit_code (dedupe: misma comuna con multiples
  unit_codes se cuenta como organizaciones distintas).
- Idempotencia: la misma corrida 2 veces sobre los mismos detalles llama
  INSERT OR IGNORE sin generar mas filas (verificamos via mock que el SQL
  emitido es INSERT OR IGNORE).
- es_ohiggins en el ingestor (defense in depth).
"""
from __future__ import annotations

import random
from unittest.mock import patch, MagicMock

import pytest

from app.core.ingesta_inteligencia_precios import (
    _filtrar_listado,
    _INSERT_INTELIGENCIA_SQL,
    categorizar_item,
    expandir_items,
    extraer_unit_code,
    persistir_lote,
    TIPOS_SCOPE,
)
from app.core.categorizador_aidu_fast import set_catalogo, reset_cache


# ============================================================
# UNIT_CODE
# ============================================================

class TestExtraerUnitCode:
    @pytest.mark.parametrize("codigo,esperado", [
        ("1620-9-LE26", "1620"),
        ("525512-8-LE26", "525512"),
        ("580075-1-CO26", "580075"),
        ("", ""),
        (None, ""),
        ("sin-guion", "sin"),  # defensive
    ])
    def test_split_segmento(self, codigo, esperado):
        assert extraer_unit_code(codigo) == esperado


class TestFiltrarListado:

    def test_filtra_solo_unit_codes_en_set(self):
        listado = [
            {"CodigoExterno": "1620-1-LE26"},
            {"CodigoExterno": "9999-1-LE26"},   # NO esta en seed
            {"CodigoExterno": "1620-2-CO26"},
            {"CodigoExterno": "8888-3-LE26"},   # NO esta en seed
        ]
        unit_codes = {"1620"}
        rng = random.Random(42)
        matched, discovery = _filtrar_listado(listado, unit_codes, 0, rng)
        assert len(matched) == 2
        assert all(extraer_unit_code(m["CodigoExterno"]) == "1620" for m in matched)
        assert discovery == []  # discovery_sample_size=0

    def test_discovery_sample_size_n(self):
        listado = [
            {"CodigoExterno": f"{i}-1-LE26"} for i in range(100, 200)
        ]
        unit_codes = set()  # ninguno matchea
        rng = random.Random(42)
        matched, discovery = _filtrar_listado(listado, unit_codes, 10, rng)
        assert matched == []
        assert len(discovery) == 10
        # Discovery sample debe ser subset del listado
        codigos_listado = {l["CodigoExterno"] for l in listado}
        assert all(d["CodigoExterno"] in codigos_listado for d in discovery)

    def test_dedupe_por_unit_code_no_por_organismo(self):
        """Misma comuna con 2 unit_codes distintos -> 2 entradas separadas.
        Ambos se filtran independientemente."""
        listado = [
            {"CodigoExterno": "1743-5-LE26"},     # Lituche, unit 1
            {"CodigoExterno": "580075-2-LE26"},   # Lituche, unit 2 (mismo organismo, otra unidad)
        ]
        unit_codes = {"1743", "580075"}
        rng = random.Random(42)
        matched, _ = _filtrar_listado(listado, unit_codes, 0, rng)
        assert len(matched) == 2  # ambos pasan, NO se dedupean


# ============================================================
# EXPANDIR ITEMS
# ============================================================

# Shape real observado durante S13.0 sampling
DETALLE_REAL_LE = {
    "Listado": [{
        "CodigoExterno": "1620-9-LE26",
        "Tipo": "LE",
        "Comprador": {
            "NombreOrganismo": "I MUNICIPALIDAD DE RANCAGUA",
            "RegionUnidad": "Region del Libertador General Bernardo O´Higgins",
            "CodigoOrganismo": "7054",
        },
        "Items": {
            "Listado": [{
                "Correlativo": 1,
                "Descripcion": "BOLSA DE CEMENTO 25KG",
                "Cantidad": 100,
                "UnidadMedida": "un",
                "Adjudicacion": {
                    "MontoUnitario": 3500.0,
                    "Cantidad": 100,
                    "NombreProveedor": "FERRETERIA SUR LTDA",
                    "RutProveedor": "77.111.222-3",
                },
            }]
        },
    }]
}


class TestExpandirItems:

    def test_un_item_con_monto(self):
        items = expandir_items(DETALLE_REAL_LE, fecha_adjudicacion="2026-05-19")
        assert len(items) == 1
        it = items[0]
        assert it["codigo_mp"] == "1620-9-LE26"
        assert it["correlativo_item"] == 1
        assert it["tipo_licitacion"] == "LE"
        assert it["unit_code"] == "1620"
        assert it["fecha_adjudicacion"] == "2026-05-19"
        assert it["precio_unitario"] == 3500.0
        assert it["cantidad"] == 100
        assert it["monto_total"] == 350000.0
        assert it["proveedor_rut"] == "77.111.222-3"

    def test_monto_unitario_null(self):
        """Hallazgo S13.0: ~36% de L1 vienen con MontoUnitario NULL."""
        det = {"Listado": [{
            "CodigoExterno": "X-1-L126",
            "Tipo": "L1",
            "Comprador": {"NombreOrganismo": "X", "RegionUnidad": "O'Higgins"},
            "Items": {"Listado": [{
                "Correlativo": 1,
                "Descripcion": "PAPEL",
                "Cantidad": 50,
                "Adjudicacion": {"MontoUnitario": None, "Cantidad": 50,
                                 "NombreProveedor": "Y", "RutProveedor": "Z"},
            }]},
        }]}
        items = expandir_items(det)
        assert len(items) == 1
        assert items[0]["precio_unitario"] is None
        # monto_total queda None tambien (no inventamos)
        assert items[0]["monto_total"] is None

    def test_detalle_sin_listado(self):
        # Algunos shapes vienen sin envoltorio Listado
        det = {**DETALLE_REAL_LE["Listado"][0]}
        items = expandir_items(det)
        assert len(items) == 1

    def test_detalle_invalido_vacio(self):
        assert expandir_items(None) == []
        assert expandir_items({}) == []
        assert expandir_items({"Listado": []}) == []

    def test_multiples_items(self):
        det = {"Listado": [{
            "CodigoExterno": "X-2-LE26",
            "Tipo": "LE",
            "Comprador": {"NombreOrganismo": "X", "RegionUnidad": "O'Higgins"},
            "Items": {"Listado": [
                {"Correlativo": 1, "Descripcion": "A", "Cantidad": 1,
                 "Adjudicacion": {"MontoUnitario": 100, "Cantidad": 1,
                                  "NombreProveedor": "P", "RutProveedor": "R"}},
                {"Correlativo": 2, "Descripcion": "B", "Cantidad": 2,
                 "Adjudicacion": {"MontoUnitario": 200, "Cantidad": 2,
                                  "NombreProveedor": "P", "RutProveedor": "R"}},
            ]},
        }]}
        items = expandir_items(det)
        assert len(items) == 2
        assert items[0]["correlativo_item"] == 1
        assert items[1]["correlativo_item"] == 2


# ============================================================
# IDEMPOTENCIA: INSERT OR IGNORE en SQL emitido
# ============================================================

class TestIdempotencia:

    def test_sql_es_insert_or_ignore(self):
        """El SQL canonico DEBE ser INSERT OR IGNORE para que re-correr
        un lote no duplique filas (criterio de exito #9 spec)."""
        assert "INSERT OR IGNORE INTO inteligencia_precios" in _INSERT_INTELIGENCIA_SQL

    def test_unique_correcto(self):
        """La UNIQUE constraint vive en (codigo_mp, correlativo_item).
        Confirmado en mig 009."""
        from pathlib import Path
        sql = Path("app/db/migrations/009_inteligencia_precios.sql").read_text(encoding="utf-8")
        assert "UNIQUE (codigo_mp, correlativo_item)" in sql

    def test_persistir_lote_envia_batches_correctos(self):
        """Mockea execute_pipeline. Verifica que persistir_lote envia
        len(items) statements con el SQL correcto."""
        with patch("app.core.ingesta_inteligencia_precios.turso_http_client.execute_pipeline") as mock_exec:
            mock_exec.return_value = []
            items = [
                {"codigo_mp": "X-1-LE26", "correlativo_item": 1,
                 "fecha_adjudicacion": "2026-05-19", "tipo_licitacion": "LE",
                 "organismo_comprador": "X", "unit_code": "X",
                 "organismo_region": "O'Higgins", "region_entrega": "O'Higgins",
                 "producto_descripcion": "A", "unidad_medida": "un",
                 "cantidad": 1, "precio_unitario": 100, "monto_total": 100,
                 "proveedor_nombre": "P", "proveedor_rut": "R",
                 "n_oferentes": 1, "linea_aidu": "Ferreteria",
                 "tipo_objeto": "producto", "keywords_matched": ""},
            ]
            n = persistir_lote(items, lote_id="test")
            assert n == 1
            assert mock_exec.called
            args, kwargs = mock_exec.call_args
            statements = args[0]
            assert len(statements) == 1
            assert "INSERT OR IGNORE" in statements[0]["sql"]


# ============================================================
# FILTRO GEOGRAFICO (defense in depth via es_ohiggins)
# ============================================================

class TestFiltroGeografico:

    def test_organismo_ohiggins_pasa(self):
        from app.core.categorizador_aidu_fast import es_ohiggins
        assert es_ohiggins("Region del Libertador General Bernardo O´Higgins")

    def test_organismo_otra_region_no_pasa(self):
        from app.core.categorizador_aidu_fast import es_ohiggins
        assert not es_ohiggins("Region Metropolitana de Santiago")

    def test_entrega_diferente_no_se_evalua_aqui(self):
        """El filtro region_entrega del spec es secundario en el ingestor:
        si organismo es O'Higgins, ingerimos aunque la entrega declarada
        sea otra region. La columna region_entrega se persiste para que
        la pantalla Streamlit pueda filtrar opcionalmente."""
        # Este test es documental: no hay logica del codigo a verificar.
        # La pantalla aplica el filtro al vuelo.
        assert True


# ============================================================
# CATEGORIZAR_ITEM (integracion ligera)
# ============================================================

class TestCategorizarItemEnIngestor:

    def setup_method(self):
        reset_cache()
        # Cargar catalogo desde CSV para todos los tests de esta clase
        from app.core.categorizador_aidu_fast import cargar_catalogo_desde_csv
        from pathlib import Path
        csv_path = Path(__file__).resolve().parents[1] / "config" / "keywords_aidu_fast.csv"
        set_catalogo(cargar_catalogo_desde_csv(csv_path))

    def teardown_method(self):
        reset_cache()

    def test_item_cemento(self):
        # S13.4.2: con prioridad fija, "cemento" cae en "Materiales de
        # Construccion" en lugar de Ferreteria (la keyword esta en ambas
        # lineas; la prioridad resuelve la colision). Cambio semanticamente
        # correcto.
        item = {"producto_descripcion": "BOLSA DE CEMENTO 25KG", "codigo_mp": "X-1"}
        out = categorizar_item(item)
        assert out["linea_aidu"] == "Materiales de Construccion"
        assert out["tipo_objeto"] == "producto"
        assert "cemento" in out["keywords_matched"]

    def test_item_servicio_consultoria(self):
        item = {"producto_descripcion": "SERVICIO DE CONSULTORIA TECNICA", "codigo_mp": "X-1"}
        out = categorizar_item(item)
        assert out["tipo_objeto"] == "servicio"
        # linea probablemente Otros (no hay keyword AIDU Fast matcheado)
        assert out["linea_aidu"] in ("Otros",)


# ============================================================
# TIPOS_SCOPE: documenta que CA esta fuera por S13.1
# ============================================================

class TestTiposScope:

    def test_ca_no_esta(self):
        assert "CA" not in TIPOS_SCOPE
        assert "AGIL" not in TIPOS_SCOPE

    def test_tipos_objetivo(self):
        assert set(TIPOS_SCOPE) == {"L1", "LE", "CO"}
