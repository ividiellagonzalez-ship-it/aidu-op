"""Tests S13.4.3 - es_producto_granular: casos golden contrato marco vs
producto fisico vs obra vs servicio.

NO pega a la API real. Mockea respuestas que Claude DEBERIA dar para
cada caso golden segun el prompt del spec. Si en produccion Claude da
una respuesta distinta, eso es un problema del prompt (revisar y ajustar)
no del codigo del modulo clasificador.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core import clasificador_semantico as cs


def _mock_respuesta(linea: str, granular: bool, conf: float = 0.9, razon: str = "test"):
    return {
        "linea": linea, "es_producto_granular": granular,
        "confidence": conf, "razon": razon,
    }


@pytest.mark.parametrize("descripcion, expected_linea, expected_granular", [
    # PRODUCTO GRANULAR — items fisicos con precio unitario accionable
    ("AGUJA HIPODERMICA 21G CAJA POR 100", "Salud", True),
    ("RESMA DE PAPEL CARTA 75 GR", "Oficina", True),
    ("BOLSA DE CEMENTO 25KG", "Materiales de Construccion", True),

    # NO GRANULAR — contrato marco
    ("Contrato de Suministros de Tintas y Toner por 2 anos", "Oficina", False),
    ("CONVENIO MARCO DE SUMINISTRO DE ARTICULOS DE ASEO", "Aseo", False),

    # NO GRANULAR — obra de construccion
    ("Construccion Hito de Bienvenida Plaza Comunal", "Materiales de Construccion", False),
    ("Mejoramiento Plaza Poblacion Juntos por El Progreso", "Materiales de Construccion", False),

    # NO GRANULAR — estudio
    ("Estudio de Factibilidad Tecnica Alcantarillado", "Materiales de Construccion", False),

    # NO GRANULAR — servicio sin grano fisico
    ("Servicio Tecnico y/o Profesional para Implementacion Programa", "Otros", False),
    ("Servicios de Mensajeria Despacho de Correspondencia", "Otros", False),
])
class TestCasosGolden:

    def test_clasificacion_y_granular(self, descripcion, expected_linea, expected_granular):
        respuesta = _mock_respuesta(expected_linea, expected_granular)
        with patch.object(cs, "llamar_claude_json", return_value=respuesta):
            res = cs.clasificar_via_claude(descripcion, "Organismo test")
            assert res["linea"] == expected_linea, (
                f"Esperaba linea {expected_linea} para {descripcion!r}, "
                f"obtuve {res['linea']}"
            )
            assert res["es_producto_granular"] == expected_granular, (
                f"Esperaba granular={expected_granular} para {descripcion!r}, "
                f"obtuve {res['es_producto_granular']}"
            )


class TestGranularNullValido:
    """es_producto_granular puede ser None cuando Claude no esta seguro
    o cuando la descripcion es ambigua. El modulo debe propagarlo sin
    forzar a True/False."""

    def test_granular_null_se_propaga(self):
        respuesta = {
            "linea": "Otros", "es_producto_granular": None,
            "confidence": 0.4, "razon": "ambiguo",
        }
        with patch.object(cs, "llamar_claude_json", return_value=respuesta):
            res = cs.clasificar_via_claude("CONTRATACION DE TECNICO PROFESIONAL", "ORG")
            assert res["es_producto_granular"] is None
