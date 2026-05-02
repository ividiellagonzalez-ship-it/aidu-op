"""
AIDU Op · Análisis IA de Bases Técnicas
=========================================
Lee un PDF de bases técnicas, extrae texto y le pide a Claude que devuelva
un análisis estructurado con:
- Requisitos eliminatorios
- Plazos críticos
- Garantías exigidas
- Criterios de evaluación
- Cláusulas problemáticas / riesgos
- Recomendación de postular SI/NO

Uso:
    from app.core.analisis_bases import analizar_pdf_bases
    
    resultado = analizar_pdf_bases(pdf_bytes, codigo_licitacion="2641-156-L125")
"""
import json
import hashlib
import logging
from io import BytesIO
from typing import Dict, Optional, List
from datetime import datetime

from app.db.migrator import get_connection

logger = logging.getLogger(__name__)


# ============================================================
# EXTRACCIÓN DE TEXTO DE PDFs
# ============================================================

def extraer_texto_pdf(pdf_bytes: bytes) -> Dict:
    """
    Extrae texto de un PDF usando pypdf.
    Si el PDF es escaneado (sin texto), retorna es_escaneado=True.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader
        except ImportError:
            raise ImportError("Instalar: pip install pypdf")
    
    reader = PdfReader(BytesIO(pdf_bytes))
    n_paginas = len(reader.pages)
    
    textos = []
    for i, page in enumerate(reader.pages):
        try:
            txt = page.extract_text() or ""
            textos.append(txt)
        except Exception as e:
            logger.warning(f"Error página {i}: {e}")
            textos.append("")
    
    texto_completo = "\n\n".join(textos)
    
    # Heurística: si menos de 100 caracteres totales y >5 páginas, probablemente escaneado
    es_escaneado = len(texto_completo.strip()) < 100 and n_paginas > 2
    
    return {
        "texto": texto_completo,
        "n_paginas": n_paginas,
        "es_escaneado": es_escaneado,
        "tamano_bytes": len(pdf_bytes),
        "n_caracteres": len(texto_completo),
    }


# ============================================================
# CACHE
# ============================================================

def hash_pdf(pdf_bytes: bytes) -> str:
    """SHA256 del PDF para cache."""
    return hashlib.sha256(pdf_bytes).hexdigest()


def buscar_cache(pdf_hash: str) -> Optional[Dict]:
    """Busca análisis cacheado del mismo PDF."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT resultado_json, fecha_analisis FROM cache_analisis_ia WHERE pdf_hash = ? AND tipo_analisis = 'bases'",
            (pdf_hash,)
        ).fetchone()
        if row:
            return {
                "resultado": json.loads(row["resultado_json"]),
                "fecha_analisis": row["fecha_analisis"],
                "from_cache": True,
            }
        return None
    finally:
        conn.close()


def guardar_cache(pdf_hash: str, codigo_licitacion: str, resultado: Dict, tokens_in: int, tokens_out: int, costo_usd: float):
    """Guarda análisis en cache."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT OR REPLACE INTO cache_analisis_ia
            (pdf_hash, licitacion_codigo, tipo_analisis, resultado_json, tokens_input, tokens_output, costo_usd)
            VALUES (?, ?, 'bases', ?, ?, ?, ?)
        """, (pdf_hash, codigo_licitacion, json.dumps(resultado, ensure_ascii=False), tokens_in, tokens_out, costo_usd))
        conn.commit()
    finally:
        conn.close()


def registrar_costo(proyecto_id: Optional[int], tipo: str, tokens_in: int, tokens_out: int, costo_usd: float):
    """Tracking de costos por proyecto."""
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO cost_tracking_ia (proyecto_id, tipo_operacion, tokens_input, tokens_output, costo_usd)
            VALUES (?, ?, ?, ?, ?)
        """, (proyecto_id, tipo, tokens_in, tokens_out, costo_usd))
        conn.commit()
    finally:
        conn.close()


# ============================================================
# PROMPT ESTRUCTURADO PARA CLAUDE
# ============================================================

PROMPT_ANALISIS_BASES = """Eres un asistente experto en licitaciones públicas chilenas. Analiza las bases técnicas adjuntas y devuelve un JSON estructurado.

CONTEXTO DEL CONSULTOR:
- Profesional: Ingeniero Civil con experiencia en cálculo estructural y gestión de proyectos
- Empresa: AIDU Op (consultoría B2G)
- Tarifa: 2 UF/hora (CLP 78.000)
- Sweet spot: CLP 3M - 15M
- Especialización: estructural, peritajes, gestión de proyectos municipales

