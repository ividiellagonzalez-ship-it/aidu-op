"""
AIDU Op · Extractor de aspectos técnicos
==========================================
Extrae información cuantitativa/cualitativa de la descripción de una licitación.
Permite comparar SERVICIOS de manera real (no solo por monto).

Detecta:
- m² mencionados (superficie del proyecto)
- HH estimadas si se mencionan
- N° de entregables (planos, memorias, informes, etc.)
- Plazo de ejecución (días o meses)
- Tipo de obra (cálculo estructural, peritaje, asesoría, etc.)
"""
import re
from typing import Dict, List, Optional


# Palabras clave para tipos de entregables
ENTREGABLES_KEYWORDS = [
    "planos", "memoria", "memoria de cálculo", "memoria sismorresistente",
    "especificaciones técnicas", "informe", "informe técnico", "estudio",
    "diagnóstico", "peritaje", "cubicaciones", "presupuesto", "carta gantt",
    "cronograma", "BPM", "manual de procedimientos", "bases técnicas",
    "minuta", "acta", "registro", "EETT", "expediente"
]


def extraer_aspectos(descripcion: str, nombre: str = "") -> Dict:
    """
    Extrae aspectos técnicos clave de la descripción de una licitación.
    Retorna dict con campos detectados (None si no encontrado).
    """
    texto = f"{nombre} {descripcion or ''}".lower()
    
    return {
        "metros_cuadrados": _extraer_m2(texto),
        "plazo_dias": _extraer_plazo_dias(texto),
        "n_entregables": _contar_entregables(texto),
        "entregables": _listar_entregables(texto),
        "tipo_servicio": _detectar_tipo_servicio(texto),
        "complejidad": _estimar_complejidad(texto),
    }


def _extraer_m2(texto: str) -> Optional[int]:
    """Busca menciones de superficie en m²."""
    patrones = [
        r"(\d{2,5})\s*m[²2]",
        r"(\d{2,5})\s*metros?\s*cuadrados?",
        r"superficie\s*de\s*(\d{2,5})",
    ]
    for pat in patrones:
        match = re.search(pat, texto, re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                continue
    return None


def _extraer_plazo_dias(texto: str) -> Optional[int]:
    """Busca plazo de ejecución en días."""
    patrones = [
        (r"plazo\s+(?:de\s+)?(\d{1,3})\s*d[ií]as?", 1),
        (r"(\d{1,3})\s*d[ií]as?\s+corridos?", 1),
        (r"(\d{1,2})\s*meses?", 30),  # convertir meses a días
        (r"(\d{1,3})\s*d[ií]as?\s+h[áa]biles?", 1.4),  # convertir hábiles a corridos
    ]
    for pat, factor in patrones:
        match = re.search(pat, texto, re.IGNORECASE)
        if match:
            try:
                n = int(match.group(1))
                return int(n * factor)
            except (ValueError, IndexError):
                continue
    return None


def _contar_entregables(texto: str) -> int:
    """Cuenta cuántos tipos de entregables se mencionan."""
    encontrados = set()
    for kw in ENTREGABLES_KEYWORDS:
        if kw.lower() in texto:
            encontrados.add(kw.lower())
    return len(encontrados)


def _listar_entregables(texto: str) -> List[str]:
    """Lista los entregables identificados (limit 5)."""
    encontrados = []
    for kw in ENTREGABLES_KEYWORDS:
        if kw.lower() in texto and len(encontrados) < 5:
            encontrados.append(kw)
    return encontrados


def _detectar_tipo_servicio(texto: str) -> str:
    """Clasifica el tipo de servicio según palabras clave."""
    if any(k in texto for k in ["cálculo estructural", "memoria estructural", "diseño estructural"]):
        return "Cálculo estructural"
    if any(k in texto for k in ["peritaje", "evaluación estructural", "diagnóstico estructural"]):
        return "Peritaje / diagnóstico"
    if any(k in texto for k in ["asesoría", "apoyo técnico", "consultoría", "secplan"]):
        return "Asesoría / consultoría"
    if any(k in texto for k in ["levantamiento", "topograf"]):
        return "Levantamiento"
    if any(k in texto for k in ["bpm", "procesos", "rediseño de procesos"]):
        return "Procesos / BPM"
    if any(k in texto for k in ["bases técnicas", "revisión de bases"]):
        return "Apoyo SECPLAN"
    return "Otro servicio profesional"


def _estimar_complejidad(texto: str) -> str:
    """Estima complejidad: BAJA, MEDIA, ALTA según señales."""
    score = 0
    if "sismorresistente" in texto or "sísmico" in texto:
        score += 2
    if "memoria" in texto:
        score += 1
    if "planos" in texto:
        score += 1
    if "hospital" in texto or "establecimiento de salud" in texto:
        score += 3
    if "edificio" in texto or "altura" in texto:
        score += 2
    if "patrimonial" in texto or "histórico" in texto:
        score += 2
    if "vivienda social" in texto or "sede vecinal" in texto or "salacuna" in texto:
        score += 1
    
    if score >= 5:
        return "ALTA"
    if score >= 2:
        return "MEDIA"
    return "BAJA"


def estimar_hh_referencial(monto_referencial: int, tarifa_hora_clp: int = 78000) -> Dict:
    """
    Estima HH equivalente al monto referencial.
    Útil para comparar 'cuánto trabajo' representa una licitación.
    """
    if not monto_referencial or monto_referencial <= 0:
        return {"hh_total": 0, "hh_por_dia_ref": 0, "dias_dedicados": 0}
    
    # Asumiendo overhead 18% y margen 22%
    # Costo HH = tarifa * 1.18, Precio venta = costo * 1.22
    # → HH = monto / (tarifa * 1.18 * 1.22) ≈ monto / (tarifa * 1.44)
    hh_total = round(monto_referencial / (tarifa_hora_clp * 1.44))
    dias_dedicados = round(hh_total / 8)  # 8 HH/día
    hh_por_dia_ref = 8
    
    return {
        "hh_total": hh_total,
        "hh_por_dia_ref": hh_por_dia_ref,
        "dias_dedicados": dias_dedicados,
    }
