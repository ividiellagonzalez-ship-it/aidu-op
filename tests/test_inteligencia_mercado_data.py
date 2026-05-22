"""Tests del data layer de la pantalla Inteligencia de Mercado (S13.2).

Cubre el bypass de libsql + SQLite local introducido para que la pantalla
funcione aunque el SQLite del container de Streamlit Cloud este corrupto.
Mockea turso_http_client.query_all() para evitar hits reales a Turso.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pandas as pd
import pytest

from app.ui import inteligencia_mercado as im


@pytest.fixture(autouse=True)
def _clean_caches():
    """Invalida cache de st.cache_data antes de cada test (los datos
    inyectados via mock cambian entre tests)."""
    try:
        im._cargar_inteligencia_precios.clear()
    except Exception:
        pass
    yield
    try:
        im._cargar_inteligencia_precios.clear()
    except Exception:
        pass


# ============================================================
# DETECCION MODO PRODUCCION
# ============================================================

class TestModoProduccion:

    def test_env_var_seteada_es_produccion(self, monkeypatch):
        monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://demo.turso.io")
        assert im._modo_produccion() is True

    def test_env_var_ausente_no_es_produccion(self, monkeypatch):
        monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
        # Tambien hay que mockear st.secrets (puede no estar configurado)
        with patch.object(im.st, "secrets", create=True) as mock_secrets:
            mock_secrets.get.return_value = None
            assert im._modo_produccion() is False

    def test_st_secrets_sin_env_es_produccion(self, monkeypatch):
        monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
        # Simular Streamlit Cloud antes de cargar el .env: st.secrets tiene
        # la URL pero el env var todavia no.
        with patch.object(im.st, "secrets", create=True) as mock_secrets:
            mock_secrets.get.return_value = "libsql://demo.turso.io"
            assert im._modo_produccion() is True


# ============================================================
# CARGAR INTELIGENCIA - MODO PRODUCCION (TURSO HTTP)
# ============================================================

FILA_SAMPLE = [
    1,                   # id_item
    "1620-9-LE26",       # codigo_mp
    1,                   # correlativo_item
    "2026-05-19",        # fecha_adjudicacion
    "LE",                # tipo_licitacion
    "I MUNICIPALIDAD DE RANCAGUA",  # organismo_comprador
    "1620",              # unit_code
    "Region del Libertador General Bernardo O'Higgins",  # organismo_region
    "Region del Libertador General Bernardo O'Higgins",  # region_entrega
    "BOLSA DE CEMENTO 25KG",  # producto_descripcion
    "un",                # unidad_medida
    100.0,               # cantidad
    3500.0,              # precio_unitario
    350000.0,            # monto_total
    "FERRETERIA SUR LTDA",  # proveedor_nombre
    "77.111.222-3",      # proveedor_rut
    3,                   # n_oferentes
    "Ferreteria",        # linea_aidu
    "producto",          # tipo_objeto
    "cemento",           # keywords_matched
    "backfill_1",        # lote_id
]


class TestCargarInteligenciaProduccion:

    def test_usa_turso_http_cuando_produccion(self, monkeypatch):
        monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://demo.turso.io")
        with patch.object(im.turso_http_client, "query_all", return_value=[FILA_SAMPLE]) as mock_q, \
             patch.object(im, "get_connection") as mock_conn:
            df = im._cargar_inteligencia_precios("2026-05-15", "2026-05-21")
            assert mock_q.called, "turso_http_client.query_all NO fue invocado"
            assert not mock_conn.called, (
                "get_connection NO debe llamarse en modo produccion "
                "(habilitaria fallback a SQLite local potencialmente corrupto)"
            )
            assert len(df) == 1
            assert df.iloc[0]["codigo_mp"] == "1620-9-LE26"
            assert df.iloc[0]["linea_aidu"] == "Ferreteria"

    def test_dataframe_columns_completas(self, monkeypatch):
        monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://demo.turso.io")
        with patch.object(im.turso_http_client, "query_all", return_value=[FILA_SAMPLE]):
            df = im._cargar_inteligencia_precios("2026-05-15", "2026-05-21")
            assert list(df.columns) == im._COLS_INTELIGENCIA
            assert len(df.columns) == 21

    def test_turso_falla_devuelve_df_vacio_con_cols_correctas(self, monkeypatch):
        monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://demo.turso.io")
        with patch.object(im.turso_http_client, "query_all", side_effect=Exception("Turso down")), \
             patch.object(im.st, "warning"):
            df = im._cargar_inteligencia_precios("2026-05-15", "2026-05-21")
            assert df.empty
            # Importante: las columnas siguen presentes asi los filtros de la UI no crashean
            assert list(df.columns) == im._COLS_INTELIGENCIA

    def test_query_pasa_argumentos_correctos(self, monkeypatch):
        monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://demo.turso.io")
        with patch.object(im.turso_http_client, "query_all", return_value=[]) as mock_q:
            im._cargar_inteligencia_precios("2026-04-30", "2026-05-21")
            args, kwargs = mock_q.call_args
            sql, params = args[0], args[1]
            assert "FROM inteligencia_precios" in sql
            assert "fecha_adjudicacion BETWEEN ? AND ?" in sql
            assert len(params) == 2
            # Los params estan en formato Hrana
            assert params[0]["type"] == "text"
            assert params[0]["value"] == "2026-04-30"
            assert params[1]["value"] == "2026-05-21"


# ============================================================
# CARGAR INTELIGENCIA - MODO DEV (FALLBACK A SQLITE)
# ============================================================

class TestCargarInteligenciaDev:

    def test_dev_usa_get_connection_no_turso_http(self, monkeypatch):
        monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
        with patch.object(im.st, "secrets", create=True) as mock_secrets:
            mock_secrets.get.return_value = None
            with patch.object(im, "get_connection") as mock_conn, \
                 patch.object(im.turso_http_client, "query_all") as mock_q:
                # Fake cursor que devuelve una fila igual a la sample
                fake_cursor = type("FC", (), {
                    "description": [(c, None, None, None, None, None, None) for c in im._COLS_INTELIGENCIA],
                    "fetchall": lambda self: [FILA_SAMPLE],
                })()
                mock_conn.return_value.execute.return_value = fake_cursor
                df = im._cargar_inteligencia_precios("2026-05-15", "2026-05-21")
                assert mock_conn.called, "get_connection debe usarse en modo dev"
                assert not mock_q.called, "turso_http_client NO debe llamarse en dev"
                assert len(df) == 1


# ============================================================
# COBERTURA DE COLUMNAS (regresion: si alguien cambia el SELECT
# sin actualizar _COLS_INTELIGENCIA, los downstream filtros rompen).
# ============================================================

class TestColsCoherencia:

    def test_cols_y_select_alineados(self):
        # 21 columnas esperadas en orden estricto
        assert len(im._COLS_INTELIGENCIA) == 21
        for col in im._COLS_INTELIGENCIA:
            assert col in im._SELECT_INTELIGENCIA, (
                f"Columna {col!r} esta en _COLS_INTELIGENCIA pero no aparece "
                f"en el SELECT. El zip(rows, cols) saldria desalineado."
            )

    def test_select_tiene_dos_parametros(self):
        assert im._SELECT_INTELIGENCIA.count("?") == 2