INSTRUCCIONES:
Devuelve EXCLUSIVAMENTE un JSON válido (sin texto antes o después) con esta estructura:

{
  "resumen_ejecutivo": "string de 2-3 frases con la esencia del proyecto",
  "objeto_licitacion": "string breve",
  "monto_referencial_clp": número o null,
  "plazo_ejecucion_dias": número o null,
  
  "requisitos_eliminatorios": [
    {"requisito": "string", "puede_cumplir": "si|no|incierto", "comentario": "string"}
  ],
  
  "plazos_criticos": [
    {"hito": "string", "fecha_o_dias": "string", "criticidad": "alta|media|baja"}
  ],
  
  "garantias_exigidas": [
    {"tipo": "seriedad|fiel_cumplimiento|anticipo|otra", "monto_uf_o_pct": "string", "obligatoria": true}
  ],
  
  "criterios_evaluacion": [
    {"criterio": "string", "ponderacion_pct": número, "comentario": "string"}
  ],
  
  "clausulas_problematicas": [
    {"clausula": "string", "riesgo": "alto|medio|bajo", "razon": "string"}
  ],
  
  "experiencia_requerida": {
    "anos_minimos": número o null,
    "proyectos_similares_min": número o null,
    "especialidad_requerida": "string"
  },
  
  "recomendacion": {
    "postular": "si|no|con_reservas",
    "confianza": número entre 0 y 100,
    "razones_principales": ["string", "string", "string"],
    "acciones_previas_necesarias": ["string"]
  },
  
  "estimacion_competencia": {
    "nivel_esperado": "baja|media|alta",
    "razon": "string"
  },
  
  "alertas_legales": ["string"]
}

REGLAS:
- Si un campo no se puede determinar del PDF, usa null o lista vacía
- Sé conservador en "puede_cumplir": si hay duda, marca "incierto"
- Las "clausulas_problematicas" deben ser específicas (cita texto si puedes)
- En "recomendacion.razones_principales" da MÁXIMO 3 razones, las más decisivas
- Devuelve SOLO el JSON, sin markdown ni explicaciones

