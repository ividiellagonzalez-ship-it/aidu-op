"""Tests sec 4.11 spec S13.4.2 — clasificador con 6 lineas + Otros.

Casos representativos uno por linea + Otros residual.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.categorizador_aidu_fast import (
    cargar_catalogo_desde_csv,
    categorizar_linea,
    LINEA_FALLBACK,
    LINEAS_AIDU_FAST,
    PRIORIDAD_LINEAS,
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


class TestSeisLineasYOtros:

    @pytest.mark.parametrize("descripcion,linea_esperada", [
        # Salud: el caso mas representativo es un insumo medico hospitalario
        ("SUJETADOR DE TUBO ENDOTRAQUEAL SE ADAPTA A TAMAÑOS DE TUBOS", "Salud"),
        # Materiales de Construccion: cemento estructural
        ("BOLSA DE CEMENTO PORTLAND TIPO I 25KG", "Materiales de Construccion"),
        # Aseo: detergente clasico
        ("DETERGENTE LIQUIDO LAVALOZA 5 LITROS", "Aseo"),
        # Oficina: resma papel
        ("RESMA DE PAPEL CARTA BLANCO 75 GR", "Oficina"),
        # Ferreteria: herramienta sin colision con Construccion
        ("MARTILLO CARPINTERO 16 OZ", "Ferreteria"),
        # Equipamiento: notebook
        ("NOTEBOOK HP CORE I5 8GB RAM", "Equipamiento"),
    ])
    def test_un_caso_por_linea(self, descripcion, linea_esperada):
        linea, kws = categorizar_linea(descripcion)
        assert linea == linea_esperada, (
            f"Esperaba {linea_esperada} para {descripcion!r}, obtuve {linea}"
        )
        assert kws, "Debe devolver al menos una keyword matcheada"

    def test_descripcion_sin_match_va_a_otros(self):
        # Texto que no contiene ninguna keyword del catalogo de las 6 lineas
        linea, kws = categorizar_linea("VEHICULO MOTORIZADO AUTOMOVIL SEDAN ANO 2026")
        assert linea == LINEA_FALLBACK
        assert kws == []

    def test_prioridad_lineas_completa(self):
        # Las 6 lineas estan en PRIORIDAD_LINEAS y en LINEAS_AIDU_FAST
        assert set(PRIORIDAD_LINEAS) == set(LINEAS_AIDU_FAST)
        assert len(PRIORIDAD_LINEAS) == 6
        # Salud primero, Construccion segundo (mas especificas)
        assert PRIORIDAD_LINEAS[0] == "Salud"
        assert PRIORIDAD_LINEAS[1] == "Materiales de Construccion"
