"""
Tests estructurales anti-regresión del fallback silencioso a SQLite local.

S12.2.1 — Tras el incidente del Run #3 (id 25611217780), donde el
handshake de Turso falló y el código cayó silenciosamente a un SQLite
efímero perdiendo 446 licitaciones, este test garantiza que:

1. Ningún módulo runtime productivo emite el log
   "Turso no disponible, opero contra SQLite local".
2. No existen comentarios o docs que sugieran que ese fallback sea un
   modo operativo aceptable (excluyendo entradas históricas del changelog
   y migracion_inicial_turso que documentan POR QUÉ se eliminó).
3. Los call sites legítimos de `sqlite3.connect()` con un path local
   están limitados a:
     - `app/db/migrator.py:get_connection` (encapsulado, con TursoUnavailableError).
     - `tests/` (cuando aparezca).
     - `docs/migracion_inicial_turso.py` (script one-shot de migración inicial).
   Cualquier otro uso es un patrón sospechoso y este test debe revisarse.

Estos tests NO requieren ejecutar el código: leen el filesystem.
"""
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "app"


def _iter_python_files(root: Path):
    """
    Itera archivos .py bajo `root`, excluyendo cachés y artefactos de
    test. Devuelve (path, contenido) para inspección.
    """
    for path in root.rglob("*.py"):
        # Excluir __pycache__ y .pyc compilados.
        if "__pycache__" in path.parts:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Archivos binarios disfrazados de .py — improbable, pero defensivo.
            continue


class TestSinFallbackEnLogs:
    """
    El log incriminatorio no debe existir en el código de runtime. Si
    alguien lo reintroduce (cut-paste, refactor mal hecho), este test lo
    captura antes del merge.
    """

    FRASE_PROHIBIDA = "Turso no disponible, opero contra SQLite local"

    def test_no_aparece_en_app(self):
        """app/ es código productivo: la frase NO puede aparecer."""
        ofensores = []
        for path, content in _iter_python_files(APP_DIR):
            if self.FRASE_PROHIBIDA in content:
                ofensores.append(str(path.relative_to(REPO_ROOT)))
        assert not ofensores, (
            f"El fallback silencioso volvió a aparecer en código runtime. "
            f"S12.2.1 lo eliminó tras el Run #3. Archivos ofensores: {ofensores}"
        )


class TestSqliteConnectAcotado:
    """
    Garantiza que sqlite3.connect() con path local solo aparezca en los
    call sites autorizados. Cualquier otro módulo que abra una conexión
    SQLite directa está saltándose el routing por Turso de migrator.
    """

    # Lista blanca: archivos donde sqlite3.connect() está justificado.
    ALLOWED = {
        # Encapsulado: la única puerta a la BD. Ya tiene TursoUnavailableError.
        "app/db/migrator.py",
        # Script de migración inicial Turso (one-shot, fuera del runtime).
        "docs/migracion_inicial_turso.py",
    }

    def test_callsites_limitados_a_lista_blanca(self):
        ofensores = []
        for path, content in _iter_python_files(REPO_ROOT):
            # Saltar tests (legítimo abrir SQLite ad-hoc para fixtures).
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel.startswith("tests/"):
                continue
            if "sqlite3.connect" not in content:
                continue
            if rel in self.ALLOWED:
                continue
            ofensores.append(rel)
        assert not ofensores, (
            f"sqlite3.connect() apareció fuera de la lista blanca "
            f"(lista actual: {sorted(self.ALLOWED)}). Cualquier llamado "
            f"directo evade el routing Turso de get_connection() y puede "
            f"reintroducir el bug del Run #3. Archivos ofensores: {ofensores}"
        )


class TestExceptionDefinida:
    """
    Smoke test: la clase TursoUnavailableError existe y mapea correctamente.
    Sin esto, el resto de la cadena de exit codes 0/1/2/3 no se sostiene.
    """

    def test_importable(self):
        from app.db.exceptions import TursoUnavailableError
        assert issubclass(TursoUnavailableError, Exception)

    def test_lleva_metadata(self):
        """
        El exit-2 handler del CLI imprime intentos y ultimo_error. Si
        cambian sin actualizar el constructor, este test rompe.
        """
        from app.db.exceptions import TursoUnavailableError
        err = TursoUnavailableError("boom", intentos=3, ultimo_error="net")
        assert err.intentos == 3
        assert err.ultimo_error == "net"
        assert "boom" in str(err)


class TestEnsureTursoReplicaLevantaConCredenciales:
    """
    Test funcional: con credenciales presentes y handshake fallido,
    `_ensure_turso_replica()` debe levantar TursoUnavailableError, NO
    devolver False. Garantiza que `get_connection()` nunca devuelva un
    SQLite local cuando hay credenciales y Turso está caído.
    """

    def test_levanta_tursounavailableerror_con_creds_y_handshake_fail(self, monkeypatch):
        from app.db import migrator
        from app.db.exceptions import TursoUnavailableError

        # Resetear cache global del módulo (pueden venir de tests previos).
        monkeypatch.setattr(migrator, "_TURSO_CONN", None)
        monkeypatch.setattr(migrator, "_TURSO_AVAILABLE", None)
        # Backoff a cero para que el test corra rápido (no esperar 21s).
        monkeypatch.setattr(migrator, "_TURSO_HANDSHAKE_BACKOFF_BASE_S", 0.0)

        # Forzar credenciales presentes.
        monkeypatch.setattr(
            migrator, "_read_turso_credentials",
            lambda: ("libsql://fake-test", "fake-token"),
        )

        # Forzar fallo del handshake. libsql_experimental.connect levanta.
        class _LibsqlFake:
            @staticmethod
            def connect(*args, **kwargs):
                raise RuntimeError("Invalid header bit 123 expected 0 or 1")

        # Inyectar el módulo fake en sys.modules para que `import
        # libsql_experimental as libsql` lo encuentre.
        import sys
        monkeypatch.setitem(sys.modules, "libsql_experimental", _LibsqlFake)

        with pytest.raises(TursoUnavailableError) as exc_info:
            migrator._ensure_turso_replica()
        assert exc_info.value.intentos == migrator._TURSO_HANDSHAKE_MAX_INTENTOS
        assert "Invalid header bit" in exc_info.value.ultimo_error

    def test_devuelve_false_sin_credenciales(self, monkeypatch):
        """
        Modo dev/CI/tests sin credenciales: el comportamiento previo se
        mantiene. NO levantar excepción, devolver False, dejar que
        get_connection() use sqlite3 puro.
        """
        from app.db import migrator

        monkeypatch.setattr(migrator, "_TURSO_CONN", None)
        monkeypatch.setattr(migrator, "_TURSO_AVAILABLE", None)
        monkeypatch.setattr(migrator, "_read_turso_credentials", lambda: None)

        assert migrator._ensure_turso_replica() is False
