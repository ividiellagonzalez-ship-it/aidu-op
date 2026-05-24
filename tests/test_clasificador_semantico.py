"""Tests S13.4.3 - clasificador semantico con Claude API mockeada.

Cubre:
- parsing de respuesta JSON valida.
- validacion de linea contra LINEAS_AIDU_FAST_CON_OTROS.
- manejo de respuesta con linea invalida -> fallback Otros + confidence=0.0.
- coercion de tipos (granular como int/string).
- descripcion corta retorna fallback sin pegar la API.
- normalizacion de respuesta con campos faltantes.

No hace llamadas reales a la API.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest

from app.core import clasificador_semantico as cs
from app.api.claude_client import ClaudeApiUnavailableError


@pytest.fixture
def respuesta_clean():
    return {
        "linea": "Salud",
        "es_producto_granular": True,
        "confidence": 0.95,
        "razon": "Insumo medico hospitalario con unidad y cantidad",
    }


class TestParsingRespuesta:

    def test_respuesta_completa_parseada(self, respuesta_clean):
        with patch.object(cs, "llamar_claude_json", return_value=respuesta_clean):
            res = cs.clasificar_via_claude("AGUJA HIPODERMICA 21G CAJA 100", "HOSPITAL X")
            assert res["linea"] == "Salud"
            assert res["es_producto_granular"] is True
            assert res["confidence"] == 0.95
            assert "Insumo" in res["razon"]

    def test_descripcion_corta_no_pega_api(self):
        with patch.object(cs, "llamar_claude_json") as mock_api:
            res = cs.clasificar_via_claude("abc", "X")
            assert mock_api.call_count == 0, (
                "Descripcion < 10 chars no debe pegar a la API (ahorro de costo)"
            )
            assert res["linea"] == "Otros"
            assert res["confidence"] == 0.0


class TestValidacionLinea:

    def test_linea_invalida_cae_a_otros(self):
        respuesta_mala = {
            "linea": "NoExiste",
            "es_producto_granular": True,
            "confidence": 0.99,
            "razon": "test",
        }
        with patch.object(cs, "llamar_claude_json", return_value=respuesta_mala):
            res = cs.clasificar_via_claude("PRODUCTO ALGO RANDOM", "ORG")
            assert res["linea"] == "Otros"
            assert res["confidence"] == 0.0
            assert "linea invalida" in res["razon"].lower()

    @pytest.mark.parametrize("linea_valida", [
        "Salud", "Aseo", "Oficina", "Ferreteria",
        "Equipamiento", "Materiales de Construccion", "Otros",
    ])
    def test_todas_las_lineas_validas_aceptadas(self, linea_valida):
        respuesta = {
            "linea": linea_valida,
            "es_producto_granular": True,
            "confidence": 0.85,
            "razon": "test",
        }
        with patch.object(cs, "llamar_claude_json", return_value=respuesta):
            res = cs.clasificar_via_claude("DESCRIPCION VALIDA AQUI", "ORG")
            assert res["linea"] == linea_valida


class TestCoercionTipos:

    def test_granular_como_string_true(self):
        respuesta = {
            "linea": "Salud", "es_producto_granular": "true",
            "confidence": 0.9, "razon": "x",
        }
        with patch.object(cs, "llamar_claude_json", return_value=respuesta):
            res = cs.clasificar_via_claude("DESCRIPCION VALIDA AQUI", "ORG")
            assert res["es_producto_granular"] is True

    def test_granular_como_string_false(self):
        respuesta = {
            "linea": "Salud", "es_producto_granular": "no",
            "confidence": 0.9, "razon": "x",
        }
        with patch.object(cs, "llamar_claude_json", return_value=respuesta):
            res = cs.clasificar_via_claude("DESCRIPCION VALIDA AQUI", "ORG")
            assert res["es_producto_granular"] is False

    def test_confidence_fuera_de_rango_se_clampa(self):
        respuesta = {
            "linea": "Salud", "es_producto_granular": True,
            "confidence": 1.5, "razon": "x",  # claude exagero
        }
        with patch.object(cs, "llamar_claude_json", return_value=respuesta):
            res = cs.clasificar_via_claude("DESCRIPCION VALIDA AQUI", "ORG")
            assert 0.0 <= res["confidence"] <= 1.0
            assert res["confidence"] == 1.0


class TestCamposFaltantes:

    def test_falta_linea_cae_a_otros(self):
        respuesta = {
            "es_producto_granular": True,
            "confidence": 0.9,
            "razon": "sin linea",
        }
        with patch.object(cs, "llamar_claude_json", return_value=respuesta):
            res = cs.clasificar_via_claude("DESCRIPCION VALIDA AQUI", "ORG")
            assert res["linea"] == "Otros"
            assert res["confidence"] == 0.0

    def test_respuesta_no_dict_cae_a_otros(self):
        with patch.object(cs, "llamar_claude_json", return_value="texto plano"):
            res = cs.clasificar_via_claude("DESCRIPCION VALIDA AQUI", "ORG")
            assert res["linea"] == "Otros"
            assert res["confidence"] == 0.0


class TestPropagacionErrorAPI:

    def test_claude_api_unavailable_se_propaga(self):
        with patch.object(cs, "llamar_claude_json",
                          side_effect=ClaudeApiUnavailableError("API down")):
            with pytest.raises(ClaudeApiUnavailableError):
                cs.clasificar_via_claude("DESCRIPCION VALIDA AQUI", "ORG")
