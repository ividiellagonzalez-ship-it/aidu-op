"""
AIDU Op · Cliente HTTP /v2/pipeline para Turso
================================================
Capa de escritura a Turso vía la API HTTP `/v2/pipeline` (protocolo Hrana
sobre HTTP). Reemplaza el camino de replication libsql en el flujo
crítico del cron (descarga diaria) por un transporte estable.

Por qué este módulo existe (S12.2.2)
------------------------------------
S12.2 reactivó el cron diario apuntando a Turso vía
`libsql_experimental==0.0.55` en modo "embedded replica". Funcionaba en
local pero falló determinísticamente en producción contra
`aws-us-east-2` con error `Invalid header bit 123 expected 0 or 1`.
Investigación durante S12.2.2 (issues `tursodatabase/libsql-laravel#2`,
`libsql-js#157`, `go-libsql#52`) confirmó que es una incompatibilidad
arquitectónica entre el modo Embedded Replica de libsql y los Turso
hosteados en AWS — no un bug de versión. El paquete `libsql-experimental`
quedó congelado en 0.0.55 (PyPI, jun-2025); su sucesor `libsql 0.1.x`
arrastra el mismo bug por la misma razón.

Solución: el cron escribe vía HTTP `/v2/pipeline` directo, que SÍ funciona
contra AWS y ya está validado en producción por
`docs/migracion_inicial_turso.py` desde S12.1.5. La app Streamlit puede
seguir usando `app.db.migrator.get_connection()` (que envuelve libsql
para reads — los reads no van por replication, así que ese path no
está afectado por el bug de Embedded Replica).

Diseño
------
- API pública: `execute_pipeline(statements)` recibe lista de dicts
  Hrana (`{"sql": "...", "args": [...]}`) y devuelve la lista de
  `results` del response. Los args ya deben venir convertidos al formato
  Hrana — usar `app.db._hrana_types.arg_for_value` o `args_for_row`.
- Errores HTTP, timeouts y conexión se mapean a `TursoUnavailableError`
  (mismo tipo que S12.2.1) para que el CLI siga clasificando exit 2.
- Errores SQL del payload (`type: "error"` en un result) se propagan al
  caller — son específicos del query, no fallas de transporte. El caller
  decide si los tolera (idempotencia tipo `already exists`) o aborta.
- Reintentos con backoff exponencial: 3 intentos (1s, 4s, 16s = 21s
  total). Cubre fallas transitorias de red sin agotar el `timeout-minutes`
  del workflow.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import requests

from app.db.exceptions import TursoUnavailableError

logger = logging.getLogger(__name__)


# Política de reintentos espejo a la de migrator._ensure_turso_replica.
# Mismos números → mismas expectativas operacionales (exit 2 después
# de ~21s si Turso no responde).
_HTTP_MAX_INTENTOS = 3
_HTTP_BACKOFF_BASE_S = 1.0  # 1, 4, 16 segundos


def _read_credentials() -> Optional[tuple[str, str]]:
    """
    Lee TURSO_DATABASE_URL + TURSO_AUTH_TOKEN desde st.secrets (Streamlit
    Cloud) o variables de entorno. Devuelve (url, token) si ambas existen
    y no están vacías, o None si no.

    Espejo intencional de `migrator._read_turso_credentials` — no
    importamos esa función para evitar dependencia circular y para que
    este módulo sea self-contained (Plan B existe precisamente para
    desacoplar del path libsql).
    """
    url, token = "", ""
    try:
        import streamlit as st  # noqa: WPS433
        if hasattr(st, "secrets"):
            url = (st.secrets.get("TURSO_DATABASE_URL", "") or "").strip()
            token = (st.secrets.get("TURSO_AUTH_TOKEN", "") or "").strip()
    except Exception:
        pass
    if not url:
        url = os.environ.get("TURSO_DATABASE_URL", "").strip()
    if not token:
        token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if url and token:
        return url, token
    return None


def is_configured() -> bool:
    """
    True si Turso está configurado vía env vars o st.secrets. Permite a
    los callers (descarga_diaria) decidir si usar este cliente o caer al
    flujo SQLite local de dev/CI/tests sin levantar excepción.
    """
    return _read_credentials() is not None


def _endpoint(creds: tuple[str, str]) -> tuple[str, dict[str, str]]:
    """
    Construye la URL HTTPS y los headers para `/v2/pipeline` desde las
    credenciales libsql. Mismo patrón que `migracion_inicial_turso.py`,
    extraído acá para reuso.
    """
    url, token = creds
    http_url = url.replace("libsql://", "https://", 1).rstrip("/") + "/v2/pipeline"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    return http_url, headers


def execute_pipeline(
    statements: list[dict],
    *,
    timeout: float = 60.0,
) -> list[dict]:
    """
    Envía una lista de statements en un solo pipeline HTTP a Turso.

    Args:
        statements: lista de dicts con shape `{"sql": str, "args": list?}`.
            Los `args` deben venir ya convertidos al formato Hrana
            (`{"type": "...", "value": ...}`) — usar
            `app.db._hrana_types.arg_for_value`.
        timeout: timeout HTTP por intento, en segundos. Default 60s
            cubre batches de hasta ~50 inserts holgadamente; el bootstrap
            (que mete miles de filas) usa 120s.

    Returns:
        Lista de dicts `results` del response Turso. Cada result tiene
        forma `{"type": "ok"|"error", "response": {...}, "error": {...}}`.
        El último result (`{"type": "ok", "response": {"type": "close"}}`)
        viene del implícito `close` que agregamos al final del pipeline
        para que Turso libere el statement context.

    Raises:
        TursoUnavailableError: el transporte falló (HTTP 4xx/5xx,
            timeout, conexión rechazada, DNS) tras 3 reintentos. NO
            cubre errores SQL del payload — esos vienen como
            `result["type"] == "error"` en la respuesta y los maneja
            el caller.
    """
    creds = _read_credentials()
    if creds is None:
        # NO es modo legítimo "sin Turso" en este path: si alguien llama
        # execute_pipeline sin credenciales es un bug. El callsite
        # debería haber chequeado `is_configured()` antes.
        raise TursoUnavailableError(
            "execute_pipeline llamado sin TURSO_DATABASE_URL/TURSO_AUTH_TOKEN. "
            "Usar is_configured() para decidir el path antes de invocar.",
            intentos=0,
            ultimo_error="missing credentials",
        )

    http_url, headers = _endpoint(creds)
    payload = {
        "requests": [{"type": "execute", "stmt": stmt} for stmt in statements]
        + [{"type": "close"}],
    }

    ultimo_error: Optional[str] = None
    for intento in range(1, _HTTP_MAX_INTENTOS + 1):
        try:
            r = requests.post(http_url, headers=headers, json=payload, timeout=timeout)
        except requests.RequestException as e:
            # Network error (timeout, DNS, conexión rechazada, TLS).
            # Determinístico solo si el endpoint está realmente caído;
            # transitorio si es glitch del runner. Reintento.
            ultimo_error = f"{type(e).__name__}: {e}"
        else:
            if r.status_code < 400:
                return r.json().get("results", [])
            # HTTP 4xx/5xx: capturar status + body recortado para diagnóstico.
            body_snippet = (r.text or "")[:300]
            ultimo_error = f"HTTP {r.status_code}: {body_snippet}"

        if intento < _HTTP_MAX_INTENTOS:
            espera = _HTTP_BACKOFF_BASE_S * (4 ** (intento - 1))
            logger.warning(
                f"⚠️  Pipeline HTTP a Turso falló (intento {intento}"
                f"/{_HTTP_MAX_INTENTOS}): {ultimo_error}. "
                f"Reintento en {espera:.0f}s."
            )
            time.sleep(espera)

    msg = (
        "Turso no disponible vía HTTP /v2/pipeline tras "
        f"{_HTTP_MAX_INTENTOS} reintentos. Abortando para evitar "
        f"pérdida silenciosa de datos. Último error: {ultimo_error}"
    )
    logger.error(f"❌ {msg}")
    raise TursoUnavailableError(
        msg,
        intentos=_HTTP_MAX_INTENTOS,
        ultimo_error=ultimo_error or "",
    )


def query_one(sql: str, args: Optional[list] = None) -> Optional[list]:
    """
    Helper de conveniencia: ejecuta un SELECT y devuelve la primera fila
    como lista de valores (ya extraídos del wrapper `{type, value}` de
    Hrana). None si no hay filas o el query falló.

    Para batches o resultados múltiples, usar `execute_pipeline`
    directamente.
    """
    stmt: dict = {"sql": sql}
    if args:
        stmt["args"] = args
    results = execute_pipeline([stmt])
    if not results:
        return None
    first = results[0]
    if first.get("type") != "ok":
        return None
    rows = first.get("response", {}).get("result", {}).get("rows", [])
    if not rows:
        return None
    return [cell.get("value") for cell in rows[0]]


def query_all(sql: str, args: Optional[list] = None) -> list[list]:
    """
    Helper: ejecuta un SELECT y devuelve todas las filas como lista de
    listas de valores. Lista vacía si no hay filas o el query falló
    (los errores SQL no se enmascaran cuando el primer result es error).
    """
    stmt: dict = {"sql": sql}
    if args:
        stmt["args"] = args
    results = execute_pipeline([stmt])
    if not results:
        return []
    first = results[0]
    if first.get("type") != "ok":
        # No tragar errores SQL: el caller los necesita ver.
        err = first.get("error", {}).get("message", "Turso SQL error")
        raise TursoUnavailableError(
            f"Query SQL falló en Turso: {err}",
            intentos=1,
            ultimo_error=err,
        )
    rows = first.get("response", {}).get("result", {}).get("rows", [])
    return [[cell.get("value") for cell in row] for row in rows]
