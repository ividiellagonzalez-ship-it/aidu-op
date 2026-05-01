"""
AIDU Op · Motor de Inteligencia de Precios
============================================
Calcula 3 escenarios de precio (agresivo/competitivo/premium) usando
el histórico real de Mercado Público almacenado en SQLite.

Fórmula:
    Costo base AIDU = (HH × tarifa_hora) + viajes + overhead
    Precio agresivo  = costo × (1 + margen_min)  → mayor probabilidad
    Precio competitivo = mediana del mercado     → equilibrio
    Precio premium = costo × (1 + margen_alto)   → menor probabilidad
"""
from typing import Dict, Optional, List
from app.db.migrator import get_connection
from config.settings import UF_VALOR_DEFAULT, TARIFA_HORA_UF, OVERHEAD_PCT, COSTO_VIAJE


def obtener_estadisticas_categoria(cod_servicio: str, organismo: Optional[str] = None) -> Dict:
    """
    Obtiene estadísticas de mercado para una categoría AIDU.
    Si se pasa organismo, también filtra por ese comprador.
    """
    conn = get_connection()
    try:
        # Stats globales de la categoría
        stats = conn.execute("""
            SELECT
                COUNT(*) as n_total,
                AVG(CAST(l.monto_adjudicado AS REAL) / NULLIF(l.monto_referencial, 0) * 100 - 100) as descuento_avg,
                MIN(CAST(l.monto_adjudicado AS REAL) / NULLIF(l.monto_referencial, 0) * 100 - 100) as descuento_min,
                MAX(CAST(l.monto_adjudicado AS REAL) / NULLIF(l.monto_referencial, 0) * 100 - 100) as descuento_max,
                AVG(l.monto_adjudicado) as monto_avg,
                MIN(l.monto_adjudicado) as monto_min,
                MAX(l.monto_adjudicado) as monto_max
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON l.codigo_externo = c.codigo_externo
            WHERE c.cod_servicio_aidu = ?
                AND l.monto_referencial > 0
                AND l.monto_adjudicado > 0
        """, (cod_servicio,)).fetchone()

        # Calcular percentiles 25 y 75 (descuento sobre referencial)
        descuentos = conn.execute("""
            SELECT (CAST(l.monto_adjudicado AS REAL) / l.monto_referencial * 100 - 100) as desc_pct
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON l.codigo_externo = c.codigo_externo
            WHERE c.cod_servicio_aidu = ?
                AND l.monto_referencial > 0
                AND l.monto_adjudicado > 0
            ORDER BY desc_pct
        """, (cod_servicio,)).fetchall()

        descuentos_lista = sorted([d["desc_pct"] for d in descuentos])

        if descuentos_lista:
            n = len(descuentos_lista)
            p25 = descuentos_lista[n // 4] if n >= 4 else descuentos_lista[0]
            p50 = descuentos_lista[n // 2]
            p75 = descuentos_lista[(3 * n) // 4] if n >= 4 else descuentos_lista[-1]
        else:
            # Sin datos: defaults conservadores
            p25, p50, p75 = -20.0, -10.0, 0.0

        # Top adjudicatarios (competidores recurrentes)
        top_competidores = conn.execute("""
            SELECT proveedor_adjudicado, COUNT(*) as n_adj
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON l.codigo_externo = c.codigo_externo
            WHERE c.cod_servicio_aidu = ?
                AND proveedor_adjudicado IS NOT NULL
            GROUP BY proveedor_adjudicado
            ORDER BY n_adj DESC
            LIMIT 5
        """, (cod_servicio,)).fetchall()

        # Stats específicas del organismo (si se pasó)
        stats_organismo = None
        if organismo:
            stats_organismo = conn.execute("""
                SELECT COUNT(*) as n, AVG(monto_adjudicado) as monto_avg
                FROM mp_licitaciones_adj l
                INNER JOIN mp_categorizacion_aidu c ON l.codigo_externo = c.codigo_externo
                WHERE c.cod_servicio_aidu = ? AND l.organismo = ?
            """, (cod_servicio, organismo)).fetchone()

        return {
            "n_total": stats["n_total"] if stats else 0,
            "descuento_p25": p25,
            "descuento_mediana": p50,
            "descuento_p75": p75,
            "descuento_promedio": stats["descuento_avg"] if stats else None,
            "monto_promedio": stats["monto_avg"] if stats else None,
            "competidores_recurrentes": [
                {"nombre": c["proveedor_adjudicado"], "n_adj": c["n_adj"]}
                for c in top_competidores
            ],
            "n_organismo": stats_organismo["n"] if stats_organismo else 0,
            "monto_organismo": stats_organismo["monto_avg"] if stats_organismo else None,
        }
    finally:
        conn.close()


def licitaciones_similares(cod_servicio: str, limit: int = 10) -> List[Dict]:
    """Top N licitaciones más relevantes para análisis comparativo"""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT l.codigo_externo, l.nombre, l.organismo, l.region,
                   l.monto_referencial, l.monto_adjudicado,
                   c.confianza,
                   (CAST(l.monto_adjudicado AS REAL) / NULLIF(l.monto_referencial, 0) * 100 - 100) as descuento
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON l.codigo_externo = c.codigo_externo
            WHERE c.cod_servicio_aidu = ?
                AND l.monto_referencial > 0
                AND l.monto_adjudicado > 0
            ORDER BY c.confianza DESC, l.monto_adjudicado DESC
            LIMIT ?
        """, (cod_servicio, limit)).fetchall()

        return [
            {
                "codigo": r["codigo_externo"],
                "nombre": r["nombre"],
                "organismo": r["organismo"],
                "region": r["region"],
                "monto_referencial": r["monto_referencial"],
                "monto_adjudicado": r["monto_adjudicado"],
                "descuento_pct": r["descuento"],
                "similarity": r["confianza"] * 100,
            }
            for r in rows
        ]
    finally:
        conn.close()


def calcular_costo_aidu(hh_ignacio: int, hh_jorella: int, region: str) -> Dict:
    """Calcula costo base AIDU para un proyecto"""
    uf = UF_VALOR_DEFAULT
    tarifa_hora_clp = TARIFA_HORA_UF * uf
    hh_total = hh_ignacio + hh_jorella

    costo_hh = hh_total * tarifa_hora_clp
    viajes = COSTO_VIAJE.get(region, COSTO_VIAJE["Otros"])
    subtotal = costo_hh + viajes
    overhead = subtotal * OVERHEAD_PCT
    costo_total = subtotal + overhead

    return {
        "hh_total": hh_total,
        "tarifa_hora_clp": tarifa_hora_clp,
        "costo_hh": costo_hh,
        "viajes": viajes,
        "overhead": overhead,
        "costo_total": costo_total,
    }


def calcular_escenarios_precio(proyecto_id: int) -> Dict:
    """
    Calcula 3 escenarios de precio para un proyecto.
    Combina costo AIDU con inteligencia de mercado del histórico.
    """
    conn = get_connection()
    try:
        proyecto = conn.execute(
            "SELECT * FROM aidu_proyectos WHERE id = ?", (proyecto_id,)
        ).fetchone()
    finally:
        conn.close()

    if not proyecto:
        return {"error": "Proyecto no encontrado"}

    # Costo base AIDU
    costo = calcular_costo_aidu(
        proyecto["hh_ignacio_estimado"] or 50,
        proyecto["hh_jorella_estimado"] or 20,
        proyecto["region"] or "O'Higgins"
    )

    # Estadísticas del mercado
    stats = obtener_estadisticas_categoria(
        proyecto["cod_servicio_aidu"],
        proyecto["organismo"]
    )

    monto_ref = proyecto["monto_referencial"] or 0

    # 3 escenarios calculados desde el referencial usando percentiles del mercado
    precio_agresivo = monto_ref * (1 + stats["descuento_p25"] / 100) if monto_ref else costo["costo_total"] * 1.10
    precio_competitivo = monto_ref * (1 + stats["descuento_mediana"] / 100) if monto_ref else costo["costo_total"] * 1.20
    precio_premium = monto_ref * (1 + stats["descuento_p75"] / 100) if monto_ref else costo["costo_total"] * 1.35

    def calcular_margen(precio):
        if costo["costo_total"] == 0:
            return 0
        return (precio - costo["costo_total"]) / costo["costo_total"] * 100

    # Probabilidad heurística:
    # - Agresivo: alta probabilidad por precio bajo (~50-65%)
    # - Competitivo: probabilidad balanceada (~30-45%)
    # - Premium: depende de diferenciación (~15-25%)
    n_competidores = max(1, len(stats["competidores_recurrentes"]))
    factor_competencia = max(0.3, 1.0 - (n_competidores - 1) * 0.10)  # más competidores = menor prob

    prob_agresivo = min(70, int(55 * factor_competencia))
    prob_competitivo = min(50, int(40 * factor_competencia))
    prob_premium = min(30, int(20 * factor_competencia))

    return {
        "costo": costo,
        "stats": stats,
        "monto_ref": monto_ref,
        "agresivo": {
            "precio": int(precio_agresivo),
            "margen_pct": round(calcular_margen(precio_agresivo), 1),
            "descuento_pct": round(stats["descuento_p25"], 1),
            "probabilidad": prob_agresivo,
            "estrategia": "Volumen y entrada",
            "descripcion": "Precio en cuartil bajo del mercado. Maximiza probabilidad de adjudicación."
        },
        "competitivo": {
            "precio": int(precio_competitivo),
            "margen_pct": round(calcular_margen(precio_competitivo), 1),
            "descuento_pct": round(stats["descuento_mediana"], 1),
            "probabilidad": prob_competitivo,
            "estrategia": "Balance óptimo",
            "descripcion": "Alineado con mediana histórica. Mejor relación margen-probabilidad."
        },
        "premium": {
            "precio": int(precio_premium),
            "margen_pct": round(calcular_margen(precio_premium), 1),
            "descuento_pct": round(stats["descuento_p75"], 1),
            "probabilidad": prob_premium,
            "estrategia": "Diferenciación",
            "descripcion": "Apunta a clientes que valoran calidad. Margen alto si la propuesta técnica destaca."
        }
    }
