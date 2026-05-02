"""
AIDU Op · Inteligencia Comercial Avanzada
==========================================
Predicción de descuento óptimo + detección de competencia recurrente
basada en histórico real de Mercado Público.

Funciones:
- predecir_descuento_optimo(): regresión sobre histórico mandante+categoría
- detectar_competencia_recurrente(): quién gana siempre con cada mandante
- forecast_pipeline(): proyección de ingresos próximos 90 días
- tasa_exito_por_dimension(): win rate desglosado
"""
import logging
from typing import Dict, List, Optional, Tuple
from datetime import date, datetime, timedelta
from collections import Counter, defaultdict
from statistics import median, mean, stdev

from app.db.migrator import get_connection

logger = logging.getLogger(__name__)


# ============================================================
# PREDICCIÓN DE DESCUENTO ÓPTIMO
# ============================================================

def predecir_descuento_optimo(
    cod_servicio_aidu: str,
    organismo: Optional[str] = None,
    monto_referencial: Optional[int] = None,
) -> Dict:
    """
    Predice el descuento óptimo basado en histórico de adjudicaciones.
    
    Combina:
    - Histórico del mandante específico (peso 50% si hay datos)
    - Histórico de la categoría AIDU (peso 30%)
    - Sweet spot del consultor (peso 20%)
    
    Returns:
        {
            "descuento_recomendado_pct": float,
            "descuento_minimo_pct": float (no bajar de aquí),
            "descuento_maximo_pct": float (sobre esto, perder margen),
            "confianza": float 0-1,
            "razon": str,
            "historico_mandante": dict,
            "historico_categoria": dict,
        }
    """
    conn = get_connection()
    try:
        # 1. Histórico del mandante específico
        hist_mandante = None
        if organismo:
            rows = conn.execute("""
                SELECT 
                    COUNT(*) as n,
                    AVG(monto_adjudicado * 1.0 / NULLIF(monto_referencial, 0)) as ratio_avg,
                    MIN(monto_adjudicado * 1.0 / NULLIF(monto_referencial, 0)) as ratio_min,
                    MAX(monto_adjudicado * 1.0 / NULLIF(monto_referencial, 0)) as ratio_max
                FROM mp_licitaciones_adj l
                INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
                WHERE l.organismo = ?
                  AND c.cod_servicio_aidu = ?
                  AND l.monto_adjudicado > 0
                  AND l.monto_referencial > 0
            """, (organismo, cod_servicio_aidu)).fetchone()
            
            if rows and rows["n"] and rows["n"] > 0:
                ratio_avg = rows["ratio_avg"] or 1.0
                hist_mandante = {
                    "n_proyectos": rows["n"],
                    "descuento_promedio_pct": round((1 - ratio_avg) * 100, 1),
                    "descuento_min_pct": round((1 - (rows["ratio_max"] or 1)) * 100, 1),
                    "descuento_max_pct": round((1 - (rows["ratio_min"] or 1)) * 100, 1),
                }
        
        # 2. Histórico de la categoría
        hist_cat = conn.execute("""
            SELECT 
                COUNT(*) as n,
                AVG(monto_adjudicado * 1.0 / NULLIF(monto_referencial, 0)) as ratio_avg
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            WHERE c.cod_servicio_aidu = ?
              AND l.monto_adjudicado > 0
              AND l.monto_referencial > 0
        """, (cod_servicio_aidu,)).fetchone()
        
        ratio_categoria = hist_cat["ratio_avg"] if hist_cat and hist_cat["ratio_avg"] else 0.90
        descuento_categoria_pct = round((1 - ratio_categoria) * 100, 1)
        
        # 3. Calcular descuento recomendado (weighted average)
        if hist_mandante and hist_mandante["n_proyectos"] >= 3:
            # Suficiente data del mandante: 60% mandante, 40% categoría
            desc_recomendado = (
                hist_mandante["descuento_promedio_pct"] * 0.6 +
                descuento_categoria_pct * 0.4
            )
            confianza = min(0.9, 0.5 + hist_mandante["n_proyectos"] * 0.05)
            razon = f"Basado en {hist_mandante['n_proyectos']} proyectos previos del mandante + categoría"
        elif hist_mandante:
            desc_recomendado = (
                hist_mandante["descuento_promedio_pct"] * 0.3 +
                descuento_categoria_pct * 0.7
            )
            confianza = 0.55
            razon = f"Basado en {hist_mandante['n_proyectos']} proyectos del mandante (poca data) + categoría"
        else:
            desc_recomendado = descuento_categoria_pct
            confianza = 0.4 if hist_cat["n"] > 5 else 0.2
            razon = f"Sin histórico del mandante. Basado en {hist_cat['n']} proyectos de la categoría"
        
        # 4. Bandas de seguridad
        desc_minimo = max(0.0, desc_recomendado - 5.0)  # No bajar más de 5pp
        desc_maximo = desc_recomendado + 8.0  # No subir más de 8pp (riesgo margen)
        
        return {
            "descuento_recomendado_pct": round(desc_recomendado, 1),
            "descuento_minimo_pct": round(desc_minimo, 1),
            "descuento_maximo_pct": round(desc_maximo, 1),
            "confianza": round(confianza, 2),
            "razon": razon,
            "historico_mandante": hist_mandante,
            "historico_categoria": {
                "n_proyectos": hist_cat["n"],
                "descuento_promedio_pct": descuento_categoria_pct,
            },
        }
    finally:
        conn.close()


