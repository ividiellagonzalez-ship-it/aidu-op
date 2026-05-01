"""
AIDU Op · Análisis IA con Claude
==================================
1 llamada API por análisis. Costo bajo, valor alto.
Usa el contexto del proyecto + estadísticas históricas reales.
"""
import os
import logging
from typing import Dict
import anthropic

from app.db.migrator import get_connection
from app.core.inteligencia_precios import calcular_escenarios_precio, obtener_estadisticas_categoria
from config.settings import get_anthropic_api_key

logger = logging.getLogger(__name__)


def analizar_proyecto_con_ia(proyecto_id: int) -> Dict:
    """
    Una llamada Claude que analiza el proyecto en su contexto completo.
    Devuelve análisis estratégico con recomendaciones accionables.
    """
    api_key = get_anthropic_api_key()
    if not api_key:
        return {
            "error": "API key de Claude no configurada. En Streamlit Cloud: Settings → Secrets → ANTHROPIC_API_KEY",
            "analisis": None
        }

    # Recopilar contexto del proyecto
    conn = get_connection()
    p = conn.execute("SELECT * FROM aidu_proyectos WHERE id = ?", (proyecto_id,)).fetchone()
    conn.close()

    if not p:
        return {"error": "Proyecto no encontrado"}

    esc = calcular_escenarios_precio(proyecto_id)
    stats = esc.get("stats", {})

    # Construir prompt con contexto
    prompt = f"""Eres asesor estratégico de AIDU Op SpA, consultora chilena de ingeniería y transformación digital con IA. Director: Ignacio Vidiella González (Ing. Civil), socia: Jorella (Ing. Comercial). Operan en Mercado Público chileno.

Analiza esta licitación que Ignacio está evaluando:

LICITACIÓN
- Código: {p['codigo_externo']}
- Nombre: {p['nombre']}
- Organismo: {p['organismo']}
- Región: {p['region']}
- Categoría AIDU: {p['cod_servicio_aidu']}
- Monto referencial: ${p['monto_referencial']:,} CLP
- Cierre: {p['fecha_cierre']}
- Descripción: {p['descripcion']}

CONTEXTO DE MERCADO (histórico Mercado Público)
- Licitaciones similares analizadas: {stats.get('n_total', 0)}
- Descuento típico (mediana): {stats.get('descuento_mediana', 0):.1f}%
- Competidores recurrentes: {len(stats.get('competidores_recurrentes', []))}

ESCENARIOS DE PRECIO CALCULADOS
- Agresivo: ${esc['agresivo']['precio']:,} (margen {esc['agresivo']['margen_pct']:.1f}%, prob {esc['agresivo']['probabilidad']}%)
- Competitivo: ${esc['competitivo']['precio']:,} (margen {esc['competitivo']['margen_pct']:.1f}%, prob {esc['competitivo']['probabilidad']}%)
- Premium: ${esc['premium']['precio']:,} (margen {esc['premium']['margen_pct']:.1f}%, prob {esc['premium']['probabilidad']}%)

COSTO BASE AIDU
- HH Ignacio: {p['hh_ignacio_estimado']} h
- HH Jorella: {p['hh_jorella_estimado']} h
- Costo total: ${esc['costo']['costo_total']:,.0f}

Entrega un análisis estratégico ejecutivo en 4 secciones cortas:

1. **VEREDICTO** (1-2 líneas): ¿Postular SÍ o NO? Por qué.

2. **ESCENARIO RECOMENDADO** (2-3 líneas): Cuál de los 3 escenarios y por qué.

3. **RIESGOS PRINCIPALES** (lista de 3): Los riesgos más relevantes para AIDU.

4. **DIFERENCIADORES PROPUESTA** (lista de 3): Qué destacar en la propuesta técnica para ganar.

Responde directo, sin preámbulo. Tono ejecutivo, accionable. Máximo 400 palabras."""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        analisis = message.content[0].text
        tokens_in = message.usage.input_tokens
        tokens_out = message.usage.output_tokens

        # Estimación de costo (Sonnet: $3/$15 por 1M tokens)
        costo_usd = (tokens_in * 3 + tokens_out * 15) / 1_000_000

        # Guardar en historial chat IA
        conn = get_connection()
        conn.execute(
            "INSERT INTO aidu_chat_ia (proyecto_id, rol, contenido) VALUES (?, ?, ?)",
            (proyecto_id, "user", "Análisis estratégico automático")
        )
        conn.execute(
            "INSERT INTO aidu_chat_ia (proyecto_id, rol, contenido) VALUES (?, ?, ?)",
            (proyecto_id, "assistant", analisis)
        )
        conn.commit()
        conn.close()

        logger.info(f"Análisis IA completado: {tokens_in}+{tokens_out} tokens, ~${costo_usd:.4f}")

        return {
            "analisis": analisis,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "costo_estimado_usd": round(costo_usd, 4),
        }

    except anthropic.AuthenticationError:
        return {
            "error": "API key de Claude inválida. Verifica ~/AIDU_Op/config/secrets.env",
            "analisis": None
        }
    except Exception as e:
        logger.error(f"Error análisis IA: {e}")
        return {"error": str(e), "analisis": None}
