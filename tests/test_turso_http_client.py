"""
Tests del cliente HTTP /v2/pipeline para Turso (S12.2.2).

Estrategia: mockear `requests.post` con un dummy que devuelve la respuesta
esperada. Verificamos:
  - Construcción correcta del endpoint y headers.
  - Estructura del payload (request envelope con `requests` array y close).
  - Mapeo de fallas de transporte a TursoUnavailableError.
  - Backoff exponencial entre reintentos (tres intentos: 1s, 4s, 16s).
  - Helpers query_all / query_one extraen valores correctamente del
    formato Hrana `{type, value}`.
"""
from __future__ import annotations

import pytest
import requests

from app.db import turso_http_client as thc
from app.db.exceptions import TursoUnavailableError


@pytest.fixture(autouse=True)
def _no_real_sleeps(monkeypatch):
    """
    Reemplaza time.sleep por no-op para que el backoff (1s+4s+16s=21s)
    no haga lentos los tests. Capturamos las duraciones para verificar
    el patrón exponencial cuando lo necesitemos.
    """
    sleeps = []
    monkeypatch.setattr(thc.time, "sleep", lambda s: sleeps.append(s))
    return sleeps


@pytest.fixture(autouse=True)
def _creds_via_env(monkeypatch):
    """
    Setea env vars Turso de prueba para todos los tests excepto los que
    explícitamente las borren.
    """
    monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://test-db.aws-us-east-2.turso.io")
    monkeypatch.setenv("TURSO_AUTH_TOKEN", "test-token-xyz")


def _fake_response(status_code: int, json_body: dict | None = None, text: str = ""):
    """Construye un objeto que cuacks como requests.Response."""
    class _Resp:
        def __init__(self):
            self.status_code = status_code
            self._json = json_body or {}
            self.text = text or (str(json_body) if json_body else "")

        def json(self):
            return self._json

    return _Resp()


class TestIsConfigured:
    def test_con_env_vars(self):
        assert thc.is_configured() is True

    def test_sin_env_vars(self, monkeypatch):
        monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
        monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
        assert thc.is_configured() is False

    def test_url_vacia_no_cuenta(self, monkeypatch):
        monkeypatch.setenv("TURSO_DATABASE_URL", "")
        assert thc.is_configured() is False

    def test_token_vacio_no_cuenta(self, monkeypatch):
        monkeypatch.setenv("TURSO_AUTH_TOKEN", "   ")  # solo whitespace
        assert thc.is_configured() is False


class TestEndpointConstruccion:
    """
    Verifica que la URL libsql:// se transforme correctamente a
    https://.../v2/pipeline y que los headers tengan auth bearer.
    """

    def test_libsql_se_traduce_a_https_y_v2_pipeline(self, monkeypatch):
        capturadas: list = []

        def _fake_post(url, headers, json, timeout):
            capturadas.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
            return _fake_response(200, {"results": []})

        monkeypatch.setattr(thc.requests, "post", _fake_post)
        thc.execute_pipeline([{"sql": "SELECT 1"}])

        assert len(capturadas) == 1
        c = capturadas[0]
        assert c["url"] == "https://test-db.aws-us-east-2.turso.io/v2/pipeline"
        assert c["headers"]["Authorization"] == "Bearer test-token-xyz"
        assert c["headers"]["Content-Type"] == "application/json"

    def test_payload_incluye_close_implicito(self, monkeypatch):
        """El pipeline siempre termina en {type: close} para que Turso libere el contexto."""
        capturadas: list = []
        monkeypatch.setattr(
            thc.requests, "post",
            lambda *a, **k: (capturadas.append(k["json"]), _fake_response(200, {"results": []}))[1],
        )
        thc.execute_pipeline([
            {"sql": "INSERT INTO t VALUES (?)", "args": [{"type": "integer", "value": "1"}]},
            {"sql": "INSERT INTO t VALUES (?)", "args": [{"type": "integer", "value": "2"}]},
        ])
        payload = capturadas[0]
        assert len(payload["requests"]) == 3  # 2 execute + 1 close
        assert payload["requests"][-1] == {"type": "close"}
        assert all(r["type"] == "execute" for r in payload["requests"][:2])