# ============================================================
# DETECCIÓN DE COMPETENCIA RECURRENTE
# ============================================================

def detectar_competencia_recurrente(
    cod_servicio_aidu: Optional[str] = None,
    organismo: Optional[str] = None,
    region: Optional[str] = None,
    top_n: int = 10,
) -> Dict:
    """
    Identifica qué proveedores ganan más en cierto contexto.
    Útil para conocer quién es la competencia "fuerte" de cada nicho.
    
    Returns:
        {
            "competidores": [{"nombre": str, "n_adjudicaciones": int, "monto_total": int, "win_rate_estimado_pct": float}],
            "concentracion_top3": float (qué % gana el top 3),
            "competencia_fragmentada": bool,
        }
    """
    conn = get_connection()
    try:
        sql = """
            SELECT 
                l.proveedor_adjudicado as nombre,
                COUNT(*) as n_adjudicaciones,
                SUM(l.monto_adjudicado) as monto_total,
                AVG(l.monto_adjudicado * 1.0 / NULLIF(l.monto_referencial, 0)) as ratio_promedio
            FROM mp_licitaciones_adj l
            LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            WHERE l.proveedor_adjudicado IS NOT NULL 
              AND l.proveedor_adjudicado != ''
              AND l.monto_adjudicado > 0
        """
        params = []
        
        if cod_servicio_aidu:
            sql += " AND c.cod_servicio_aidu = ?"
            params.append(cod_servicio_aidu)
        if organismo:
            sql += " AND l.organismo = ?"
            params.append(organismo)
        if region:
            sql += " AND l.region LIKE ?"
            params.append(f"%{region}%")
        
        sql += f" GROUP BY l.proveedor_adjudicado ORDER BY n_adjudicaciones DESC LIMIT ?"
        params.append(top_n)
        
        rows = conn.execute(sql, params).fetchall()
        
        # Total para calcular win rate
        sql_total = """
            SELECT COUNT(*) as total
            FROM mp_licitaciones_adj l
            LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            WHERE l.proveedor_adjudicado IS NOT NULL AND l.proveedor_adjudicado != ''
        """
        params_t = []
        if cod_servicio_aidu:
            sql_total += " AND c.cod_servicio_aidu = ?"
            params_t.append(cod_servicio_aidu)
        if organismo:
            sql_total += " AND l.organismo = ?"
            params_t.append(organismo)
        if region:
            sql_total += " AND l.region LIKE ?"
            params_t.append(f"%{region}%")
        
        total_row = conn.execute(sql_total, params_t).fetchone()
        total = total_row["total"] if total_row else 0
        
        competidores = []
        for r in rows:
            if total > 0:
                win_rate = round((r["n_adjudicaciones"] / total) * 100, 1)
            else:
                win_rate = 0
            competidores.append({
                "nombre": r["nombre"][:80],
                "n_adjudicaciones": r["n_adjudicaciones"],
                "monto_total_clp": int(r["monto_total"] or 0),
                "win_rate_pct": win_rate,
                "descuento_promedio_pct": round((1 - (r["ratio_promedio"] or 1)) * 100, 1),
            })
        
        # Concentración del top 3
        top3_n = sum(c["n_adjudicaciones"] for c in competidores[:3])
        concentracion = round((top3_n / total) * 100, 1) if total > 0 else 0
        
        return {
            "competidores": competidores,
            "concentracion_top3_pct": concentracion,
            "competencia_fragmentada": concentracion < 30,
            "total_proyectos_analizados": total,
        }
    finally:
        conn.close()


# ============================================================
# FORECAST DE PIPELINE 90 DÍAS
# ============================================================

# Probabilidades por etapa (estimadas, calibrar con experiencia real)
PROB_ETAPA = {
    "EN_CARTERA": 0.10,
    "EN_ESTUDIO": 0.25,
    "EN_ESTUDIO": 0.45,
    "EN_OFERTA": 0.65,
    "LISTO_SUBIR": 0.40,  # bajó porque ya está en manos de evaluación
    "ADJUDICADO": 1.0,
}


