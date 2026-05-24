"""Tests S13.5 - iteracion de rango de fechas y nuevos stats.

Cubre:
- `ingerir_rango` itera dia a dia, fecha_desde y fecha_hasta inclusivos.
- `fecha_desde > fecha_hasta` levanta ValueError.
- Stats reportadas: dias_procesados, n_listados_total,
  n_filtrados_por_unit, n_skip_idempotente, n_llamadas_semanticas,
  costo_claude_usd, tiempo_total_seg.
- usar_semantico=True thread-through a categorizar_item.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.core import ingesta_inteligencia_precios as ing
from app.core.ingesta_inteligencia_precios import (
    StatsCorrida,
    ingerir_rango,
)


def _detalle_ok_ohiggins(codigo: str = "1627-9-LE26"):
    return {"Listado": [{
        "CodigoExterno": codigo,
        "Tipo": "LE",
        "Comprador": {
            "NombreOrganismo": "SERVICIO DE SALUD HOSPITAL X",
            "RegionUnidad": "Region del Libertador General Bernardo O´Higgins",
        },
        "Items": {"Listado": [{
            "Correlativo": 1, "Descripcion": "ITEM TEST",
            "Cantidad": 5, "UnidadMedida": "un",
            "Adjudicacion": {
                "MontoUnitario": 1000.0, "Cantidad": 5,
                "NombreProveedor": "P", "RutProveedor": "R",
            },
        }]},
    }]}


class TestIteracionRangoFechas:

    def test_un_solo_dia(self):
        fake_cli = MagicMock()
        fake_cli.listar_adjudicadas_por_fecha = MagicMock(return_value=[])
        fake_cli.detalle_licitacion = MagicMock(return_value=None)
        with patch.object(ing, "cargar_unit_codes_validos", return_value=set()):
            stats = ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="test", cliente=fake_cli,
            )
        assert stats.dias_procesados == 1
        # Solo se llama listar_adjudicadas_por_fecha 1 vez (1 dia).
        assert fake_cli.listar_adjudicadas_por_fecha.call_count == 1

    def test_rango_inclusivo_ambos_extremos(self):
        fake_cli = MagicMock()
        fake_cli.listar_adjudicadas_por_fecha = MagicMock(return_value=[])
        fake_cli.detalle_licitacion = MagicMock(return_value=None)
        with patch.object(ing, "cargar_unit_codes_validos", return_value=set()):
            stats = ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 7),
                lote_id="test", cliente=fake_cli,
            )
        # 1, 2, 3, 4, 5, 6, 7 = 7 dias
        assert stats.dias_procesados == 7
        assert fake_cli.listar_adjudicadas_por_fecha.call_count == 7

    def test_febrero_2026_completo_28_dias(self):
        """Feb 2026 no es bisiesto: 28 dias."""
        fake_cli = MagicMock()
        fake_cli.listar_adjudicadas_por_fecha = MagicMock(return_value=[])
        fake_cli.detalle_licitacion = MagicMock(return_value=None)
        with patch.object(ing, "cargar_unit_codes_validos", return_value=set()):
            stats = ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 28),
                lote_id="backfill_feb2026", cliente=fake_cli,
            )
        assert stats.dias_procesados == 28

    def test_fecha_desde_mayor_que_hasta_levanta_value_error(self):
        with pytest.raises(ValueError, match="fecha_desde"):
            ingerir_rango(
                fecha_desde=date(2026, 2, 28), fecha_hasta=date(2026, 2, 1),
                lote_id="bad",
            )


def _fake_categorizar_factory(metodo: str = "keyword"):
    """Crea un mock de categorizar_item que llena las claves que el
    loop interno espera leer."""
    def _fake(it, catalog=None, **kw):
        it["linea_aidu"] = "Otros"
        it["tipo_objeto"] = "producto"
        it["keywords_matched"] = ""
        it["es_producto_granular"] = None
        it["confidence_score"] = 0.0
        it["clasificacion_metodo"] = metodo
        return it
    return _fake


class TestUsarSemanticoThreadThrough:

    def test_usar_semantico_true_se_propaga_a_categorizar_item(self):
        """Validar que el flag llega a categorizar_item via el loop."""
        fake_cli = MagicMock()
        fake_cli.listar_adjudicadas_por_fecha = MagicMock(
            return_value=[{"CodigoExterno": "1627-9-LE26"}]
        )
        fake_cli.detalle_licitacion = MagicMock(
            return_value=_detalle_ok_ohiggins("1627-9-LE26")
        )

        with patch.object(ing, "categorizar_item",
                          side_effect=_fake_categorizar_factory()) as mock_cat, \
             patch.object(ing, "cargar_unit_codes_validos",
                          return_value={"1627"}), \
             patch.object(ing, "persistir_lote", return_value=1):
            ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="backfill", cliente=fake_cli,
                usar_semantico=True,
                codigos_existentes_override=set(),
            )

        assert mock_cat.called
        # Validar que se llamo con usar_semantico=True
        _, kwargs = mock_cat.call_args
        assert kwargs.get("usar_semantico") is True

    def test_usar_semantico_false_es_default_y_se_propaga(self):
        """Cron diario sigue lexical: NO debe activar Claude."""
        fake_cli = MagicMock()
        fake_cli.listar_adjudicadas_por_fecha = MagicMock(
            return_value=[{"CodigoExterno": "1627-9-LE26"}]
        )
        fake_cli.detalle_licitacion = MagicMock(
            return_value=_detalle_ok_ohiggins("1627-9-LE26")
        )

        with patch.object(ing, "categorizar_item",
                          side_effect=_fake_categorizar_factory()) as mock_cat, \
             patch.object(ing, "cargar_unit_codes_validos",
                          return_value={"1627"}), \
             patch.object(ing, "persistir_lote", return_value=1):
            ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="cron", cliente=fake_cli,
                # usar_semantico=False es default
            )

        assert mock_cat.called
        _, kwargs = mock_cat.call_args
        assert kwargs.get("usar_semantico") is False, (
            "Default del cron diario debe ser lexical (no incurrir costo Claude)"
        )


class TestStatsCorridaCamposNuevos:

    def test_stats_corrida_tiene_campos_nuevos_s13_5(self):
        s = StatsCorrida()
        # Campos viejos siguen ahi.
        assert s.dias_procesados == 0
        assert s.n_listados_total == 0
        # Nuevos campos S13.5.
        assert s.n_skip_idempotente == 0
        assert s.n_llamadas_semanticas == 0
        assert s.costo_claude_usd == 0.0
        assert s.aborted_cost_guard is False

    def test_costo_claude_usd_se_calcula_al_cierre(self):
        """Al final del run, costo_claude_usd = _estimar_costo_claude(n_llamadas_semanticas)."""
        fake_cli = MagicMock()
        fake_cli.listar_adjudicadas_por_fecha = MagicMock(return_value=[])
        fake_cli.detalle_licitacion = MagicMock(return_value=None)

        with patch.object(ing, "cargar_unit_codes_validos", return_value=set()):
            stats = ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="test", cliente=fake_cli,
            )

        # Sin llamadas semanticas, costo es 0.
        assert stats.n_llamadas_semanticas == 0
        assert stats.costo_claude_usd == 0.0

    def test_n_llamadas_semanticas_cuenta_solo_metodo_semantic(self):
        """Si Claude fallo y se cayo a 'keyword', NO se cuenta como
        llamada semantica para el costo (porque la API no consumio
        token output util)."""
        fake_cli = MagicMock()
        fake_cli.listar_adjudicadas_por_fecha = MagicMock(
            return_value=[{"CodigoExterno": "1627-9-LE26"}]
        )
        fake_cli.detalle_licitacion = MagicMock(
            return_value=_detalle_ok_ohiggins("1627-9-LE26")
        )

        # Mockeamos categorizar_item para que marque metodo='keyword'
        # (simula fallback lexical post-Claude-error).
        def fake_categorizar(it, catalog=None, **kw):
            it["linea_aidu"] = "Otros"
            it["tipo_objeto"] = "producto"
            it["keywords_matched"] = ""
            it["es_producto_granular"] = None
            it["confidence_score"] = 0.0
            it["clasificacion_metodo"] = "keyword"  # NO 'semantic'
            return it

        with patch.object(ing, "categorizar_item",
                          side_effect=fake_categorizar), \
             patch.object(ing, "cargar_unit_codes_validos",
                          return_value={"1627"}), \
             patch.object(ing, "persistir_lote", return_value=1):
            stats = ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="backfill", cliente=fake_cli,
                usar_semantico=True,
                codigos_existentes_override=set(),
            )

        # Fallback a lexical: n_llamadas_semanticas = 0, costo = 0.
        assert stats.n_llamadas_semanticas == 0
        assert stats.costo_claude_usd == 0.0

    def test_n_llamadas_semanticas_cuenta_metodo_semantic(self):
        fake_cli = MagicMock()
        fake_cli.listar_adjudicadas_por_fecha = MagicMock(
            return_value=[{"CodigoExterno": "1627-9-LE26"}]
        )
        fake_cli.detalle_licitacion = MagicMock(
            return_value=_detalle_ok_ohiggins("1627-9-LE26")
        )

        def fake_categorizar(it, catalog=None, **kw):
            it["linea_aidu"] = "Salud"
            it["tipo_objeto"] = "producto"
            it["keywords_matched"] = ""
            it["es_producto_granular"] = True
            it["confidence_score"] = 0.9
            it["clasificacion_metodo"] = "semantic"
            return it

        with patch.object(ing, "categorizar_item",
                          side_effect=fake_categorizar), \
             patch.object(ing, "cargar_unit_codes_validos",
                          return_value={"1627"}), \
             patch.object(ing, "persistir_lote", return_value=1):
            stats = ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="backfill", cliente=fake_cli,
                usar_semantico=True,
                codigos_existentes_override=set(),
            )

        assert stats.n_llamadas_semanticas == 1
        # Costo > 0 (positivo, pequeno)
        assert stats.costo_claude_usd > 0
        assert stats.costo_claude_usd < 0.01  # 1 call = pocos centavos
