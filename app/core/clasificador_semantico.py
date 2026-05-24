"""
AIDU Op - Clasificador semantico con Claude API (S13.4.3)
============================================================

Reemplaza el clasificador lexical (`categorizador_aidu_fast.categorizar_linea`)
por uno basado en Claude API. Envia descripcion + organismo y recibe un JSON
estructurado con linea AIDU, granularidad (producto vs contrato/obra/servicio)
y confidence.

USO BASICO
----------
    from app.core.clasificador_semantico import clasificar_via_claude

    resultado = clasificar_via_claude(
        descripcion="AGUJA HIPODERMICA 21G CAJA POR 100",
        organismo="SERVICIO DE SALUD O'HIGGINS",
    )
    # resultado = {
    #     "linea": "Salud",
    #     "es_producto_granular": True,
    #     "confidence": 0.95,
    #     "razon": "Insumo medico hospitalario con unidad y cantidad.",
    # }

FALLBACK
--------
Este modulo NO implementa el fallback al clasificador lexical. Eso queda
en `app.core.ingesta_inteligencia_precios.categorizar_item` que envuelve
la llamada en try/except y cae a `categorizar_linea` si la API falla.

PROMPT
------
Disenado para Claude Sonnet 4.5+. El prompt define las 7 lineas con
ejemplos cortos. Se truncan descripcion a 500 chars y organismo a 200
para mantener tokens bajos (~$0.0024 USD por llamada con sonnet-4-5).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from app.api.claude_client import ClaudeApiUnavailableError, llamar_claude_json
from app.core.categorizador_aidu_fast import (
    LINEA_FALLBACK,
    LINEAS_AIDU_FAST_CON_OTROS,
)

logger = logging.getLogger(__name__)


PROMPT_TEMPLATE = """Eres un experto en clasificacion de items adquiridos en el Mercado Publico de Chile.

Clasifica el siguiente item en UNA de estas 7 lineas de negocio AIDU:

- Salud: insumos medicos, farmaceuticos, dentales, hospitalarios, laboratorio, quirurgicos, ortopedicos, protesis, medicamentos, instrumental clinico.
- Aseo: productos de limpieza profesional para edificios e instituciones (mopa, cera, detergente, papel higienico, jabon, alcohol gel, escobillas).
- Oficina: papeleria, archivadores, tinta, toner para impresora, lapices, cuadernos, materiales administrativos.
- Ferreteria: tornillos, clavos, herramientas de mano, articulos de ferreteria general para mantencion basica.
- Equipamiento: mobiliario institucional, electrodomesticos, equipos electronicos no medicos, equipos de oficina mayores.
- Materiales de Construccion: cemento, hormigon, fierro estructural, aridos, ladrillo, madera dimensionada, terminaciones constructivas.
- Otros: no encaja claramente en ninguna de las anteriores.

ADEMAS, determina si el item es un PRODUCTO GRANULAR (algo con precio unitario accionable) o NO (contrato marco, obra de construccion, estudio, servicio generico sin grano fisico).

Item descripcion: {descripcion}
Organismo comprador: {organismo}

Responde SOLO con un JSON valido, sin texto adicional:
{{"linea": "<nombre exacto de la linea>", "es_producto_granular": <true|false>, "confidence": <0.0 a 1.0>, "razon": "<una linea breve>"}}"""


# Schema esperado de la respuesta para validacion mas estricta.
_CAMPOS_REQUERIDOS = ("linea", "es_producto_granular", "confidence", "razon")


def _resultado_fallback(razon: str) -> Dict[str, Any]:
    """Devuelve un resultado seguro para casos donde la clasificacion no
    fue determinante. Se usa cuando Claude responde con linea invalida o
    estructura incompleta. No cuando la API falla por completo (eso lo
    maneja el caller via try/except ClaudeApiUnavailableError)."""
    return {
        "linea": LINEA_FALLBACK,
        "es_producto_granular": None,
        "confidence": 0.0,
        "razon": razon,
    }


def _normalizar_resultado(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Valida y normaliza el JSON que devolvio Claude. Si la linea no esta
    en LINEAS_AIDU_FAST_CON_OTROS, cae a Otros con confidence=0.0."""
    if not isinstance(raw, dict):
        return _resultado_fallback("respuesta Claude no es dict")

    # Validar campos requeridos
    faltantes = [k for k in _CAMPOS_REQUERIDOS if k not in raw]
    if faltantes:
        return _resultado_fallback(f"faltan campos en respuesta Claude: {faltantes}")

    linea = str(raw.get("linea", "")).strip()
    if linea not in LINEAS_AIDU_FAST_CON_OTROS:
        logger.warning(
            "Claude devolvio linea invalida %r; fallback a Otros con confidence=0.0",
            linea,
        )
        return _resultado_fallback(f"linea invalida: {linea!r}")

    # Coercer es_producto_granular a bool/None tolerante
    granular = raw.get("es_producto_granular")
    if isinstance(granular, bool):
        granular_norm: Any = granular
    elif isinstance(granular, (int, float)):
        granular_norm = bool(granular)
    elif isinstance(granular, str):
        s = granular.strip().lower()
        if s in ("true", "1", "si", "yes"):
            granular_norm = True
        elif s in ("false", "0", "no"):
            granular_norm = False
        else:
            granular_norm = None
    else:
        granular_norm = None

    # Coercer confidence a float en [0.0, 1.0]
    try:
        confidence = float(raw.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    razon = str(raw.get("razon", ""))[:300]

    return {
        "linea": linea,
        "es_producto_granular": granular_norm,
        "confidence": confidence,
        "razon": razon,
    }


def clasificar_via_claude(descripcion: str, organismo: str = "") -> Dict[str, Any]:
    """Clasifica un item via Claude API.

    Devuelve dict con keys: linea, es_producto_granular, confidence, razon.

    Pre-procesamiento defensivo:
      - Si descripcion tiene < 10 chars utiles, retorna Otros + granular=None
        (no vale la pena pegar la API por ruido).
      - Trunca descripcion a 500 chars y organismo a 200 para tokens bajos.

    Si la API falla, propaga `ClaudeApiUnavailableError`. El caller
    (ingesta) decide si caer al clasificador lexical.
    """
    desc = (descripcion or "").strip()
    if len(desc) < 10:
        return _resultado_fallback("descripcion demasiado corta (<10 chars)")

    prompt = PROMPT_TEMPLATE.format(
        descripcion=desc[:500],
        organismo=(organismo or "")[:200],
    )

    try:
        raw = llamar_claude_json(prompt, max_tokens=200)
    except json.JSONDecodeError as e:
        logger.warning("Claude respondio JSON invalido (%s); fallback a Otros", e)
        return _resultado_fallback(f"json invalido: {e}")
    # ClaudeApiUnavailableError sube al caller intencionalmente

    return _normalizar_resultado(raw)
