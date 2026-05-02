"""
AIDU Op · Constantes del sistema
=================================
Configuración centralizada. Cuando se quiera cambiar tarifa, regiones,
o cualquier parámetro, se modifica AQUÍ — no en múltiples archivos.
"""

# ========================================
# ECONOMÍA
# ========================================
TARIFA_HORA_CLP = 78_000          # 2 UF/hora ≈ CLP 78.000
OVERHEAD_PCT = 18                  # Overhead AIDU sobre costo HH
MARGEN_OBJETIVO_DEFAULT = 22       # Margen apuntado por defecto
MARGEN_MINIMO_ACEPTABLE = 12       # Bajo este margen, NO postular

# ========================================
# SWEET SPOT (rango de monto óptimo)
# ========================================
SWEET_SPOT_MIN_CLP = 3_000_000
SWEET_SPOT_MAX_CLP = 15_000_000
RANGO_ACEPTABLE_MIN_CLP = 1_500_000
RANGO_ACEPTABLE_MAX_CLP = 30_000_000

# ========================================
# REGIONES (peso para match score)
# ========================================
PESOS_REGION = {
    "O'Higgins": 100,      # Base AIDU
    "Metropolitana de Santiago": 70,
    "Metropolitana": 70,
    "Maule": 60,
    "Valparaíso": 50,
}
PESO_REGION_DEFAULT = 40   # Cualquier otra región

# ========================================
# MANDANTES PRIORITARIOS (peso match score)
# ========================================
MANDANTES_RECURRENTES_AIDU = [
    "I. Municipalidad de Machalí",
    "I. Municipalidad de Rancagua",
    "I. Municipalidad de Graneros",
]

# ========================================
# ESTADOS DEL PIPELINE
# ========================================
# ESTADOS DEL EMBUDO COMERCIAL (alineados 1:1 con UI)
# 1. Buscar      → (sin estado, son licitaciones disponibles)
# 2. Cartera     → EN_CARTERA
# 3. Estudio     → EN_ESTUDIO
# 4. Ofertar     → EN_OFERTA
# 5. Subir a MP  → LISTO_SUBIR
# Cerrados       → ADJUDICADO / PERDIDO / DESCARTADO
# ========================================
ESTADOS_PIPELINE = [
    "EN_CARTERA",
    "EN_ESTUDIO",
    "EN_OFERTA",
    "LISTO_SUBIR",
    "ADJUDICADO",
    "PERDIDO",
    "DESCARTADO",
]

ESTADOS_ACTIVOS = ["EN_CARTERA", "EN_ESTUDIO", "EN_OFERTA", "LISTO_SUBIR"]
ESTADOS_CERRADOS = ["ADJUDICADO", "PERDIDO", "DESCARTADO"]

# Mapping etapa embudo → estado BD (para UI)
EMBUDO_ETAPAS = [
    ("📂", "Cartera",    "EN_CARTERA"),
    ("🔬", "Estudio",    "EN_ESTUDIO"),
    ("📝", "Ofertar",    "EN_OFERTA"),
    ("📤", "Subir a MP", "LISTO_SUBIR"),
]

# Labels amigables de estados (para mostrar en UI)
ESTADO_LABELS = {
    "EN_CARTERA":  "📂 En Cartera",
    "EN_ESTUDIO":  "🔬 En Estudio",
    "EN_OFERTA":   "📝 En Oferta",
    "LISTO_SUBIR": "📤 Listo Subir",
    "ADJUDICADO":  "🏆 Adjudicado",
    "PERDIDO":     "❌ Perdido",
    "DESCARTADO":  "🗑️ Descartado",
}

# Colores por estado
ESTADO_COLORES = {
    "EN_CARTERA":  ("#64748B", "#F1F5F9"),
    "EN_ESTUDIO":  ("#0E7490", "#CFFAFE"),
    "EN_OFERTA":   ("#9A3412", "#FED7AA"),
    "LISTO_SUBIR": ("#6B21A8", "#E9D5FF"),
    "ADJUDICADO":  ("#14532D", "#BBF7D0"),
    "PERDIDO":     ("#7F1D1D", "#FEE2E2"),
    "DESCARTADO":  ("#475569", "#F1F5F9"),
}

# ========================================
# COLORES UI (consistencia visual)
# ========================================
COLOR_PRIMARIO = "#1E40AF"     # Azul AIDU
COLOR_EXITO = "#15803D"
COLOR_ALERTA = "#D97706"
COLOR_PELIGRO = "#DC2626"
COLOR_NEUTRO = "#64748B"

# ========================================
# PESOS MATCH SCORE
# ========================================
PESO_CATEGORIA = 35
PESO_REGION = 20
PESO_MONTO = 20
PESO_MANDANTE = 10
PESO_RECENCIA = 15

# ========================================
# CATEGORÍAS AIDU (servicios)
# ========================================
CATEGORIAS_AIDU = {
    "CE-01": "Diagnóstico estructural",
    "CE-02": "Cálculo y planos estructurales",
    "CE-03": "Inspección técnica de obra (ITO) estructural",
    "CE-04": "Memorias de cálculo sismorresistente",
    "CE-05": "Peritajes estructurales",
    "CE-06": "Apoyo técnico SECPLAN (revisión bases)",
    "GP-01": "Gestión de proyectos",
    "GP-02": "Coordinación de obras",
    "GP-03": "Levantamiento procesos administrativos",
    "GP-04": "Rediseño procesos operacionales",
    "GP-05": "Diseño KPIs y tableros control",
    "CAP-01": "Capacitación técnica",
}
