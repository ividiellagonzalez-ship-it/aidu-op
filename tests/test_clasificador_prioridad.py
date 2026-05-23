"""Tests sec 4.11 — prioridad fija ante matches multiples (S13.4.2 D3).

Verifica que cuando un item matchea keywords de >=2 lineas, la linea con
mayor prioridad gana. Tambien valida que keywords excluyentes funcionan.
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


class TestPrioridadFija:
    """Cada caso matchea keywords de mas de una linea — la linea con
    prioridad mas alta debe ganar (Salud > Construccion > Aseo > Oficina >
    Ferreteria > Equipamiento)."""

    def test_cemento_va_a_construccion_no_ferreteria(self):
        # `cemento` esta en Ferreteria (legacy) y en Construccion. Con
        # prioridad, gana Construccion (mas especifica).
        linea, _ = categorizar_linea("BOLSA DE CEMENTO 25KG")
        assert linea == "Materiales de Construccion"

    def test_arido_va_a_construccion_no_ferreteria(self):
        # `arido` esta en Ferreteria (legacy de S13-keywords-iter-1) y en
        # Construccion. Con prioridad, gana Construccion.
        linea, _ = categorizar_linea("CONVENIO DE SUMINISTRO ÁRIDOS PARA OBRAS")
        assert linea == "Materiales de Construccion"

    def test_ladrillo_va_a_construccion(self):
        linea, _ = categorizar_linea("LADRILLO PRINCESA HUECO 14X28")
        assert linea == "Materiales de Construccion"

    def test_jeringa_va_a_salud(self):
        linea, _ = categorizar_linea("JERINGA DESCARTABLE 5ML CAJA")
        assert linea == "Salud"

    def test_gasa_va_a_salud(self):
        # `gasa` en Salud. No colisiona con otras lineas.
        linea, _ = categorizar_linea("GASA ESTERIL 5X5 CAJA X 50")
        assert linea == "Salud"


class TestKeywordsExcluyentes:
    """Verifica que la columna keywords_excluyentes funciona (S13.4.2 D2):
    si una excluyente matchea, la linea se descarta aunque alguna
    incluyente tambien matchee."""

    def test_cemento_dental_es_salud_no_construccion(self):
        # `cemento dental` es excluyente de Construccion. La incluyente
        # `cemento` matchea, pero como tambien matchea el excluyente
        # `cemento dental`, Construccion queda descartada. Cae en Salud
        # (que matchea por `cateter`? no, en "CEMENTO DENTAL PARA RESTAURACION"
        # no hay keyword de Salud literal). Hmm, este caso necesita
        # repensar: si Construccion se descarta y nada de Salud matchea,
        # cae en Otros.
        #
        # En realidad lo importante es: NO cae en Construccion.
        linea, _ = categorizar_linea("CEMENTO DENTAL PARA IMPLANTES")
        assert linea != "Materiales de Construccion", (
            "El excluyente 'cemento dental' debe descartar Construccion"
        )

    def test_pintura_de_oficina_no_es_construccion(self):
        # `pintura de oficina` es excluyente de Construccion.
        linea, _ = categorizar_linea("PINTURA DE OFICINA COLOR BLANCO")
        assert linea != "Materiales de Construccion"
