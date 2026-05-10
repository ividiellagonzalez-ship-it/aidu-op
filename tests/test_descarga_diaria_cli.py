"""
Tests del CLI de descarga diaria — exit codes 0/1/2/3.

S12.2.1 — Anti-regresión del bug del Run #3 (id 25611217780):
el handshake de Turso falló y el código cayó silenciosamente a un SQLite
local efímero, perdiendo 446 licitaciones con exit code 0 (verde
engañoso). Estos tests verifican que cada modo de falla produce el exit
code correcto, sin heurística por substring.

Estrategia: monkeypatch sobre `app.core.descarga_diaria.ejecutar_descarga`
y llamada directa a `_main()`. Sin subprocess: `_main()` devuelve int.
"""
import logging

import pytest

from app.core import descarga_diaria as dd
from app.core.descarga_diaria import _main, MercadoPublicoAPIError
from app.db.exceptions import TursoUnavailableError


@pytest.fixture(autouse=True)
def _reset_logging_handlers():
    """
    `_main()` llama `logging.basicConfig(...)` que es idempotente solo si no
    hay handlers previos. Limpiamos antes de cada test para que la salida
    sea predecible cuando pytest captura logs.
    """
    root = logging.getLogger()
    handlers = list(root.handlers)
    yield
    # Restaurar el estado para no interferir con otros tests del suite.
    root.handlers = handlers


def _stub_resultado_ok():
    return {
        "nuevas": 5,
        "actualizadas": 1,
        "fallidas": 0,
        "total_descargado": 6,
        "categorizadas_aidu": 5,
        "agiles_descargadas": 0,
    }


class TestExitCodes:
    """Verifica que cada modo de falla mapea al exit code correcto."""

    def test_exit_0_descarga_exitosa(self, monkeypatch, capsys):
        """Path feliz: ejecutar_descarga devuelve dict, _main retorna 0."""
        monkeypatch.setattr(
            dd, "ejecutar_descarga",
            lambda dias_atras=2, ticket=None: _stub_resultado_ok(),
        )
        assert _main() == 0
        captured = capsys.readouterr()
        # El resumen debe imprimirse a stdout para que el cron lo logguee.
        assert "Resultado" in captured.out
        assert "nuevas" in captured.out

    def test_exit_1_api_mercadopublico(self, monkeypatch):
        """API ChileCompra falla → MercadoPublicoAPIError → exit 1."""
        def _api_fail(dias_atras=2, ticket=None):
            raise MercadoPublicoAPIError(
                "API Mercado Público falló: rate limit"
            )
        monkeypatch.setattr(dd, "ejecutar_descarga", _api_fail)
        assert _main() == 1

    def test_exit_2_turso_unavailable(self, monkeypatch):
        """
        Turso caído tras reintentos → TursoUnavailableError → exit 2.
        Este es el caso CRÍTICO del Run #3: antes daba exit 0 (verde
        engañoso), ahora exit 2 limpio.
        """
        def _turso_fail(dias_atras=2, ticket=None):
            raise TursoUnavailableError(
                "Turso no disponible tras 3 reintentos",
                intentos=3,
                ultimo_error="Invalid header bit 123 expected 0 or 1",
            )
        monkeypatch.setattr(dd, "ejecutar_descarga", _turso_fail)
        assert _main() == 2

    def test_exit_3_error_inesperado(self, monkeypatch, capsys):
        """
        Excepción no clasificada (bug real) → traceback + exit 3.
        Antes la heurística por substring de S12.2 mapeaba estos a exit 1
        (falsa atribución a la API). Ahora se aíslan para investigación.
        """
        def _bug(dias_atras=2, ticket=None):
            raise ValueError("scenario inesperado: divide by zero")
        monkeypatch.setattr(dd, "ejecutar_descarga", _bug)
        assert _main() == 3
        captured = capsys.readouterr()
        # Traceback debe imprimirse a stderr para auditoría operacional.
        assert "Traceback" in captured.err
        assert "ValueError" in captured.err

    def test_turso_unavailable_no_se_confunde_con_api(self, monkeypatch):
        """
        Anti-regresión: la heurística de S12.2 mapeaba 'auth' (substring)
        a exit 2. Si la API devolviera un mensaje con 'auth' (token MP
        inválido), antes daba exit 2 (BD) cuando en verdad es API (exit 1).
        Ahora la captura es por TIPO, no por substring, así que un error
        de la API con 'auth' en el mensaje sigue siendo exit 1.
        """
        def _api_auth_fail(dias_atras=2, ticket=None):
            raise MercadoPublicoAPIError(
                "API Mercado Público: ticket auth rechazado por el servidor"
            )
        monkeypatch.setattr(dd, "ejecutar_descarga", _api_auth_fail)
        assert _main() == 1


