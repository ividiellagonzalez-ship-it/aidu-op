"""Tests S13.4.3.1 - persistencia incremental + idempotencia del script
de reclasificacion semantica.

Cubre tres invariantes nuevas del script:

1. SELECT idempotente: por defecto solo lee items que aun NO tienen
   clasificacion_metodo='semantic'. Esto permite re-disparar el workflow
   tras un timeout intermedio sin re-procesar items ya completados.

2. --force flag: ignora el filtro y lee TODOS los items.

3. _flush_batch invoca turso_http_client.execute_pipeline con el SQL
   UPDATE correcto y con BATCH_SIZE statements por llamada.

NO pega a Turso real ni a Claude. Mocks-only.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from scripts import s13_4_3_reclasificar_semantico as script


class TestLeerPendientesIdempotente:

    def test_default_filtra_por_clasificacion_metodo(self):
        with patch.object(script.turso_http_client, "query_all",
                          return_value=[]) as mock_q:
            script._leer_pendientes(force=False)
            sql = mock_q.call_args[0][0]
            assert "WHERE" in sql, "SELECT default debe tener WHERE"
            assert "clasificacion_metodo IS NULL" in sql, (
                "SELECT default debe incluir items con metodo NULL"
            )
            assert "clasificacion_metodo != 'semantic'" in sql, (
                "SELECT default debe excluir items ya clasificados semantic"
            )

    def test_force_no_filtra(self):
        with patch.object(script.turso_http_client, "query_all",
                          return_value=[]) as mock_q:
            script._leer_pendientes(force=True)
            sql = mock_q.call_args[0][0]
            assert "WHERE" not in sql, (
                "SELECT --force NO debe tener WHERE (procesa TODOS los items)"
            )

    def test_ambos_seleccionan_mismas_columnas(self):
        # El zip(rows, ...) downstream asume orden y cantidad fija de cols.
        with patch.object(script.turso_http_client, "query_all",
                          return_value=[]) as mock_q:
            script._leer_pendientes(force=False)
            sql_default = mock_q.call_args[0][0]
            script._leer_pendientes(force=True)
            sql_force = mock_q.call_args[0][0]
            # Mismas columnas, mismo orden.
            cols_clause_default = sql_default.split("FROM")[0]
            cols_clause_force = sql_force.split("FROM")[0]
            assert cols_clause_default == cols_clause_force


class TestFlushBatch:

    def test_flush_vacio_no_hace_nada(self):
        with patch.object(script.turso_http_client,
                          "execute_pipeline") as mock_exec:
            n = script._flush_batch([], "2026-05-24 00:00:00")
            assert n == 0
            assert not mock_exec.called

    def test_flush_genera_un_statement_por_cambio(self):
        cambios = [
            (1, "Otros", "Salud", True, 0.9, "razon a", "semantic"),
            (2, "Otros", "Aseo", False, 0.7, "razon b", "semantic"),
            (3, "Otros", "Oficina", None, 0.3, "razon c", "keyword"),
        ]
        with patch.object(script.turso_http_client,
                          "execute_pipeline") as mock_exec:
            n = script._flush_batch(cambios, "2026-05-24 00:00:00")
            assert n == 3
            assert mock_exec.called
            statements, = mock_exec.call_args[0]
            assert len(statements) == 3
            for stmt in statements:
                assert "UPDATE inteligencia_precios" in stmt["sql"]
                assert "WHERE id_item = ?" in stmt["sql"]
                # 7 SET cols + 1 WHERE = 8 args
                assert len(stmt["args"]) == 8

    def test_granular_true_se_codifica_como_1(self):
        cambios = [(1, "Otros", "Salud", True, 0.9, "x", "semantic")]
        with patch.object(script.turso_http_client,
                          "execute_pipeline") as mock_exec:
            script._flush_batch(cambios, "2026-05-24 00:00:00")
            stmt = mock_exec.call_args[0][0][0]
            # Posicion 2 del args (linea_nueva, linea_anterior, granular, ...)
            granular_arg = stmt["args"][2]
            assert granular_arg["type"] == "integer"
            assert granular_arg["value"] == "1"

    def test_granular_false_se_codifica_como_0(self):
        cambios = [(1, "Otros", "Salud", False, 0.9, "x", "semantic")]
        with patch.object(script.turso_http_client,
                          "execute_pipeline") as mock_exec:
            script._flush_batch(cambios, "2026-05-24 00:00:00")
            granular_arg = mock_exec.call_args[0][0][0]["args"][2]
            assert granular_arg["type"] == "integer"
            assert granular_arg["value"] == "0"

    def test_granular_none_se_codifica_como_null(self):
        cambios = [(1, "Otros", "Salud", None, 0.9, "x", "semantic")]
        with patch.object(script.turso_http_client,
                          "execute_pipeline") as mock_exec:
            script._flush_batch(cambios, "2026-05-24 00:00:00")
            granular_arg = mock_exec.call_args[0][0][0]["args"][2]
            assert granular_arg["type"] == "null"


class TestBatchSizeConstante:
    """BATCH_SIZE define cada cuantos items se flushea. Si baja a 1, el
    workflow se vuelve costoso (1 round-trip por item). Si sube > 200,
    Turso puede rechazar el pipeline. Sanity check del valor."""

    def test_batch_size_razonable(self):
        assert 10 <= script.BATCH_SIZE <= 200
