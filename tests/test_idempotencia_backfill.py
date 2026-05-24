"""Tests S13.5 - idempotencia del backfill por codigo_mp.

El modo backfill semantico carga al inicio el set de codigos_mp ya
presentes en BD y los saltea: NO pega API MP, NO llama Claude, NO
inserta. Esto evita re-pagar Claude en re-runs y permite que el
workflow se dispare multiples veces sin coste extra.

Cubre:
- SELECT bulk filtra por fecha_adjudicacion +/- buffer.
- SKIP correcto cuando codigo_mp esta en el set.
- Procesamiento normal cuando NO esta en el set.
- Cron diario (usar_semantico=False) NO precarga el set
  (no aplica idempotencia de codigo_mp; mantiene INSERT OR IGNORE).
- Override via codigos_existentes_override (path de testing).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.core import ingesta_inteligencia_precios as ing
from app.core.ingesta_inteligencia_precios import (
    cargar_codigos_existentes,
    ingerir_rango,
)


# ============================================================
# cargar_codigos_existentes: SELECT bulk con buffer +/- N dias
# ============================================================

class TestCargarCodigosExistentes:

    def test_turso_no_configurado_devuelve_set_vacio(self):
        with patch.object(ing.turso_http_client, "is_configured", return_value=False):
            out = cargar_codigos_existentes(
                date(2026, 2, 1), date(2026, 2, 28), buffer_days=30,
            )
            assert out == set()

    def test_query_aplica_buffer_30_dias(self):
        with patch.object(ing.turso_http_client, "is_configured", return_value=True), \
             patch.object(ing.turso_http_client, "query_all", return_value=[]) as mock_q:
            cargar_codigos_existentes(
                date(2026, 2, 1), date(2026, 2, 28), buffer_days=30,
            )
            assert mock_q.called
            args, _ = mock_q.call_args
            sql, params = args[0], args[1]
            assert "fecha_adjudicacion" in sql
            assert "DISTINCT codigo_mp" in sql
            # buffer 30 dias: 2026-02-01 - 30 = 2026-01-02 ; 2026-02-28 + 30 = 2026-03-30
            assert params[0]["value"] == "2026-01-02"
            assert params[1]["value"] == "2026-03-30"

    def test_devuelve_set_no_lista(self):
        rows = [["1627-29-LE26"], ["2107-51-LE26"], ["1627-29-LE26"]]
        with patch.object(ing.turso_http_client, "is_configured", return_value=True), \
             patch.object(ing.turso_http_client, "query_all", return_value=rows):
            out = cargar_codigos_existentes(date(2026, 2, 1), date(2026, 2, 28))
            assert isinstance(out, set)
            assert out == {"1627-29-LE26", "2107-51-LE26"}

    def test_query_fallida_devuelve_set_vacio_sin_crashear(self):
        # Defensa: si Turso falla, el backfill sigue (pero pierde
        # idempotencia y puede re-pagar Claude). Mejor que crashear.
        with patch.object(ing.turso_http_client, "is_configured", return_value=True), \
             patch.object(ing.turso_http_client, "query_all",
                          side_effect=Exception("Turso down")):
            out = cargar_codigos_existentes(date(2026, 2, 1), date(2026, 2, 28))
            assert out == set()


# ============================================================
# ingerir_rango: SKIP por codigo_mp existente
# ============================================================

# Helper: fake MP client que devuelve un listado controlado por dia.
def _make_fake_client(listado_por_dia: dict, detalle_por_codigo: dict):
    cli = MagicMock()
    cli.listar_adjudicadas_por_fecha = MagicMock(
        side_effect=lambda d: listado_por_dia.get(d.isoformat(), [])
    )
    cli.detalle_licitacion = MagicMock(
        side_effect=lambda c: detalle_por_codigo.get(c)
    )
    return cli


class TestSkipIdempotente:

    def test_codigo_en_bd_se_saltea_sin_pegar_detalle(self):
        fake_cli = _make_fake_client(
            listado_por_dia={
                "2026-02-01": [
                    {"CodigoExterno": "1627-29-LE26"},   # YA EN BD
                    {"CodigoExterno": "1627-30-LE26"},   # NUEVO
                ],
            },
            detalle_por_codigo={
                "1627-30-LE26": {"Listado": [{
                    "CodigoExterno": "1627-30-LE26",
                    "Tipo": "LE",
                    "Comprador": {
                        "NombreOrganismo": "SERVICIO DE SALUD HOSPITAL X",
                        "RegionUnidad": "Region del Libertador General Bernardo O´Higgins",
                    },
                    "Items": {"Listado": [{
                        "Correlativo": 1, "Descripcion": "ITEM TEST",
                        "Cantidad": 1, "UnidadMedida": "un",
                        "Adjudicacion": {
                            "MontoUnitario": 1000.0, "Cantidad": 1,
                            "NombreProveedor": "P", "RutProveedor": "R",
                        },
                    }]},
                }]},
            },
        )
        with patch.object(ing, "persistir_lote", return_value=1) as mock_persist, \
             patch.object(ing, "cargar_unit_codes_validos",
                          return_value={"1627"}):
            stats = ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="test", cliente=fake_cli,
                codigos_existentes_override={"1627-29-LE26"},
            )

        # SKIP idempotente disparado para 1627-29-LE26.
        assert stats.n_skip_idempotente == 1
        # Detalle solo se pego para el codigo nuevo.
        assert fake_cli.detalle_licitacion.call_count == 1
        fake_cli.detalle_licitacion.assert_called_with("1627-30-LE26")
        # Y se persistio una vez (el item nuevo).
        assert mock_persist.called

    def test_todos_los_codigos_estan_en_bd_sin_detalle_calls(self):
        """Re-run perfecto post-backfill: 0 detalles pegados, 0 inserts."""
        fake_cli = _make_fake_client(
            listado_por_dia={
                "2026-02-01": [
                    {"CodigoExterno": "1627-29-LE26"},
                    {"CodigoExterno": "1627-30-LE26"},
                ],
            },
            detalle_por_codigo={},
        )
        with patch.object(ing, "persistir_lote", return_value=0) as mock_persist, \
             patch.object(ing, "cargar_unit_codes_validos",
                          return_value={"1627"}):
            stats = ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="test", cliente=fake_cli,
                codigos_existentes_override={"1627-29-LE26", "1627-30-LE26"},
            )

        assert stats.n_skip_idempotente == 2
        assert fake_cli.detalle_licitacion.call_count == 0
        # persistir_lote no se llama porque no hay items.
        assert not mock_persist.called

    def test_cron_diario_no_precarga_codigos_existentes(self):
        """usar_semantico=False (default) NO debe llamar
        cargar_codigos_existentes (mantiene comportamiento cron). La
        idempotencia sigue garantizada via INSERT OR IGNORE en BD."""
        fake_cli = _make_fake_client(
            listado_por_dia={"2026-02-01": []},
            detalle_por_codigo={},
        )
        with patch.object(ing, "cargar_codigos_existentes") as mock_carga, \
             patch.object(ing, "cargar_unit_codes_validos", return_value=set()), \
             patch.object(ing, "persistir_lote", return_value=0):
            ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="cron", cliente=fake_cli,
                # usar_semantico=False (default).
            )
        assert not mock_carga.called, (
            "Cron diario NO debe pegar SELECT bulk de codigos_existentes "
            "(es un costo Turso innecesario en el path lexical)."
        )

    def test_modo_backfill_llama_cargar_codigos_existentes(self):
        fake_cli = _make_fake_client(
            listado_por_dia={"2026-02-01": []},
            detalle_por_codigo={},
        )
        with patch.object(ing, "cargar_codigos_existentes",
                          return_value=set()) as mock_carga, \
             patch.object(ing, "cargar_unit_codes_validos", return_value=set()), \
             patch.object(ing, "persistir_lote", return_value=0):
            ingerir_rango(
                fecha_desde=date(2026, 2, 1), fecha_hasta=date(2026, 2, 1),
                lote_id="backfill", cliente=fake_cli,
                usar_semantico=True,
            )
        assert mock_carga.called, (
            "Backfill semantico DEBE precargar codigos_existentes "
            "para idempotencia + ahorro Claude."
        )
        # buffer_days es kwarg
        _, kwargs = mock_carga.call_args
        assert kwargs.get("buffer_days") == 30


# ============================================================
# Cost guard: abort cuando proyeccion supera tope
# ============================================================

class TestCostGuardBackfill:

    def test_sin_cost_guard_no_aborta_aunque_haya_calls(self):
        """cost_guard_max_usd=None: nunca aborta por costo. Probamos
        que el flag default es False y que el costo crece con N."""
        from app.core.ingesta_inteligencia_precios import (
            _estimar_costo_claude, StatsCorrida,
        )
        # ~$3.15 USD por 1000 calls (input 450tok + output 120tok
        # sonnet-4-5). Cero asercion sobre umbrales — solo que es
        # positivo y plausible.
        c = _estimar_costo_claude(1000)
        assert c > 0
        assert c < 10  # sanity check; si subimos $10/1000 calls algo se rompio.
        s = StatsCorrida()
        assert s.aborted_cost_guard is False

    def test_estimar_costo_claude_lineal_en_n_calls(self):
        from app.core.ingesta_inteligencia_precios import _estimar_costo_claude
        c1 = _estimar_costo_claude(100)
        c2 = _estimar_costo_claude(200)
        # Tolerancia para floats.
        assert abs(c2 - 2 * c1) < 1e-9

    def test_estimar_costo_claude_cero_calls_devuelve_cero(self):
        from app.core.ingesta_inteligencia_precios import _estimar_costo_claude
        assert _estimar_costo_claude(0) == 0.0
        assert _estimar_costo_claude(-5) == 0.0