class TestEjecutarDescargaPropagaTurso:
    """
    Verifica que el try/except interno de `ejecutar_descarga` (que captura
    errores de licitación individual) NO traga TursoUnavailableError. Sin
    este re-raise, el bug original del Run #3 se reproduce: 446 fallas
    individuales que silencian el problema y permiten exit 0.
    """

    def test_turso_unavailable_escala_durante_loop(self, monkeypatch):
        """
        Simulamos que el cliente MP devuelve una licitación, y que
        get_connection() devuelve una conexión cuyo execute() levanta
        TursoUnavailableError al primer insert. La excepción debe
        propagar al caller, NO ser tragada como 'Error procesando
        licitación'.
        """
        from app.api.mercadopublico import MercadoPublicoClient

        # Cliente fake con una licitación mínima.
        class _ClienteFake:
            def __init__(self, ticket=None):
                pass

            def descargar_vigentes_recientes(self, dias_atras):
                return [{
                    "CodigoExterno": "TEST-001",
                    "Nombre": "Test",
                    "Comprador": {},
                }]

            def listar_agiles_recientes(self, dias_atras):
                return []

        # Conexión fake cuyo execute revienta con TursoUnavailableError.
        class _ConnFake:
            def execute(self, *args, **kwargs):
                raise TursoUnavailableError(
                    "sync falló a media corrida",
                    intentos=3,
                    ultimo_error="connection reset",
                )

            def commit(self):
                pass

            def close(self):
                pass

        monkeypatch.setattr(dd, "MercadoPublicoClient", _ClienteFake)
        monkeypatch.setattr(dd, "get_connection", lambda: _ConnFake())

        with pytest.raises(TursoUnavailableError):
            dd.ejecutar_descarga(dias_atras=1)

    def test_error_individual_de_licitacion_no_aborta(self, monkeypatch):
        """
        Contrapartida: una licitación individual con un campo malformado
        (ValueError, KeyError, lo que sea que NO sea TursoUnavailableError)
        sí se traga y se contabiliza como 'fallida'. Eso preserva la
        semántica útil del try/except por licitación.
        """
        class _ClienteFake:
            def __init__(self, ticket=None):
                pass

            def descargar_vigentes_recientes(self, dias_atras):
                return [
                    {"CodigoExterno": "OK-001", "Nombre": "ok", "Comprador": {}},
                    {"CodigoExterno": "BAD-002", "Nombre": "bad", "Comprador": {}},
                ]

            def listar_agiles_recientes(self, dias_atras):
                return []

        # SELECT siempre devuelve None (no existe). INSERT del segundo
        # registro lanza ValueError; del primero pasa.
        class _ConnFake:
            def __init__(self):
                self._n = 0

            def execute(self, sql, params=()):
                if "INSERT" in sql and "BAD-002" in (params or ()):
                    raise ValueError("simula campo malformado")

                class _Cur:
                    def fetchone(self_inner):
                        return None
                return _Cur()

            def commit(self):
                pass

            def close(self):
                pass

        # Bypass de la categorización AIDU (requiere BD real).
        monkeypatch.setattr(dd, "_calcular_match_aidu", lambda *a, **k: [])
        monkeypatch.setattr(dd, "MercadoPublicoClient", _ClienteFake)
        monkeypatch.setattr(dd, "get_connection", lambda: _ConnFake())

        resultado = dd.ejecutar_descarga(dias_atras=1)
        # No abortó; contabilizó la fallida.
        assert resultado["fallidas"] == 1
        assert resultado["nuevas"] == 1
