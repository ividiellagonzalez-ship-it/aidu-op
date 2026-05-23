"""Tests sec 4.11 — idempotencia del script de reclasificacion (S13.4.2).

El script s13_4_2_reclasificar_lineas.py corre via workflow temporal y
debe ser idempotente: re-ejecutarlo produce el mismo estado final.

Logica: para cada item, calcular linea_nueva = categorizar_linea(desc).
  - Si linea_nueva == linea_actual → no-op (no UPDATE).
  - Si linea_nueva != linea_actual → UPDATE SET linea_aidu=nueva,
    linea_aidu_anterior=actual, fecha+motivo.

La segunda corrida del script no debe producir ningun UPDATE porque
todos los items ya estan con su linea correcta segun el nuevo
clasificador.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.categorizador_aidu_fast import (
    cargar_catalogo_desde_csv,
    categorizar_linea,
    reset_cache,
    set_catalogo,
)

CSV_PATH = Path(__file__).resolve().parents[1] / "config" / "keywords_aidu_fast.csv"


@pytest.fixture(autouse=True)
def _load_catalog():
    reset_cache()
    set_catalogo(cargar_catalogo_desde_csv(CSV_PATH))
    yield
    reset_cache()


def _decidir_reclasificacion(linea_actual: str, descripcion: str):
    """Replica la logica del script: devuelve (linea_nueva, kws_matched, debe_actualizar)."""
    linea_nueva, kws = categorizar_linea(descripcion)
    debe_actualizar = (linea_nueva != linea_actual)
    return linea_nueva, kws, debe_actualizar


class TestIdempotencia:

    def test_primera_corrida_aplica_cambios(self):
        # Antes del refactor: "BOLSA DE CEMENTO 25KG" estaba en Ferreteria.
        # Tras refactor: debe reclasificarse a Materiales de Construccion.
        nueva, _, debe = _decidir_reclasificacion("Ferreteria", "BOLSA DE CEMENTO 25KG")
        assert nueva == "Materiales de Construccion"
        assert debe is True

    def test_segunda_corrida_es_noop(self):
        # Si la linea_actual YA es la correcta (post-primer-run), el
        # script no debe actualizar.
        nueva, _, debe = _decidir_reclasificacion(
            "Materiales de Construccion", "BOLSA DE CEMENTO 25KG"
        )
        assert nueva == "Materiales de Construccion"
        assert debe is False

    def test_item_ya_correcto_no_cambia(self):
        # Items que ya estaban bien clasificados desde S13: no deben moverse.
        nueva, _, debe = _decidir_reclasificacion("Oficina", "RESMA DE PAPEL CARTA 75 GR")
        assert nueva == "Oficina"
        assert debe is False

    def test_item_otros_que_es_salud_se_reclasifica(self):
        # El caso central del sprint: items en "Otros" que matchean Salud
        # ahora se reclasifican.
        nueva, _, debe = _decidir_reclasificacion(
            "Otros", "JERINGA DESCARTABLE 5ML CAJA"
        )
        assert nueva == "Salud"
        assert debe is True

    def test_item_otros_sin_match_sigue_otros(self):
        # Items que no matchean ninguna linea siguen siendo Otros.
        nueva, _, debe = _decidir_reclasificacion(
            "Otros", "TARJETAS GIFT CARD AÑO 2026"
        )
        assert nueva == "Otros"
        assert debe is False
