"""
AIDU Op · Excepciones de la capa de persistencia
=================================================
Tipos de error explícitos para distinguir fallas de BD/Turso del resto del
universo de excepciones, y permitir que el CLI principal mapee a exit codes
sin recurrir a heurística por substring.

S12.2.1 — Introducido tras el incidente del Run #3 (id 25611217780):
el handshake de libsql con Turso falló con 'Invalid header bit 123 expected
0 or 1' y el código de la capa de conexión cayó silenciosamente a un
SQLite local efímero del runner de GitHub Actions. 446 licitaciones
descargadas se escribieron contra una BD sin schema y se perdieron al
terminar el job. Esta excepción reemplaza ese fallback: producción debe
abortar con exit 2 antes de tocar SQLite local cuando hay credenciales
Turso configuradas.
"""


class TursoUnavailableError(Exception):
    """
    El handshake con Turso falló a pesar de que las credenciales
    (TURSO_DATABASE_URL + TURSO_AUTH_TOKEN) están presentes.

    NO se debe capturar para caer a SQLite local. El callsite de runtime
    (CLI de descarga, cron de refresh, scripts de mantenimiento) debe
    propagarla al punto de entrada principal y terminar con exit 2.

    El SQLite local solo es válido en dos escenarios explícitos:
    1) Modo dev/CI sin credenciales (TURSO_DATABASE_URL vacía).
    2) Tests con monkeypatch que sustituyen get_connection().

    Cualquier otro uso de SQLite local en runtime productivo es el bug
    arquitectónico que motivó la migración a Turso en S12.1.
    """

    def __init__(self, mensaje: str, intentos: int = 0, ultimo_error: str = ""):
        self.intentos = intentos
        self.ultimo_error = ultimo_error
        super().__init__(mensaje)
