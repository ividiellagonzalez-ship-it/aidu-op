"""Tests S13.4.3 - fallback al clasificador lexical ante fallo de Claude API.

Verifica que el ingestor cae al `categorizar_linea` lexical sin perder
data cuando Claude API falla por:
- ANTHROPIC_API_KEY ausente
- Network error / timeout
- Respuesta no parseable
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.api.claude_client import ClaudeApiUnavailableError
from app.core.categorizador_aidu_fast import (
    cargar_catalogo_desde_csv,
    reset_cache,
    set_catalogo,
)
from app.core import ingesta_inteligencia_precios as ing


CSV_PATH = Path(__file__).resolve().parents[1] / "config" / "keywords_aidu_fast.csv"


@pytest.fixture(autouse=True)
def _load_catalog():
    reset_cache()
    set_catalogo(cargar_catalogo_desde_csv(CSV_PATH))
    yield
    reset_cache()


class TestFallbackLexicalAnteFalloAPI:

    def test_usar_semantico_false_solo_lexical(self):
        """Default usar_semantico=False: nunca pega la API."""
        item = {"producto_descripcion": "BOLSA DE CEMENTO 25KG", "codigo_mp": "X-1"}
        # No mockeamos Claude porque NO debe llamarse
        out = ing.categorizar_item(item, usar_semantico=False)
        assert out["linea_aidu"] == "Materiales de Construccion"
        assert out["clasificacion_metodo"] == "keyword"
        assert out["confidence_score"] == 0.0
        # Granular queda None en modo lexical (no se determina)
        assert out["es_producto_granular"] is None

    def test_usar_semantico_true_claude_responde_ok(self):
        """Modo semantico exitoso: sobrescribe lexical."""
        item = {"producto_descripcion": "AGUJA HIPODERMICA 21G", "codigo_mp": "X-2"}
        respuesta = {
            "linea": "Salud", "es_producto_granular": True,
            "confidence": 0.95, "razon": "Insumo medico",
        }
        with patch(
            "app.core.clasificador_semantico.llamar_claude_json",
            return_value=respuesta,
        ):
            out = ing.categorizar_item(item, usar_semantico=True)
            assert out["linea_aidu"] == "Salud"
            assert out["clasificacion_metodo"] == "semantic"
            assert out["confidence_score"] == 0.95
            assert out["es_producto_granular"] is True

    def test_usar_semantico_true_api_falla_cae_a_lexical(self):
        """Si Claude falla con ClaudeApiUnavailableError, conserva
        clasificacion lexical sin abortar la ingesta."""
        item = {"producto_descripcion": "BOLSA DE CEMENTO 25KG", "codigo_mp": "X-3"}
        with patch(
            "app.core.clasificador_semantico.llamar_claude_json",
            side_effect=ClaudeApiUnavailableError("API down"),
        ):
            out = ing.categorizar_item(item, usar_semantico=True)
            # Cae a lexical: cemento -> Construccion por prioridad fija
            assert out["linea_aidu"] == "Materiales de Construccion"
            assert out["clasificacion_metodo"] == "keyword"
            assert out["confidence_score"] == 0.0
            # No marca granular en fallback lexical
            assert out["es_producto_granular"] is None

    def test_usar_semantico_true_excepcion_inesperada_no_aborta(self):
        """Cualquier excepcion no-Claude tambien cae a lexical sin abortar."""
        item = {"producto_descripcion": "RESMA PAPEL CARTA 75GR", "codigo_mp": "X-4"}
        with patch(
            "app.core.clasificador_semantico.llamar_claude_json",
            side_effect=RuntimeError("network blip"),
        ):
            out = ing.categorizar_item(item, usar_semantico=True)
            # Debe haber clasificado por lexical sin crash
            assert "linea_aidu" in out
            # Si llegamos aca sin excepcion el test pasa
            assert out.get("clasificacion_metodo") == "keyword"


class TestSchemaCamposNuevos:
    """Garantiza que `categorizar_item` siempre emite las 3 columnas
    nuevas de la mig 012, en cualquier modo. Esto es importante para
    que el INSERT del ingestor no rompa por KeyError."""

    @pytest.mark.parametrize("usar_semantico", [False, True])
    def test_emite_es_producto_granular_confidence_metodo(self, usar_semantico):
        item = {"producto_descripcion": "CEMENTO 25KG", "codigo_mp": "X-5"}
        # En modo semantico, mockeamos para que no pegue API
        if usar_semantico:
            patcher = patch(
                "app.core.clasificador_semantico.llamar_claude_json",
                return_value={
                    "linea": "Materiales de Construccion",
                    "es_producto_granular": True,
                    "confidence": 0.9, "razon": "x",
                },
            )
            patcher.start()
        try:
            out = ing.categorizar_item(item, usar_semantico=usar_semantico)
        finally:
            if usar_semantico:
                patcher.stop()

        for key in ("es_producto_granular", "confidence_score", "clasificacion_metodo"):
            assert key in out, f"Falta campo {key!r} en modo usar_semantico={usar_semantico}"
