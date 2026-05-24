"""
AIDU Op - Cliente canonico Claude API (S13.4.3)
=================================================

Cliente HTTP para Anthropic Claude API con parsing JSON estructurado y
manejo de errores. Es el punto unico de contacto del proyecto con la
API de Claude.

USO BASICO
----------
    from app.api.claude_client import llamar_claude_json

    resultado = llamar_claude_json(
        "Clasifica este producto en una linea AIDU: ...",
        max_tokens=200,
    )
    # resultado es dict parseado desde el JSON que devolvio Claude

OVERRIDE DEL MODELO
-------------------
El parametro `model` defaultea a `config.settings.get_modelo_clasificador()`,
que lee la env var `CLAUDE_MODEL_CLASIFICADOR` con fallback al
`CLAUDE_MODEL` global. Override sin tocar codigo:

    export CLAUDE_MODEL_CLASIFICADOR=claude-sonnet-4-6

DEUDA TECNICA (TD-02)
---------------------
Hay 3 callers historicos de la API Claude en app/core/analisis_*.py que
no usan este cliente y duplican el patron `anthropic.Anthropic + messages.create`.
Unificarlos al cliente canonico esta agendado en docs/tech_debt.md TD-02
(no en scope de S13.4.3).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ClaudeApiUnavailableError(RuntimeError):
    """Se levanta si ANTHROPIC_API_KEY no esta configurada o si la API no
    responde tras los reintentos del SDK. Permite al caller decidir
    (fallback a clasificador lexical, registro de error, etc.)."""


def get_client():
    """Devuelve un cliente `anthropic.Anthropic` listo para usar.

    Lee ANTHROPIC_API_KEY (env var o st.secrets via config.settings).
    Levanta ClaudeApiUnavailableError si no hay key.
    """
    # Import diferido para que el modulo sea importable en entornos sin
    # `anthropic` instalado (ej. tests unitarios con mocks).
    try:
        import anthropic  # type: ignore[import-untyped]
    except ImportError as e:
        raise ClaudeApiUnavailableError(
            "Paquete `anthropic` no instalado. pip install anthropic"
        ) from e

    # Tres fuentes en orden: env var directa, config.settings.get_anthropic_api_key,
    # st.secrets si se corre desde Streamlit Cloud.
    api_key = (os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        try:
            from config.settings import get_anthropic_api_key
            api_key = (get_anthropic_api_key() or "").strip()
        except Exception:
            api_key = ""
    if not api_key or api_key.startswith("tu-"):
        raise ClaudeApiUnavailableError(
            "ANTHROPIC_API_KEY no configurada o placeholder. "
            "Setear en GitHub Secrets / .env / st.secrets."
        )
    return anthropic.Anthropic(api_key=api_key)


def _get_default_model() -> str:
    """Lazy: lee el modelo default del config (que mira CLAUDE_MODEL_CLASIFICADOR)."""
    try:
        from config.settings import get_modelo_clasificador
        return get_modelo_clasificador()
    except Exception:
        # Fallback de ultima instancia si config.settings no esta accesible.
        return "claude-sonnet-4-5"


def llamar_claude_json(
    prompt: str,
    max_tokens: int = 200,
    model: Optional[str] = None,
    system: Optional[str] = None,
) -> Dict[str, Any]:
    """Llama a Claude API y parsea la respuesta como JSON.

    Args:
        prompt: el contenido del mensaje user.
        max_tokens: limite superior de tokens en la respuesta.
        model: opcional, override del modelo. Default = get_modelo_clasificador().
        system: opcional, prompt de sistema.

    Returns:
        dict parseado desde el JSON de Claude.

    Raises:
        ClaudeApiUnavailableError: si no hay credenciales o falla la
            llamada despues de los reintentos del SDK.
        json.JSONDecodeError: si la respuesta de Claude no es JSON valido.
    """
    client = get_client()
    effective_model = model or _get_default_model()
    kwargs: Dict[str, Any] = {
        "model": effective_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        kwargs["system"] = system
    try:
        msg = client.messages.create(**kwargs)
    except Exception as e:
        # El SDK ya reintenta internamente para 429/503; si llego aca es fatal.
        raise ClaudeApiUnavailableError(
            f"Claude API fallo tras reintentos del SDK: {e}"
        ) from e

    # Extraer texto del primer content block (puede haber multiples).
    try:
        text = msg.content[0].text.strip()
    except (AttributeError, IndexError) as e:
        raise ClaudeApiUnavailableError(
            f"Respuesta inesperada de Claude (sin content[0].text): {e}"
        ) from e

    # Limpiar fences markdown si vienen (a veces Claude envuelve JSON en ```).
    if text.startswith("```"):
        # Quitar la primera linea (puede ser ```json o ```) y el ``` final.
        parts = text.split("\n", 1)
        if len(parts) == 2:
            text = parts[1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()

    return json.loads(text)