def forecast_pipeline_90d() -> Dict:
    """
    Calcula proyección de ingresos próximos 90 días basado en:
    - Estado actual de cada proyecto
    - Probabilidad de adjudicación por etapa
    - Margen objetivo (de config_usuario)
    
    Returns:
        {
            "valor_pipeline_total_clp": int (suma de montos referenciales),
            "valor_esperado_clp": int (sum * prob),
            "ingresos_esperados_clp": int (valor * margen),
            "n_proyectos": int,
            "por_etapa": [{etapa, n, valor, prob, esperado}],
            "top_oportunidades": [...]
        }
    """
    from app.core.configuracion import obtener_config
    cfg = obtener_config()
    margen_obj = cfg.margen_objetivo_pct / 100
    
    conn = get_connection()
    try:
        proyectos = conn.execute("""
            SELECT id, nombre, organismo, estado, monto_referencial, fecha_cierre,
                   cod_servicio_aidu, precio_ofertado, probabilidad_estimada
            FROM aidu_proyectos
            WHERE estado NOT IN ('PERDIDA', 'NO_PARTICIPAR', 'ARCHIVADO', 'ADJUDICADO')
            ORDER BY monto_referencial DESC
        """).fetchall()
        
        proyectos = [dict(p) for p in proyectos]
        
        # Agrupar por etapa
        por_etapa_dict = defaultdict(lambda: {"n": 0, "valor": 0, "esperado": 0})
        
        for p in proyectos:
            etapa = p.get("estado", "EN_CARTERA")
            prob = PROB_ETAPA.get(etapa, 0.1)
            valor = p.get("monto_referencial") or 0
            # Si tiene precio_ofertado usarlo, sino usar 95% del referencial (asumiendo 5% descuento)
            valor_oferta = p.get("precio_ofertado") or int(valor * 0.95)
            esperado = valor_oferta * prob
            
            por_etapa_dict[etapa]["n"] += 1
            por_etapa_dict[etapa]["valor"] += valor_oferta
            por_etapa_dict[etapa]["esperado"] += esperado
        
        por_etapa = [
            {
                "etapa": etapa,
                "n_proyectos": data["n"],
                "valor_total_clp": int(data["valor"]),
                "probabilidad_pct": round(PROB_ETAPA.get(etapa, 0.1) * 100, 0),
                "valor_esperado_clp": int(data["esperado"]),
            }
            for etapa, data in por_etapa_dict.items()
        ]
        # Orden por flujo natural
        orden = ["EN_CARTERA", "EN_ESTUDIO", "EN_ESTUDIO", "EN_OFERTA", "LISTO_SUBIR"]
        por_etapa.sort(key=lambda x: orden.index(x["etapa"]) if x["etapa"] in orden else 99)
        
        valor_total = sum(d["valor"] for d in por_etapa_dict.values())
        valor_esperado = sum(d["esperado"] for d in por_etapa_dict.values())
        ingresos_esperados = valor_esperado * margen_obj
        
        # Top 5 oportunidades por valor esperado
        top = []
        for p in proyectos[:20]:
            prob = PROB_ETAPA.get(p["estado"], 0.1)
            valor = p.get("monto_referencial") or 0
            valor_oferta = p.get("precio_ofertado") or int(valor * 0.95)
            esperado = valor_oferta * prob
            top.append({**p, "prob": prob, "valor_esperado": int(esperado)})
        top.sort(key=lambda x: x["valor_esperado"], reverse=True)
        
        return {
            "valor_pipeline_total_clp": int(valor_total),
            "valor_esperado_clp": int(valor_esperado),
            "ingresos_esperados_clp": int(ingresos_esperados),
            "n_proyectos_activos": len(proyectos),
            "margen_aplicado_pct": cfg.margen_objetivo_pct,
            "por_etapa": por_etapa,
            "top_oportunidades": top[:5],
        }
    finally:
        conn.close()


# ============================================================
# WIN RATE POR DIMENSIÓN
# ============================================================

