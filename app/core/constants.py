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
ESTADOS_PIPELINE = [
    "PROSPECTO",
    "ESTUDIO",
    "EN_PREPARACION",
    "LISTO_OFERTAR",
    "OFERTADO",
    "ADJUDICADO",
    "PERDIDO",
    "DESCARTADO",
]

ESTADOS_ACTIVOS = ["PROSPECTO", "ESTUDIO", "EN_PREPARACION", "LISTO_OFERTAR", "OFERTADO"]
ESTADOS_CERRADOS = ["ADJUDICADO", "PERDIDO", "DESCARTADO"]

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