class TestExecutePipelineErrores:
    """
    Verifica que las fallas de transporte (HTTP 4xx/5xx, timeout, conexión)
    se mapeen a TursoUnavailableError después de los 3 reintentos.
    """

    def test_http_500_levanta_tras_3_intentos(self, monkeypatch, _no_real_sleeps):
        intentos = []

        def _post(*args, **kwargs):
            intentos.append(1)
            return _fake_response(500, text="Internal Server Error")

        monkeypatch.setattr(thc.requests, "post", _post)

        with pytest.raises(TursoUnavailableError) as exc_info:
            thc.execute_pipeline([{"sql": "SELECT 1"}])

        assert len(intentos) == thc._HTTP_MAX_INTENTOS == 3
        assert exc_info.value.intentos == 3
        assert "HTTP 500" in exc_info.value.ultimo_error

    def test_backoff_exponencial_entre_intentos(self, monkeypatch, _no_real_sleeps):
        """Verifica el patrón 1s, 4s entre los 3 intentos (sin sleep al final)."""
        monkeypatch.setattr(
            thc.requests, "post",
            lambda *a, **k: _fake_response(503, text="Service Unavailable"),
        )
        with pytest.raises(TursoUnavailableError):
            thc.execute_pipeline([{"sql": "SELECT 1"}])
        # Sleeps esperados: 1.0 (después del intento 1), 4.0 (después del 2),
        # NO sleep después del intento 3 (ya levantó).
        assert _no_real_sleeps == [1.0, 4.0]

    def test_timeout_levanta_tras_3_intentos(self, monkeypatch, _no_real_sleeps):
        def _post(*a, **k):
            raise requests.Timeout("Read timed out")

        monkeypatch.setattr(thc.requests, "post", _post)
        with pytest.raises(TursoUnavailableError) as exc_info:
            thc.execute_pipeline([{"sql": "SELECT 1"}])
        assert "Timeout" in exc_info.value.ultimo_error

    def test_connection_error_levanta(self, monkeypatch, _no_real_sleeps):
        def _post(*a, **k):
            raise requests.ConnectionError("DNS resolution failed")

        monkeypatch.setattr(thc.requests, "post", _post)
        with pytest.raises(TursoUnavailableError) as exc_info:
            thc.execute_pipeline([{"sql": "SELECT 1"}])
        assert "ConnectionError" in exc_info.value.ultimo_error

    def test_recovery_en_segundo_intento(self, monkeypatch, _no_real_sleeps):
        """
        Si el primer intento falla pero el segundo OK, se devuelve el
        resultado del segundo sin levantar.
        """
        respuestas = [
            _fake_response(503, text="transient"),
            _fake_response(200, {"results": [{"type": "ok"}]}),
        ]

        def _post(*a, **k):
            return respuestas.pop(0)

        monkeypatch.setattr(thc.requests, "post", _post)
        out = thc.execute_pipeline([{"sql": "SELECT 1"}])
        assert out == [{"type": "ok"}]
        # Solo un sleep entre los dos intentos.
        assert _no_real_sleeps == [1.0]

    def test_sin_credenciales_levanta_inmediato(self, monkeypatch, _no_real_sleeps):
        """
        Llamar execute_pipeline sin credenciales es un bug del callsite
        (debería haber chequeado is_configured). No se reintenta.
        """
        monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
        monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)
        with pytest.raises(TursoUnavailableError) as exc_info:
            thc.execute_pipeline([{"sql": "SELECT 1"}])
        assert "missing credentials" in exc_info.value.ultimo_error
        assert _no_real_sleeps == []  # Sin reintentos.


class TestQueryHelpers:
    """
    `query_one` y `query_all` extraen los valores del wrapper Hrana
    `{"type": "integer", "value": "42"}` y devuelven listas planas.
    """

    def test_query_all_devuelve_filas_planas(self, monkeypatch):
        body = {
            "results": [{
                "type": "ok",
                "response": {"result": {"rows": [
                    [{"value": "ABC-001"}, {"value": "Test 1"}],
                    [{"value": "ABC-002"}, {"value": "Test 2"}],
                ]}},
            }, {"type": "ok", "response": {"type": "close"}}]
        }
        monkeypatch.setattr(thc.requests, "post", lambda *a, **k: _fake_response(200, body))
        rows = thc.query_all("SELECT codigo_externo, nombre FROM t")
        assert rows == [["ABC-001", "Test 1"], ["ABC-002", "Test 2"]]

    def test_query_one_devuelve_primera_fila(self, monkeypatch):
        body = {
            "results": [{
                "type": "ok",
                "response": {"result": {"rows": [[{"value": "42"}]]}},
            }, {"type": "ok", "response": {"type": "close"}}]
        }
        monkeypatch.setattr(thc.requests, "post", lambda *a, **k: _fake_response(200, body))
        assert thc.query_one("SELECT COUNT(*) FROM t") == ["42"]

    def test_query_one_sin_filas_devuelve_none(self, monkeypatch):
        body = {
            "results": [{
                "type": "ok",
                "response": {"result": {"rows": []}},
            }]
        }
        monkeypatch.setattr(thc.requests, "post", lambda *a, **k: _fake_response(200, body))
        assert thc.query_one("SELECT 1 FROM t WHERE 1=0") is None

    def test_query_all_propaga_error_sql(self, monkeypatch):
        body = {
            "results": [{
                "type": "error",
                "error": {"message": "no such table: foo"},
            }]
        }
        monkeypatch.setattr(thc.requests, "post", lambda *a, **k: _fake_response(200, body))
        with pytest.raises(TursoUnavailableError) as exc_info:
            thc.query_all("SELECT * FROM foo")
        assert "no such table" in exc_info.value.ultimo_error
