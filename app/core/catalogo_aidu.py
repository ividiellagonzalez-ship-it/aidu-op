"""
AIDU Op · Catálogo de servicios
================================
Definición central de los códigos de servicio AIDU con descripciones legibles.
Usar este módulo en TODAS partes donde se muestre un código CE-XX o GP-XX.
"""

CATALOGO_AIDU = {
    # ============ Cálculo Estructural (CE) ============
    "CE-01": {
        "nombre": "Peritaje y diagnóstico estructural",
        "descripcion": "Evaluación de daños, inspección visual, informes técnicos post-sismo",
        "linea": "Estructural",
    },
    "CE-02": {
        "nombre": "Cálculo y diseño estructural",
        "descripcion": "Planos, memoria de cálculo, diseño sismorresistente",
        "linea": "Estructural",
    },
    "CE-03": {
        "nombre": "Revisión de proyectos estructurales",
        "descripcion": "Revisión técnica de cálculos y planos de terceros",
        "linea": "Estructural",
    },
    "CE-04": {
        "nombre": "Asesoría en obras estructurales",
        "descripcion": "Apoyo técnico en faenas, soluciones constructivas",
        "linea": "Estructural",
    },
    "CE-05": {
        "nombre": "Inspección técnica de obras (ITO) estructural",
        "descripcion": "ITO en obras nuevas y modificaciones estructurales",
        "linea": "Estructural",
    },
    "CE-06": {
        "nombre": "Apoyo SECPLAN — bases técnicas",
        "descripcion": "Revisión bases técnicas, cubicaciones, EETT para licitaciones municipales",
        "linea": "Estructural",
    },
    
    # ============ Gestión de Proyectos (GP) ============
    "GP-01": {
        "nombre": "Gestión de proyectos · PMO",
        "descripcion": "PMO, control integral de proyectos, metodología ágil/PMI",
        "linea": "Gestión",
    },
    "GP-02": {
        "nombre": "Optimización de procesos operacionales",
        "descripcion": "Análisis y mejora de procesos productivos y administrativos",
        "linea": "Gestión",
    },
    "GP-03": {
        "nombre": "Diagnóstico organizacional",
        "descripcion": "Diagnóstico de madurez, brechas y oportunidades de mejora",
        "linea": "Gestión",
    },
    "GP-04": {
        "nombre": "Levantamiento y rediseño de procesos · BPM",
        "descripcion": "Mapeo de procesos as-is, rediseño to-be, manuales de procedimiento",
        "linea": "Gestión",
    },
    "GP-05": {
        "nombre": "Gestión del cambio organizacional",
        "descripcion": "Acompañamiento en transformaciones, capacitación, comunicación",
        "linea": "Gestión",
    },
    "GP-06": {
        "nombre": "Asesoría en compras públicas",
        "descripcion": "Apoyo en confección de bases, evaluación de ofertas, gestión post-adjudicación",
        "linea": "Gestión",
    },
}


def get_servicio(codigo: str) -> dict:
    """Devuelve info del servicio. Retorna dict con valores genéricos si no existe."""
    if not codigo:
        return {"nombre": "Sin categoría", "descripcion": "", "linea": "—"}
    return CATALOGO_AIDU.get(codigo, {
        "nombre": codigo,
        "descripcion": "Categoría no catalogada",
        "linea": "—"
    })


def label_servicio(codigo: str, formato: str = "completo") -> str:
    """
    Devuelve label formateado para usar en dropdowns / pills.
    
    formato:
    - "completo": "CE-01 — Peritaje y diagnóstico estructural"
    - "corto": "CE-01 (Peritaje)"
    - "tooltip": "CE-01: Peritaje y diagnóstico estructural · Evaluación de daños..."
    """
    info = get_servicio(codigo)
    if formato == "completo":
        return f"{codigo} — {info['nombre']}"
    if formato == "corto":
        # Extrae primera palabra significativa
        primera = info["nombre"].split(" ")[0] if info["nombre"] else codigo
        return f"{codigo} ({primera})"
    if formato == "tooltip":
        return f"{codigo}: {info['nombre']} · {info['descripcion']}"
    return codigo


def codigos_por_linea(linea: str) -> list:
    """
    Devuelve lista de códigos AIDU de una línea de negocio.
    
    linea: "Estructural" o "Gestión"
    """
    return [cod for cod, info in CATALOGO_AIDU.items() if info["linea"] == linea]


# Línea de negocio → emoji + color (para UI)
LINEAS_NEGOCIO = {
    "Estructural": {"emoji": "🏗️", "color": "#1E40AF", "bg": "#DBEAFE"},
    "Gestión":     {"emoji": "📊", "color": "#7C3AED", "bg": "#EDE9FE"},
}


# ============================================================
# REGIONES DE INTERÉS AIDU (zonas con facilidad logística)
# ============================================================
# Si AIDU expande operaciones, agregar aquí
REGIONES_INTERES_AIDU = {
    "II":  "Antofagasta",
    "V":   "Valparaíso",
    "RM":  "Metropolitana",
    "VI":  "O'Higgins",
    "X":   "Los Lagos",
}

# Mapeo desde nombres como aparecen en MP a códigos cortos
MP_REGION_TO_CODE = {
    "Antofagasta": "II",
    "Valparaíso": "V",
    "Valparaiso": "V",
    "Metropolitana": "RM",
    "Metropolitana de Santiago": "RM",
    "RM": "RM",
    "O'Higgins": "VI",
    "Lib. Gral. Bernardo O'Higgins": "VI",
    "Libertador General Bernardo O'Higgins": "VI",
    "Los Lagos": "X",
}


def es_region_interes(region_mp: str) -> bool:
    """¿Esta región está en las zonas de operación AIDU?"""
    if not region_mp:
        return False
    code = MP_REGION_TO_CODE.get(region_mp.strip())
    return code in REGIONES_INTERES_AIDU
