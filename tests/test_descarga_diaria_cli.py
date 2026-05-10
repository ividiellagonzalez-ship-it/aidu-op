"""
Tests del CLI de descarga diaria — exit codes 0/1/2/3 y dispatcher de
paths (HTTP /v2/pipeline vs SQLite local).

S12.2.1 — Anti-regresión del bug del Run #3 (id 25611217780):
el handshake de Turso falló y el código cayó silenciosamente a un SQLite
local efímero, perdiendo 446 licitaciones con exit code 0 (verde
engañoso). Estos tests verifican que cada modo de falla produce el exit
code correcto, sin heurística por substring.

S12.2.2 — Tests del path HTTP que reemplaza al cliente libsql en
producción. Verifican selección automática del path según
`turso_http_client.is_configured()`, batches de tamaño correcto,
escritura de `mp_ingesta_log`, y propagación de TursoUnavailableError.

Estrategia: monkeypatch sobre `app.core.descarga_diaria.ejecutar_descarga`
o sobre `turso_http_client.execute_pipeline`. Sin subprocess: `_main()`
devuelve int.
"""
import logging

import pytest

from app.core import descarga_diaria as dd
from app.core.descarga_diaria import _main, MercadoPublicoAPIError
from app.db import turso_http_client
from app.db.exceptions import TursoUnavailableError


@pytest.fixture(autouse=True)
def _aislar_env_turso(monkeypatch):
    """
    Por defecto, los tests del path SQLite asumen que NO hay credenciales
    Turso (de lo contrario la bifurcación de S12.2.2 manda al path HTTP
    y los monkeypatches de `get_connection` no aplican). Los tests de la
    clase TestEjecutarViaHTTP setean explícitamente las env vars que
    necesiten.
    """
    monkeypatch.delenv("TURSO_DATABASE_URL", raising=False)
    monkeypatch.delenv("TURSO_AUTH_TOKEN", raising=False)


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


