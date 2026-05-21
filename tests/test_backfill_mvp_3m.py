"""
Tests del backfill MVP S12.3 v2.2 — CLI, dispatcher de fases, exit codes.

Estrategia
----------
- Sin red: monkeypatch sobre `MercadoPublicoClient` y
  `turso_http_client.execute_pipeline`/`query_all`/`query_one`.
- Sin SQLite: el path HTTP siempre se activa (env vars seteadas).
- Sin subprocess: `_main(argv=...)` devuelve int.

Cobertura
---------
- TestCLIArgs: parsing, defaults, fechas inválidas.
- TestExitCodes: 0/1/2/3 con cada tipo de excepción.
- TestDispatcherFases: orden estricto, dependencias entre fases.
- TestPersistirHTTP: lo que el path HTTP escribe a Turso, batches.
- TestRegionesYTipos: helpers de filtrado, mapping codigo→nombre.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.api.mercadopublico import (
    filtrar_por_region, filtrar_por_tipo, TIPOS_VALIDOS,
)
from app.core import backfill_fases_mvp as orq
from app.core.backfill_fases_mvp import (
    BackfillMvpError, FASES_DEFAULT, REGIONES_CODIGO_A_NOMBRE,
    ejecutar_backfill_mvp, resolver_regiones,
)
from app.core.descarga_diaria import MercadoPublicoAPIError
from app.db.exceptions import TursoUnavailableError
from scripts.backfill_mvp_3m import _main


@pytest.fixture(autouse=True)
def _aislar_env(monkeypatch):
    """Default: sin credenciales Turso. Tests que las necesiten las setean."""
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)


@pytest.fixture
def turso_configurado(monkeypatch):
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://test.aws-us-east-2.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "test-token-mvp")


@pytest.fixture
def mock_http(monkeypatch, turso_configurado):
    """
    Mock de turso_http_client. Captura pipelines y responde a queries
    con valores configurables vía `responses`.
    """
    from app.db import turso_http_client as thc

    captured = {
        "pipelines": [],
        "queries": [],
        "responses": {},  # marker_substring → rows o int
    }

    def _execute(statements, *, timeout=60.0):
        captured["pipelines"].append(list(statements))
        return [{"type": "ok"} for _ in statements]

    def _query_all(sql, args=None):
        captured["queries"].append((sql, args))
        for marker, rows in captured["responses"].items():
            if marker in sql:
                return rows
        return []

    def _query_one(sql, args=None):
        captured["queries"].append((sql, args))
        for marker, rows in captured["responses"].items():
            if marker in sql:
                if isinstance(rows, int):
                    return [rows]
                if rows:
                    return rows[0]
        return None

    monkeypatch.setattr(thc, "execute_pipeline", _execute)
    monkeypatch.setattr(thc, "query_all", _query_all)
    monkeypatch.setattr(thc, "query_one", _query_one)
    monkeypatch.setattr(orq.turso_http_client, "execute_pipeline", _execute)
    monkeypatch.setattr(orq.turso_http_client, "query_all", _query_all)
    monkeypatch.setattr(orq.turso_http_client, "query_one", _query_one)
    return captured


@pytest.fixture
def mock_mp_client(monkeypatch):
    """Cliente MP fake parametrizable."""
    store = {"adj": [], "vig": [], "agil": []}

    class _Fake:
        def __init__(self, *args, **kwargs):
            pass

        def listar_adjudicadas_por_fecha(self, fecha):
            return list(store["adj"])

        def listar_vigentes_por_fecha(self, fecha):
            return list(store["vig"])

        def listar_agiles_por_fecha(self, fecha):
            return list(store["agil"])

        def descargar_vigentes_recientes(self, dias_atras=7):
            return list(store["vig"])

        def listar_agiles_recientes(self, dias_atras=7):
            return list(store["agil"])

    # Reemplazar en TODOS los módulos que lo importan.
    from app.api import mercadopublico as mp_mod
    from app.core import descarga_historica as hist_mod
    monkeypatch.setattr(mp_mod, "MercadoPublicoClient", _Fake)
    monkeypatch.setattr(hist_mod, "MercadoPublicoClient", _Fake)
    return store


# ============================================================
# CLI arguments
# ============================================================
class TestCLIArgs:
    def test_help_no_levanta(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _main(["--help"])
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "Backfill MVP S12.3 v2.2" in out
        assert "--fecha-desde" in out
        assert "--regiones" in out

    def test_fecha_invalida_levanta_argparse_error(self, capsys):
        with pytest.raises(SystemExit) as exc:
            _main(["--fecha-desde", "no-es-fecha"])
        # argparse devuelve 2 para argumentos inválidos.
        assert exc.value.code == 2
        err = capsys.readouterr().err
        assert "Fecha inválida" in err

    def test_fecha_desde_mayor_que_hasta_es_exit_3(self, capsys):
        """Validación post-parse: --fecha-desde > --fecha-hasta es bug del operador."""
        rc = _main([
            "--fecha-desde", "2026-05-10",
            "--fecha-hasta", "2026-02-10",
            "--dry-run",
        ])
        assert rc == 3
        err = capsys.readouterr().err
        assert "--fecha-desde" in err

    def test_dry_run_no_toca_turso(self, capsys, mock_mp_client):
        """Dry-run completa OK sin credenciales y sin red."""
        rc = _main([
            "--fecha-desde", "2026-05-09",
            "--fecha-hasta", "2026-05-09",
            "--dry-run",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "Resultado por fase" in out

    def test_fases_subset(self, mock_mp_client, mock_http):
        """`--fases cabecera,vigentes` solo ejecuta esas dos."""
        out = ejecutar_backfill_mvp(
            fecha_desde=date(2026, 5, 9),
            fecha_hasta=date(2026, 5, 9),
            regiones_codigos=["RM"],
            tipos=["CA"],
            fases=["cabecera", "vigentes"],
            dry_run=False,
        )
        assert "fase_1_cabecera" in out
        assert "fase_6_vigentes" in out
        assert "fase_2_items_producto" not in out
        assert "fase_4_catalogos" not in out


# ============================================================
# Exit codes
# ============================================================
class TestExitCodes:
    def test_exit_0_descarga_exitosa(self, monkeypatch, capsys, turso_configurado, mock_http, mock_mp_client):
        """Path feliz: sin licitaciones, todas las fases corren OK."""
        rc = _main([
            "--fecha-desde", "2026-05-09",
            "--fecha-hasta", "2026-05-09",
            "--regiones", "RM",
            "--tipos", "CA",
        ])
        assert rc == 0

    def test_exit_2_turso_unavailable(self, monkeypatch, turso_configurado):
        """Si execute_pipeline levanta TursoUnavailableError → exit 2."""
        def _fail(**kw):
            raise TursoUnavailableError(
                "transport down", intentos=3, ultimo_error="HTTP 503",
            )
        # IMPORTANTE: monkeypatchear en el módulo del script (donde se hizo
        # el `from app.core.backfill_fases_mvp import ejecutar_backfill_mvp`),
        # no en `orq` — ese tiene su propia referencia que el script ya
        # importó. Sin esto, el test corre el código real y hace requests
        # HTTP reales a la API MP (15+ segundos).
        monkeypatch.setattr(
            "scripts.backfill_mvp_3m.ejecutar_backfill_mvp", _fail,
        )
        rc = _main([
            "--fecha-desde", "2026-05-09",
            "--fecha-hasta", "2026-05-09",
        ])
        assert rc == 2

    def test_exit_1_api_mercadopublico(self, monkeypatch, turso_configurado):
        """Si la API MP falla → MercadoPublicoAPIError → exit 1."""
        def _fail(**kw):
            raise MercadoPublicoAPIError("rate limit excedido")
        monkeypatch.setattr(
            "scripts.backfill_mvp_3m.ejecutar_backfill_mvp", _fail,
        )
        rc = _main([
            "--fecha-desde", "2026-05-09",
            "--fecha-hasta", "2026-05-09",
        ])
        assert rc == 1

    def test_exit_3_error_inesperado(self, monkeypatch, turso_configurado, capsys):
        """Excepción no clasificada → traceback + exit 3."""
        def _bug(**kw):
            raise ValueError("scenario raro")
        monkeypatch.setattr(
            "scripts.backfill_mvp_3m.ejecutar_backfill_mvp", _bug,
        )
        rc = _main([
            "--fecha-desde", "2026-05-09",
            "--fecha-hasta", "2026-05-09",
        ])
        assert rc == 3
        err = capsys.readouterr().err
        assert "Traceback" in err
        assert "ValueError" in err


# ============================================================
# Dispatcher de fases y orden
# ============================================================
class TestDispatcherFases:
    def test_fase_2_no_ejecuta_si_fase_1_aborta(self, monkeypatch, mock_mp_client, mock_http):
        """
        Si Fase 1 levanta BackfillMvpError, Fases 2-5 NO se ejecutan.
        Verifica el contrato del orquestador.
        """
        from app.core import backfill_fases_mvp as orq_mod

        def _fase1_fail(*args, **kwargs):
            # Simular que descargar_rango interno levanta TursoUnavailableError.
            raise TursoUnavailableError("sim", intentos=3, ultimo_error="x")

        monkeypatch.setattr(orq_mod, "descargar_rango", _fase1_fail)

        with pytest.raises(BackfillMvpError) as exc_info:
            ejecutar_backfill_mvp(
                fecha_desde=date(2026, 5, 9),
                fecha_hasta=date(2026, 5, 9),
                regiones_codigos=["RM"],
                tipos=["CA"],
                fases=["cabecera", "items_producto", "items_servicio"],
            )
        assert isinstance(exc_info.value.__cause__, TursoUnavailableError)

    def test_fase_6_vigentes_ejecuta_aunque_4_catalogos_falle(
        self, monkeypatch, mock_mp_client, mock_http,
    ):
        """
        Fase 4 (catálogos) falla → loguea pero NO aborta Fase 5 ni Fase 6.
        Decisión del orquestador: catálogos son derivados, no críticos.
        """
        from app.core import backfill_fases_mvp as orq_mod
        # Mock de descargar_rango para que Fase 1 y Fase 6 sucedan limpio.
        monkeypatch.setattr(orq_mod, "descargar_rango", lambda **kw: {
            "nuevas": 1, "actualizadas": 0, "fallidas": 0,
            "total_vigentes": 0, "total_adjudicadas": 1, "total_agiles": 0,
        })
        # Mock de _recalcular_proveedores_via_http para que falle.
        monkeypatch.setattr(
            orq_mod, "_recalcular_proveedores_via_http",
            lambda: (_ for _ in ()).throw(ValueError("FK constraint hipotético")),
        )

        stats = ejecutar_backfill_mvp(
            fecha_desde=date(2026, 5, 9),
            fecha_hasta=date(2026, 5, 9),
            regiones_codigos=["RM"],
            tipos=["CA"],
        )
        assert "error" in stats["fase_4_catalogos"]
        assert "fase_4_catalogos" in stats["agregado"]["fases_fallidas"]
        # Fase 6 corrió porque es independiente.
        assert "fase_6_vigentes" in stats

    def test_orden_de_fases_es_estricto(self, monkeypatch, mock_mp_client, mock_http):
        """
        Verifica que las fases se ejecuten en el orden canónico
        (cabecera → items_producto → items_servicio → catalogos → adj → vigentes).
        """
        from app.core import backfill_fases_mvp as orq_mod
        orden_observado = []

        def _hook_descargar(**kw):
            if kw.get("incluir_adjudicadas"):
                orden_observado.append("cabecera")
            if kw.get("incluir_vigentes"):
                orden_observado.append("vigentes")
            return {"nuevas": 0, "actualizadas": 0, "fallidas": 0,
                    "total_vigentes": 0, "total_adjudicadas": 0, "total_agiles": 0}

        monkeypatch.setattr(orq_mod, "descargar_rango", _hook_descargar)
        monkeypatch.setattr(orq_mod, "_recalcular_proveedores_via_http", lambda: 0)

        stats = ejecutar_backfill_mvp(
            fecha_desde=date(2026, 5, 9),
            fecha_hasta=date(2026, 5, 9),
            regiones_codigos=["RM"],
            tipos=["CA"],
        )
        # cabecera precede vigentes.
        assert orden_observado == ["cabecera", "vigentes"]
        # Todas las fases en `agregado.fases_ejecutadas`.
        assert set(stats["agregado"]["fases_ejecutadas"]) == set(FASES_DEFAULT)


# ============================================================
# Path HTTP de _persistir_licitaciones
# ============================================================
class TestPersistirHTTP:
    def test_marca_tipo_origen_servicio_para_LE(self, monkeypatch, turso_configurado, mock_http):
        """
        Una licitación con Tipo='LE' debe generar items con tipo_origen='servicio'.
        Activo principal del MVP (criterio #3).
        """
        from app.core import descarga_historica as hist
        licitacion_le = {
            "CodigoExterno": "LE-TEST-001",
            "Nombre": "Consultoría",
            "Tipo": "LE",
            "Items": {"Listado": [
                {"Correlativo": 1, "NombreProducto": "Servicio consultor"},
            ]},
            "Comprador": {"NombreOrganismo": "Org X"},
        }
        hist._persistir_licitaciones_http([licitacion_le], "mp_licitaciones_adj", "test")

        # Buscar el INSERT a mp_licitaciones_items y verificar que el último
        # arg (tipo_origen) es 'servicio'.
        item_inserts = [
            stmt
            for batch in mock_http["pipelines"]
            for stmt in batch
            if "INSERT OR IGNORE INTO mp_licitaciones_items" in stmt["sql"]
        ]
        assert len(item_inserts) == 1, f"esperaba 1 item insert, got {len(item_inserts)}"
        args = item_inserts[0]["args"]
        tipo_origen_arg = args[-1]  # última columna en el INSERT
        # arg_for_value produce {"type": "text", "value": "servicio"}
        assert tipo_origen_arg["value"] == "servicio"

    def test_marca_tipo_origen_producto_para_AGIL(self, monkeypatch, turso_configurado, mock_http):
        """CA/AGIL/L1/otros → tipo_origen='producto'."""
        from app.core import descarga_historica as hist
        licitacion_agil = {
            "CodigoExterno": "AGIL-TEST-002",
            "Nombre": "Compra ágil",
            "Tipo": "AGIL",
            "Items": {"Listado": [
                {"Correlativo": 1, "NombreProducto": "Papel bond A4"},
            ]},
            "Comprador": {"NombreOrganismo": "Org Y"},
        }
        hist._persistir_licitaciones_http([licitacion_agil], "mp_licitaciones_adj", "test")

        item_inserts = [
            stmt
            for batch in mock_http["pipelines"]
            for stmt in batch
            if "INSERT OR IGNORE INTO mp_licitaciones_items" in stmt["sql"]
        ]
        args = item_inserts[0]["args"]
        assert args[-1]["value"] == "producto"

    def test_idempotencia_con_insert_or_ignore(self, monkeypatch, turso_configurado, mock_http):
        """El SQL emitido debe usar INSERT OR IGNORE (NO INSERT plano)."""
        from app.core import descarga_historica as hist
        hist._persistir_licitaciones_http(
            [{"CodigoExterno": "T-001", "Nombre": "x", "Tipo": "L1",
              "Comprador": {}, "Items": {"Listado": []}}],
            "mp_licitaciones_adj", "test",
        )
        all_sql = " || ".join(
            stmt["sql"]
            for batch in mock_http["pipelines"]
            for stmt in batch
        )
        assert "INSERT OR IGNORE INTO mp_licitaciones_adj" in all_sql

    def test_bulk_check_existencia_usa_in_clause(self, monkeypatch, turso_configurado, mock_http):
        """Lookup de existentes hace WHERE codigo_externo IN (...), no N queries."""
        from app.core import descarga_historica as hist
        licitaciones = [
            {"CodigoExterno": f"T-{i:03d}", "Nombre": "x", "Tipo": "L1",
             "Comprador": {}, "Items": {"Listado": []}}
            for i in range(10)
        ]
        hist._persistir_licitaciones_http(licitaciones, "mp_licitaciones_adj", "test")

        # Debe haber exactamente 1 query de bulk check (con 10 placeholders).
        bulk_queries = [
            (sql, args) for sql, args in mock_http["queries"]
            if "WHERE codigo_externo IN" in sql
        ]
        assert len(bulk_queries) == 1
        assert bulk_queries[0][1] is not None
        assert len(bulk_queries[0][1]) == 10

    def test_path_http_solo_cabeceras(self, turso_configurado):
        """
        El path HTTP solo acepta cabeceras (mp_licitaciones_vigentes o
        mp_licitaciones_adj). Una tabla distinta levanta ValueError.
        """
        from app.core import descarga_historica as hist
        with pytest.raises(ValueError) as exc:
            hist._persistir_licitaciones_http(
                [{"CodigoExterno": "X", "Nombre": "y", "Tipo": "L1"}],
                "mp_licitaciones_items",  # no es cabecera
                "test",
            )
        assert "solo acepta cabeceras" in str(exc.value)

    def test_use_http_client_false_no_dispatch_a_http(self, monkeypatch, capsys, tmp_path):
        """
        El default `use_http_client=False` NO llama al path HTTP.
        Verifica backward compatibility con UI Streamlit y refresh_cierres.
        """
        from app.core import descarga_historica as hist

        # Si por error se dispatcha a HTTP, este monkeypatch lo cazaría.
        def _no_se_debe_llamar(*a, **k):
            pytest.fail("_persistir_licitaciones_http NO debería llamarse cuando use_http_client=False")

        monkeypatch.setattr(hist, "_persistir_licitaciones_http", _no_se_debe_llamar)

        # Path SQLite: necesita BD real. Solo verificamos que NO entra al HTTP.
        # Lista vacía → return temprano sin tocar BD.
        result = hist._persistir_licitaciones([], "mp_licitaciones_vigentes", "test")
        assert result["nuevas"] == 0


# ============================================================
# Helpers de filtrado por tipo / región
# ============================================================
class TestRegionesYTipos:
    def test_resolver_regiones_5_target(self):
        nombres = resolver_regiones(["II", "V", "RM", "VI", "X"])
        assert nombres == ["Antofagasta", "Valparaíso", "Metropolitana",
                           "O'Higgins", "Los Lagos"]

    def test_resolver_regiones_desconocida_pass_through(self):
        """Códigos desconocidos se pasan literal (con warning logged)."""
        out = resolver_regiones(["XX-no-existe"])
        assert out == ["XX-no-existe"]

    def test_filtrar_por_tipo_CA_es_alias_de_AGIL(self):
        licitaciones = [
            {"CodigoExterno": "A", "Tipo": "AGIL"},
            {"CodigoExterno": "B", "Tipo": "L1"},
            {"CodigoExterno": "C", "Tipo": "LE"},
        ]
        # Pedir CA debería devolver AGIL.
        out = filtrar_por_tipo(licitaciones, ["CA"])
        assert [l["CodigoExterno"] for l in out] == ["A"]

    def test_filtrar_por_tipo_CA_L1_LE(self):
        licitaciones = [
            {"CodigoExterno": "A", "Tipo": "AGIL"},
            {"CodigoExterno": "B", "Tipo": "L1"},
            {"CodigoExterno": "C", "Tipo": "LE"},
            {"CodigoExterno": "D", "Tipo": "LP"},  # se filtra fuera
        ]
        out = filtrar_por_tipo(licitaciones, ["CA", "L1", "LE"])
        assert {l["CodigoExterno"] for l in out} == {"A", "B", "C"}

    def test_filtrar_por_region_substring_lower_case(self):
        licitaciones = [
            {"Comprador": {"RegionUnidad": "Región Metropolitana de Santiago"}},
            {"Comprador": {"RegionUnidad": "del Libertador General Bernardo O'Higgins"}},
            {"Comprador": {"RegionUnidad": "Antofagasta"}},
            {"Comprador": {"RegionUnidad": "Magallanes"}},
        ]
        out = filtrar_por_region(
            licitaciones,
            ["Metropolitana", "O'Higgins", "Antofagasta", "Valparaíso", "Los Lagos"],
        )
        assert len(out) == 3  # las 3 primeras matchean; Magallanes no.

    def test_filtrar_lista_vacia_pass_through(self):
        licitaciones = [{"Tipo": "L1"}]
        # Sin filtros: devuelve todo.
        assert filtrar_por_tipo(licitaciones, []) == licitaciones
        assert filtrar_por_region(licitaciones, []) == licitaciones

    def test_tipos_validos_incluye_canon_y_alias(self):
        # Sanity check del set público.
        assert "AGIL" in TIPOS_VALIDOS
        assert "CA" in TIPOS_VALIDOS
        assert "L1" in TIPOS_VALIDOS
        assert "LE" in TIPOS_VALIDOS


# ============================================================
# Anti-regresión S12.2.1: backfill MVP no escribe a SQLite local
# ============================================================
class TestAntiRegresionSQLite:
    def test_path_http_no_llama_get_connection(self, monkeypatch, turso_configurado, mock_http):
        """
        `_persistir_licitaciones_http` NO debe llamar a get_connection().
        Cualquier sqlite3.connect en este path reintroduciría el bug
        del Run #3 (datos perdidos en runner efímero).
        """
        from app.core import descarga_historica as hist

        def _no_llamar(*a, **k):
            pytest.fail("get_connection NO debe usarse en path HTTP del backfill MVP")
        monkeypatch.setattr(hist, "get_connection", _no_llamar)

        # Debe completar sin tocar SQLite.
        out = hist._persistir_licitaciones_http(
            [{"CodigoExterno": "T", "Nombre": "x", "Tipo": "L1",
              "Comprador": {}, "Items": {"Listado": []}}],
            "mp_licitaciones_adj", "test",
        )
        assert out["nuevas"] == 1
