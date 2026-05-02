"""
AIDU Op · Análisis IA Masivo
=============================
Analiza un batch de oportunidades en una sola llamada a Claude
para identificar las top N más prometedoras según el perfil AIDU.

Caso de uso: el usuario tiene 50 oportunidades filtradas y quiere
saber rápidamente cuáles 5 vale la pena estudiar a fondo.

Costo: 1 llamada Claude por batch (~$0.02-0.05 USD)
Tiempo: 15-30 segundos
"""
import json
import logging
from typing import Dict, List, Optional

import anthropic

from config.settings import get_anthropic_api_key

logger = logging.getLogger(__name__)


PROMPT_SISTEMA = """Eres un asistente comercial estratégico para AIDU Op, una consultora 
de Ingeniería Civil chilena enfocada en licitaciones de Mercado Público.

PERFIL AIDU:
- Empresa solo: Ignacio (Ing. Civil estructural + gestión proyectos) + Jorella (Ing. Comercial)
- Servicios: cálculo estructural (CE-01 a CE-06), gestión procesos (GP-01 a GP-05),
  análisis con IA (IA-01 a IA-03), capacitación digital (CAP-01)
- Tarifa base: 2 UF/hora (~CLP 78.000)
- Foco geográfico: Región de O'Higgins (prioritario), RM y zona centro
- Sweet spot de monto: $3M - $15M CLP
- Restricción: NO compite donde JEJ Ingeniería opera (mineras estatales, ITO minería)

TU TAREA:
Analizar la lista de licitaciones que recibirás y devolver SOLO las {top_n} más 
prometedoras para AIDU, con justificación corta y accionable para cada una.

CRITERIOS DE SELECCIÓN (en orden de importancia):
1. Match real con servicios AIDU (no genérico, sino qué servicio específico aplica)
2. Margen esperado realista considerando tarifa AIDU vs precio adjudicado histórico
3. Bajo riesgo: organismos serios, plazos razonables, alcance acotado
4. Diferenciación posible: AIDU puede ofrecer algo que otros no
5. Recencia y posibilidad de postular (si está vigente)

DESCARTAR:
- Licitaciones donde el descuento histórico de adjudicación es >20% (mercado quemado)
- Montos muy bajos donde la tarifa AIDU no es competitiva
- Servicios fuera del catálogo AIDU
- Ya adjudicadas hace >6 meses (no se pueden postular)

FORMATO DE RESPUESTA:
Devuelve SOLO un JSON válido (sin markdown, sin texto adicional) con esta estructura exacta:
{{
  "top": [
    {{
      "codigo": "string",
      "nombre": "string corto",
      "veredicto": "POSTULAR" | "EVALUAR" | "DESCARTAR",
      "razon_principal": "1 frase concreta de por qué",
      "margen_estimado_pct": número,
      "riesgo": "BAJO" | "MEDIO" | "ALTO"
    }}
  ],
  "resumen_ejecutivo": "2-3 frases con conclusión general del batch"
}}"""


def analisis_masivo(
    oportunidades: List[Dict],
    top_n: int = 5,
    api_key: Optional[str] = None,
) -> Dict:
    """
    Analiza un batch de oportunidades con Claude y devuelve las top_n más prometedoras.
    
    Args:
        oportunidades: lista de dicts con codigo_externo, nombre, descripcion, 
                       organismo, region, monto_referencial, monto_adjudicado, 
                       cod_servicio_aidu, fecha_publicacion
        top_n: cuántas devolver en el ranking (default 5)
        api_key: opcional, sino usa get_anthropic_api_key()
    
    Returns:
        {
            "top": [{codigo, nombre, veredicto, razon_principal, margen_estimado_pct, riesgo}, ...],
            "resumen_ejecutivo": str,
            "costo_usd": float,
            "tokens_in": int,
            "tokens_out": int,
            "n_analizadas": int,
            "error": str | None
        }
    """
    if not oportunidades:
        return {"error": "No hay oportunidades para analizar", "top": [], "resumen_ejecutivo": ""}
    
    key = api_key or get_anthropic_api_key()
    if not key:
        return {
            "error": "API key de Claude no configurada en Streamlit Secrets",
            "top": [],
            "resumen_ejecutivo": ""
        }
    
    # Reducir el batch a campos relevantes (ahorra tokens)
    batch_resumido = []
    for op in oportunidades[:30]:  # cap a 30 para no exceder context
        batch_resumido.append({
            "codigo": op.get("codigo_externo"),
            "nombre": (op.get("nombre") or "")[:120],
            "descripcion": (op.get("descripcion") or "")[:300],
            "organismo": op.get("organismo"),
            "region": op.get("region"),
            "monto_ref_M": round((op.get("monto_referencial") or 0) / 1_000_000, 1),
            "monto_adj_M": round((op.get("monto_adjudicado") or 0) / 1_000_000, 1) if op.get("monto_adjudicado") else None,
            "categoria_aidu": op.get("cod_servicio_aidu"),
            "fecha_pub": (op.get("fecha_publicacion") or "")[:10],
            "match_score": op.get("match", {}).get("score") if isinstance(op.get("match"), dict) else None,
        })
    
    user_prompt = f"""Analiza estas {len(batch_resumido)} licitaciones y devuelve las {top_n} más prometedoras para AIDU Op:

{json.dumps(batch_resumido, ensure_ascii=False, indent=1)}

Recuerda: SOLO JSON válido, sin markdown ni texto adicional."""
    
    try:
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2500,
            system=PROMPT_SISTEMA.format(top_n=top_n),
            messages=[{"role": "user", "content": user_prompt}],
        )
        
        texto_respuesta = response.content[0].text.strip()
        
        # Limpiar markdown si Claude lo agregó (a veces lo hace)
        if texto_respuesta.startswith("```"):
            texto_respuesta = texto_respuesta.split("```")[1]
            if texto_respuesta.startswith("json"):
                texto_respuesta = texto_respuesta[4:]
            texto_respuesta = texto_respuesta.strip()
        
        try:
            parsed = json.loads(texto_respuesta)
        except json.JSONDecodeError as e:
            logger.warning(f"Error parsing JSON Claude: {e}\nResponse: {texto_respuesta[:500]}")
            return {
                "error": f"Claude devolvió respuesta no parseable: {str(e)[:100]}",
                "top": [],
                "resumen_ejecutivo": "",
                "raw": texto_respuesta[:1000],
            }
        
        # Calcular costo (Sonnet 4.5: $3/MTok input, $15/MTok output)
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        costo = (tokens_in * 3.0 + tokens_out * 15.0) / 1_000_000
        
        return {
            "top": parsed.get("top", []),
            "resumen_ejecutivo": parsed.get("resumen_ejecutivo", ""),
            "costo_usd": round(costo, 4),
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "n_analizadas": len(batch_resumido),
            "error": None,
        }
    except Exception as e:
        logger.exception("Error en análisis masivo")
        return {
            "error": f"Error llamando a Claude: {str(e)[:200]}",
            "top": [],
            "resumen_ejecutivo": "",
        }