# ============================================================
# S12.2.2 — Path HTTP /v2/pipeline (Plan B)
# ============================================================
class TestEjecutarViaHTTP:
    """
    Cubre el path nuevo de S12.2.2 que escribe a Turso vía HTTP en lugar
    de libsql. Verifica selección automática del path, batches correctos,
    propagación de TursoUnavailableError, escritura de mp_ingesta_log.

    Estrategia: setear env vars Turso para activar el path, monkeypatch
    a `turso_http_client.execute_pipeline` y `query_all` para capturar
    los statements enviados sin tocar la red.
    """

    @pytest.fixture(autouse=True)
    def _activar_path_http(self, monkeypatch):
        monkeypatch.setenv("TURSO_DATABASE_URL", "libsql://test-aidu.aws-us-east-2.turso.io")
        monkeypatch.setenv("TURSO_AUTH_TOKEN", "test-token-1234")

    @pytest.fixture
    def cliente_mp_fake(self, monkeypatch):
        """
        Reemplaza MercadoPublicoClient por un fake parametrizable. La
        prueba decide qué licitaciones devolver. AGIL siempre devuelve
        lista vacía (cobertura mínima — el path AGIL ya está cubierto
        en los tests del path SQLite).
        """
        store = {"vigentes": [], "agiles": []}

        class _Fake:
            def __init__(self, ticket=None):
                pass

            def descargar_vigentes_recientes(self, dias_atras):
                return store["vigentes"]

            def listar_agiles_recientes(self, dias_atras):
                return store["agiles"]

        monkeypatch.setattr(dd, "MercadoPublicoClient", _Fake)
        return store

    @pytest.fixture
    def http_capture(self, monkeypatch):
        """
        Reemplaza turso_http_client.execute_pipeline / query_all por
        capturas en memoria. Cada test decide qué devolver para query_all
        (existencia, matchers) y qué hacer con los pipelines disparados.
        """
        captured = {
            "pipelines": [],          # lista de batches (cada batch es lista de statements)
            "queries": [],            # lista de (sql, args)
            "query_responses": {},    # {sql_substring: rows}
            "pipeline_raise": None,   # excepción opcional a levantar
        }

        def _execute(statements, *, timeout=60.0):
            captured["pipelines"].append(list(statements))
            if captured["pipeline_raise"] is not None:
                raise captured["pipeline_raise"]
            # Por defecto: devolver results "ok" para cada statement.
            return [{"type": "ok"} for _ in statements]

        def _query_all(sql, args=None):
            captured["queries"].append((sql, args))
            for marker, rows in captured["query_responses"].items():
                if marker in sql:
                    return rows
            return []

        monkeypatch.setattr(turso_http_client, "execute_pipeline", _execute)
        monkeypatch.setattr(turso_http_client, "query_all", _query_all)
        return captured

    def test_path_http_se_usa_cuando_creds_presentes(
        self, monkeypatch, cliente_mp_fake, http_capture,
    ):
        """
        Sanity: con env vars Turso seteadas y una licitación, el flujo
        usa HTTP (dispara pipelines) y NO llama a get_connection().
        """
        cliente_mp_fake["vigentes"] = [{
            "CodigoExterno": "TEST-001", "Nombre": "Construcción", "Comprador": {},
        }]

        # Si get_connection se llamara, levantamos para detectarlo.
        monkeypatch.setattr(dd, "get_connection", lambda: pytest.fail(
            "get_connection NO debe llamarse en path HTTP"
        ))

        resultado = dd.ejecutar_descarga(dias_atras=1)

        assert resultado["nuevas"] == 1
        assert resultado["total_descargado"] == 1
        # Al menos un pipeline disparado (el INSERT a vigentes y el log).
        assert len(http_capture["pipelines"]) >= 1

    def test_codigos_existentes_se_actualizan(self, cliente_mp_fake, http_capture):
        """
        Si el bulk_check_existencia devuelve un código como existente,
        ese código debe ir a UPDATE, no a INSERT.
        """
        cliente_mp_fake["vigentes"] = [
            {"CodigoExterno": "NUEVA-001", "Nombre": "Nueva", "Comprador": {}},
            {"CodigoExterno": "EXIST-002", "Nombre": "Vieja", "Comprador": {}},
        ]
        # Marcar EXIST-002 como ya presente en mp_licitaciones_vigentes.
        http_capture["query_responses"]["FROM mp_licitaciones_vigentes WHERE codigo_externo IN"] = [
            ["EXIST-002"],
        ]

        resultado = dd.ejecutar_descarga(dias_atras=1)
        assert resultado["nuevas"] == 1
        assert resultado["actualizadas"] == 1

        # Inspeccionar SQL disparado: debe haber un INSERT y un UPDATE.
        all_sql = " || ".join(
            stmt["sql"]
            for batch in http_capture["pipelines"]
            for stmt in batch
        )
        assert "INSERT INTO mp_licitaciones_vigentes" in all_sql
        assert "UPDATE mp_licitaciones_vigentes" in all_sql

    def test_batches_de_50_para_grandes_volumenes(self, cliente_mp_fake, http_capture):
        """
        Con 120 licitaciones nuevas, el INSERT a vigentes debe partirse
        en pipelines de 50/50/20 (3 batches).
        """
        cliente_mp_fake["vigentes"] = [
            {"CodigoExterno": f"BIG-{i:04d}", "Nombre": f"Lic {i}", "Comprador": {}}
            for i in range(120)
        ]

        dd.ejecutar_descarga(dias_atras=1)

        # Aislar pipelines de INSERT a vigentes (excluye categorización
        # y mp_ingesta_log).
        inserts_vigentes = [
            batch for batch in http_capture["pipelines"]
            if batch and "INSERT INTO mp_licitaciones_vigentes" in batch[0]["sql"]
        ]
        sizes = [len(b) for b in inserts_vigentes]
        assert sizes == [50, 50, 20], f"Tamaños esperados [50,50,20], got {sizes}"

    def test_mp_ingesta_log_se_escribe(self, cliente_mp_fake, http_capture):
        """
        Criterio #3 del plan S12.2.2: cada corrida del cron deja una
        entrada en mp_ingesta_log con n_nuevas, duración y estado.
        """
        cliente_mp_fake["vigentes"] = [
            {"CodigoExterno": f"LOG-{i:03d}", "Nombre": "x", "Comprador": {}}
            for i in range(3)
        ]

        dd.ejecutar_descarga(dias_atras=1)

        log_pipelines = [
            batch for batch in http_capture["pipelines"]
            if batch and "INSERT INTO mp_ingesta_log" in batch[0]["sql"]
        ]
        assert len(log_pipelines) == 1, "Debe escribirse exactamente una fila a mp_ingesta_log"
        # Pipeline tiene 1 statement.
        assert len(log_pipelines[0]) == 1

    def test_turso_unavailable_durante_pipeline_propaga_para_exit_2(
        self, cliente_mp_fake, http_capture,
    ):
        """
        Si execute_pipeline levanta TursoUnavailableError (HTTP 5xx tras
        reintentos), la excepción debe propagar al CLI sin ser capturada
        como 'falla individual'. Verifica anti-regresión del fix S12.2.1.
        """
        cliente_mp_fake["vigentes"] = [
            {"CodigoExterno": "FAIL-001", "Nombre": "x", "Comprador": {}},
        ]
        http_capture["pipeline_raise"] = TursoUnavailableError(
            "Turso no disponible vía HTTP", intentos=3, ultimo_error="HTTP 503",
        )

        with pytest.raises(TursoUnavailableError):
            dd.ejecutar_descarga(dias_atras=1)

    def test_main_path_http_turso_caido_exit_2(
        self, monkeypatch, cliente_mp_fake, http_capture,
    ):
        """
        Integración end-to-end: env vars Turso seteadas + execute_pipeline
        que falla → _main() retorna exit code 2.
        """
        cliente_mp_fake["vigentes"] = [
            {"CodigoExterno": "X-001", "Nombre": "x", "Comprador": {}},
        ]
        http_capture["pipeline_raise"] = TursoUnavailableError(
            "transport down", intentos=3, ultimo_error="HTTP 502",
        )
        assert _main() == 2

    def test_categorizacion_inmemory_no_consulta_keywords_por_licitacion(
        self, cliente_mp_fake, http_capture,
    ):
        """
        El path HTTP debe cargar `aidu_servicios_keywords` UNA SOLA VEZ
        con un query, no una vez por licitación. Verifica que el número
        de queries SELECT a esa tabla sea exactamente 1, no N.
        """
        cliente_mp_fake["vigentes"] = [
            {"CodigoExterno": f"CAT-{i:03d}", "Nombre": f"servicio {i}", "Comprador": {}}
            for i in range(20)
        ]
        # Simular keywords AIDU para que el matching corra.
        http_capture["query_responses"]["aidu_servicios_keywords"] = [
            ["CE-01", "edificación,construcción", ""],
        ]
        # Existencia: ninguna está; todas son nuevas.
        http_capture["query_responses"]["FROM mp_licitaciones_vigentes WHERE codigo_externo IN"] = []

        dd.ejecutar_descarga(dias_atras=1)

        # Contar SELECTs a aidu_servicios_keywords.
        n_queries_keywords = sum(
            1 for sql, _ in http_capture["queries"]
            if "aidu_servicios_keywords" in sql
        )
        assert n_queries_keywords == 1, (
            f"Esperaba 1 query a aidu_servicios_keywords (pre-cargada), "
            f"encontré {n_queries_keywords}. El bug original del cron "
            f"hacía 1 query por licitación."
        )

    def test_match_aidu_inmemory_replica_logica_canonica(self):
        """
        El matcher in-memory debe dar los mismos resultados que el
        canónico de `app.core.ingesta._calcular_match_aidu` para entradas
        equivalentes. Casos: hit múltiple, excluyente, sin texto, umbral.
        """
        matchers = [
            ("CE-01", ["edificación", "construcción"], []),
            ("CE-02", ["puente", "carretera"], ["torres de alta tensión"]),
            ("DV-01", ["diseño", "consultoría"], []),
        ]
        # Hit múltiple: 2 keywords matched de CE-01.
        out = dd._match_aidu_inmemory(
            "Construcción de edificación municipal", matchers, top_n=2,
        )
        assert out and out[0][0] == "CE-01"
        assert out[0][1] >= 0.5

        # Excluyente: aunque tenga 'puente', el texto contiene
        # 'torres de alta tensión' → CE-02 descartado.
        out = dd._match_aidu_inmemory(
            "Diseño de puente para torres de alta tensión", matchers, top_n=2,
        )
        cods = [c for c, _ in out]
        assert "CE-02" not in cods

        # Sin texto.
        assert dd._match_aidu_inmemory("", matchers) == []
        assert dd._match_aidu_inmemory("   ", matchers) == []

        # Sin match (texto sin keywords).
        assert dd._match_aidu_inmemory(
            "ferretería barrial limpieza", matchers,
        ) == []