def tasa_exito_por_dimension() -> Dict:
    """
    Calcula tasa de adjudicación de AIDU desglosada por:
    - Categoría AIDU
    - Mandante
    - Región
    - Rango de monto
    
    Solo considera proyectos en estado terminal (ADJUDICADA, PERDIDA, NO_PARTICIPAR).
    """
    conn = get_connection()
    try:
        # Total general
        terminal = conn.execute("""
            SELECT estado, COUNT(*) as n
            FROM aidu_proyectos
            WHERE estado IN ('ADJUDICADO', 'PERDIDA', 'NO_PARTICIPAR', 'OFERTADO')
            GROUP BY estado
        """).fetchall()
        
        total_postuladas = sum(r["n"] for r in terminal if r["estado"] in ["ADJUDICADO", "PERDIDA"])
        adjudicadas = next((r["n"] for r in terminal if r["estado"] == "ADJUDICADO"), 0)
        win_rate_global = round((adjudicadas / total_postuladas) * 100, 1) if total_postuladas > 0 else 0
        
        # Por categoría
        por_cat = conn.execute("""
            SELECT cod_servicio_aidu,
                   SUM(CASE WHEN estado = 'ADJUDICADO' THEN 1 ELSE 0 END) as ganadas,
                   SUM(CASE WHEN estado IN ('ADJUDICADO', 'PERDIDA') THEN 1 ELSE 0 END) as postuladas
            FROM aidu_proyectos
            WHERE cod_servicio_aidu IS NOT NULL
            GROUP BY cod_servicio_aidu
            HAVING postuladas > 0
            ORDER BY postuladas DESC
        """).fetchall()
        
        por_categoria = [
            {
                "categoria": r["cod_servicio_aidu"],
                "ganadas": r["ganadas"],
                "postuladas": r["postuladas"],
                "win_rate_pct": round((r["ganadas"] / r["postuladas"]) * 100, 1) if r["postuladas"] > 0 else 0,
            }
            for r in por_cat
        ]
        
        # Por mandante
        por_mand = conn.execute("""
            SELECT organismo,
                   SUM(CASE WHEN estado = 'ADJUDICADO' THEN 1 ELSE 0 END) as ganadas,
                   SUM(CASE WHEN estado IN ('ADJUDICADO', 'PERDIDA') THEN 1 ELSE 0 END) as postuladas
            FROM aidu_proyectos
            WHERE organismo IS NOT NULL AND organismo != ''
            GROUP BY organismo
            HAVING postuladas > 0
            ORDER BY postuladas DESC LIMIT 10
        """).fetchall()
        
        por_mandante = [
            {
                "mandante": r["organismo"][:50],
                "ganadas": r["ganadas"],
                "postuladas": r["postuladas"],
                "win_rate_pct": round((r["ganadas"] / r["postuladas"]) * 100, 1) if r["postuladas"] > 0 else 0,
            }
            for r in por_mand
        ]
        
        return {
            "win_rate_global_pct": win_rate_global,
            "total_postuladas": total_postuladas,
            "total_adjudicadas": adjudicadas,
            "por_categoria": por_categoria,
            "por_mandante": por_mandante,
        }
    finally:
        conn.close()


# ============================================================
# ANÁLISIS COMPLETO DE UN MANDANTE
# ============================================================

def analizar_mandante(organismo: str) -> Dict:
    """
    Análisis 360 de un mandante:
    - Cuántas licitaciones publica al año
    - Sus categorías más frecuentes
    - Su descuento promedio histórico
    - Sus proveedores recurrentes
    - Estacionalidad
    """
    conn = get_connection()
    try:
        # Stats generales
        stats = conn.execute("""
            SELECT 
                COUNT(*) as total_licitaciones,
                AVG(monto_referencial) as monto_promedio,
                MIN(monto_referencial) as monto_min,
                MAX(monto_referencial) as monto_max,
                AVG(monto_adjudicado * 1.0 / NULLIF(monto_referencial, 0)) as ratio_avg
            FROM mp_licitaciones_adj
            WHERE organismo = ? AND monto_referencial > 0
        """, (organismo,)).fetchone()
        
        if not stats or not stats["total_licitaciones"]:
            return {"encontrado": False, "organismo": organismo}
        
        # Categorías más frecuentes
        cats = conn.execute("""
            SELECT c.cod_servicio_aidu, COUNT(*) as n
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            WHERE l.organismo = ?
            GROUP BY c.cod_servicio_aidu
            ORDER BY n DESC LIMIT 5
        """, (organismo,)).fetchall()
        
        # Proveedores recurrentes
        prov = conn.execute("""
            SELECT proveedor_adjudicado, COUNT(*) as n,
                   SUM(monto_adjudicado) as total
            FROM mp_licitaciones_adj
            WHERE organismo = ? AND proveedor_adjudicado IS NOT NULL AND proveedor_adjudicado != ''
            GROUP BY proveedor_adjudicado
            ORDER BY n DESC LIMIT 5
        """, (organismo,)).fetchall()
        
        return {
            "encontrado": True,
            "organismo": organismo,
            "total_licitaciones": stats["total_licitaciones"],
            "monto_promedio_clp": int(stats["monto_promedio"] or 0),
            "monto_min_clp": int(stats["monto_min"] or 0),
            "monto_max_clp": int(stats["monto_max"] or 0),
            "descuento_promedio_pct": round((1 - (stats["ratio_avg"] or 1)) * 100, 1),
            "categorias_frecuentes": [{"categoria": r["cod_servicio_aidu"], "n": r["n"]} for r in cats],
            "proveedores_recurrentes": [
                {"nombre": r["proveedor_adjudicado"][:60], "n": r["n"], "total_clp": int(r["total"] or 0)}
                for r in prov
            ],
        }
    finally:
        conn.close()