BASES TÉCNICAS A ANALIZAR:
"""


def analizar_pdf_bases(
    pdf_bytes: bytes,
    codigo_licitacion: str = "",
    proyecto_id: Optional[int] = None,
    forzar_reanalisis: bool = False,
) -> Dict:
    """
    Analiza bases técnicas con Claude. Devuelve resultado estructurado + meta.
    
    Returns:
        {
            "ok": bool,
            "resultado": dict (estructura del prompt),
            "meta": {...},
            "from_cache": bool,
            "error": str si ok=False
        }
    """
    # 1. Hash y cache
    pdf_h = hash_pdf(pdf_bytes)
    
    if not forzar_reanalisis:
        cached = buscar_cache(pdf_h)
        if cached:
            logger.info(f"📦 Cache hit para {codigo_licitacion}")
            return {
                "ok": True,
                "resultado": cached["resultado"],
                "from_cache": True,
                "fecha_analisis": cached["fecha_analisis"],
                "meta": {"tokens_input": 0, "tokens_output": 0, "costo_usd": 0.0},
            }
    
    # 2. Extraer texto
    extraccion = extraer_texto_pdf(pdf_bytes)
    
    if extraccion["es_escaneado"]:
        return {
            "ok": False,
            "error": "PDF parece ser escaneado (sin texto extraíble). Necesita OCR.",
            "meta": {"n_paginas": extraccion["n_paginas"]},
        }
    
    if extraccion["n_caracteres"] < 200:
        return {
            "ok": False,
            "error": f"PDF tiene muy poco texto ({extraccion['n_caracteres']} caracteres). ¿PDF correcto?",
        }
    
    texto = extraccion["texto"]
    
    # 3. Truncar si es muy largo (Claude maneja ~200k tokens, pero costoso)
    MAX_CHARS = 80_000  # ~20k tokens
    if len(texto) > MAX_CHARS:
        texto = texto[:MAX_CHARS] + "\n\n[...TRUNCADO POR TAMAÑO...]"
        logger.warning(f"PDF truncado a {MAX_CHARS} chars")
    
    # 4. Llamar a Claude
    try:
        import anthropic
        from config.settings import get_anthropic_key
        
        api_key = get_anthropic_key()
        if not api_key:
            return {
                "ok": False,
                "error": "ANTHROPIC_API_KEY no configurada en secretos de Streamlit Cloud",
            }
        
        client = anthropic.Anthropic(api_key=api_key)
        
        prompt_completo = PROMPT_ANALISIS_BASES + texto
        
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt_completo}],
        )
        
        respuesta_texto = response.content[0].text.strip()
        
        # Limpiar markdown si Claude devolvió ```json ... ```
        if respuesta_texto.startswith("```"):
            lineas = respuesta_texto.split("\n")
            respuesta_texto = "\n".join(lineas[1:-1] if lineas[-1].startswith("```") else lineas[1:])
        
        # Parsear JSON
        try:
            resultado = json.loads(respuesta_texto)
        except json.JSONDecodeError as e:
            logger.error(f"Claude devolvió JSON inválido: {respuesta_texto[:300]}")
            return {
                "ok": False,
                "error": f"Claude devolvió formato inválido: {e}",
                "raw_response": respuesta_texto[:500],
            }
        
        # 5. Costos
        tokens_in = response.usage.input_tokens
        tokens_out = response.usage.output_tokens
        # Claude Sonnet 4.5: $3/MTok input, $15/MTok output
        costo_usd = (tokens_in / 1_000_000) * 3.0 + (tokens_out / 1_000_000) * 15.0
        
        # 6. Cache
        guardar_cache(pdf_h, codigo_licitacion, resultado, tokens_in, tokens_out, costo_usd)
        registrar_costo(proyecto_id, "bases_tecnicas", tokens_in, tokens_out, costo_usd)
        
        return {
            "ok": True,
            "resultado": resultado,
            "from_cache": False,
            "meta": {
                "tokens_input": tokens_in,
                "tokens_output": tokens_out,
                "costo_usd": round(costo_usd, 4),
                "n_paginas": extraccion["n_paginas"],
                "n_caracteres_analizados": len(texto),
            },
        }
        
    except Exception as e:
        logger.exception("Error en análisis IA bases")
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
        }


# ============================================================
# AUTO-RELLENO DE CHECKLIST DESDE ANÁLISIS IA
# ============================================================

def auto_rellenar_checklist(proyecto_id: int, analisis_ia: Dict) -> int:
    """
    Toma el análisis IA y marca/desmarca items del checklist
    de precalificación según los requisitos detectados.
    
    Returns: cantidad de items actualizados
    """
    requisitos = analisis_ia.get("requisitos_eliminatorios", [])
    if not requisitos:
        return 0
    
    conn = get_connection()
    n_actualizados = 0
    try:
        for req in requisitos:
            req_text = req.get("requisito", "").lower()
            puede = req.get("puede_cumplir", "incierto")
            
            # Mapear a items del checklist standard
            mapeo = {
                "boleta": "garantia_seriedad",
                "garantía": "garantia_seriedad",
                "patente": "patente_municipal",
                "iniciación": "iniciacion_actividades",
                "experiencia": "experiencia_minima",
                "antecedentes": "antecedentes_tributarios",
                "f30": "f30_cumplimiento",
                "deudor": "registro_deudores",
            }
            
            for keyword, item_id in mapeo.items():
                if keyword in req_text:
                    estado = "OK" if puede == "si" else "FALTA" if puede == "no" else "REVISAR"
                    try:
                        conn.execute("""
                            UPDATE proy_checklist
                            SET estado = ?, comentario = ?
                            WHERE proyecto_id = ? AND item_id = ?
                        """, (estado, req.get("comentario", "")[:200], proyecto_id, item_id))
                        if conn.total_changes > 0:
                            n_actualizados += 1
                    except Exception:
                        pass
        conn.commit()
    finally:
        conn.close()
    
    return n_actualizados


# ============================================================
# OBTENER ÚLTIMO ANÁLISIS DE UN PROYECTO
# ============================================================

def obtener_ultimo_analisis(licitacion_codigo: str) -> Optional[Dict]:
    """Recupera el análisis más reciente de un proyecto/licitación."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT pdf_hash, resultado_json, fecha_analisis, tokens_input, tokens_output, costo_usd
            FROM cache_analisis_ia
            WHERE licitacion_codigo = ? AND tipo_analisis = 'bases'
            ORDER BY fecha_analisis DESC LIMIT 1
        """, (licitacion_codigo,)).fetchone()
        
        if not row:
            return None
        
        return {
            "pdf_hash": row["pdf_hash"],
            "resultado": json.loads(row["resultado_json"]),
            "fecha_analisis": row["fecha_analisis"],
            "tokens_input": row["tokens_input"],
            "tokens_output": row["tokens_output"],
            "costo_usd": row["costo_usd"],
        }
    finally:
        conn.close()
