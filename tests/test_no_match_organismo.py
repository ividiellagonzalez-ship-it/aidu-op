"""Tests sec 4.11 — matching NUNCA usa nombre de organismo (S13.4.2).

Decision del Director (spec sec 1.4): el matching por nombre de
organismo fue rechazado porque genera ~20 falsos positivos sobre
productos legitimos de Aseo/Oficina vendidos a hospitales.

Estos tests pegan al contrato: aunque el comprador sea un hospital,
el clasificador solo mira `producto_descripcion`.
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


class TestNoMatchPorOrganismo:
    """Cada caso lleva la descripcion REAL de un producto de Aseo/Oficina
    que en el universo Lote 1 fue comprado por un hospital. Si el
    clasificador usara el organismo, lo clasificaria como Salud. La
    asercion verifica que NO lo hace."""

    def test_alcohol_gel_dispensador_es_aseo(self):
        # Alcohol gel/jabon de manos: producto legitimo de Aseo, comun
        # en compras hospitalarias. NO debe ser Salud.
        linea, _ = categorizar_linea("ALCOHOL GEL 340 ML CON DISPENSADOR")
        assert linea == "Aseo"

    def test_mopa_industrial_es_aseo(self):
        linea, _ = categorizar_linea("MOPA INDUSTRIAL CON MANGO TELESCOPICO")
        assert linea == "Aseo"

    def test_papel_higienico_doble_hoja_es_aseo(self):
        linea, _ = categorizar_linea("PAPEL HIGIENICO DOBLE HOJA PACK 12")
        assert linea == "Aseo"

    def test_resma_papel_carta_es_oficina(self):
        # Papel carta comprado por Hospital → Oficina, no Salud.
        linea, _ = categorizar_linea("RESMA DE PAPEL CARTA 75 GR HOSPITAL")
        assert linea == "Oficina"

    def test_funcion_solo_recibe_descripcion(self):
        # Defensa estructural: la signatura de categorizar_linea NO acepta
        # un parametro organismo_comprador. Si alguien la agregara en el
        # futuro y empezara a usar el organismo, este test (que no la
        # pasa) seguiria validando solo por descripcion. La intencion del
        # test es de regresion arquitectonica.
        import inspect
        sig = inspect.signature(categorizar_linea)
        params = list(sig.parameters.keys())
        # Solo debe aceptar (descripcion, catalog, conn). NO organismo.
        for p in params:
            assert "organismo" not in p.lower(), (
                f"categorizar_linea acepta parametro {p!r}; matching por "
                "organismo fue rechazado por el Director (spec sec 1.4)."
            )
