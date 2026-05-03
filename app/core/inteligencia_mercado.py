"""
AIDU Op · Inteligencia de Mercado
==================================
Métricas macro del mercado de compras públicas para el Dashboard ejecutivo.
Visión estilo "bolsa de mercado": tamaño total, market share AIDU, principales
organismos, evolución temporal, tendencias por categoría.

Todas las consultas trabajan sobre la BD local (SQLite), por lo que son rápidas
y permiten trabajar offline.
"""
from __future__ import annotations
from typing import Dict, List, Optional
from datetime import date, timedelta
from app.db.migrator import get_connection


# Regiones consideradas zonas AIDU (para market share regional)
REGIONES_AIDU_NOMBRES = [
    "Antofagasta",
    "Valparaíso",
    "Valparaiso",
    "Metropolitana",
    "Metropolitana de Santiago",
    "RM",
    "O'Higgins",
    "Lib. Gral. Bernardo O'Higgins",
    "Libertador General Bernardo O'Higgins",
    "Los Lagos",
]


def metricas_mercado_global(dias_atras: int = 365) -> Dict:
    """
    Métricas macro del mercado de compras públicas en los últimos N días.
    Es la "vista bolsa" del dashboard.
    """
    conn = get_connection()
    try:
        fecha_corte = (date.today() - timedelta(days=dias_atras)).isoformat()
        
        # Stats globales (adjudicadas en el período)
        row_global = conn.execute("""
            SELECT 
                COUNT(*) AS n_total,
                COALESCE(SUM(monto_adjudicado), 0) AS monto_total,
                COALESCE(AVG(monto_adjudicado), 0) AS monto_promedio,
                COUNT(DISTINCT organismo) AS n_organismos
            FROM mp_licitaciones_adj
            WHERE monto_adjudicado > 0
              AND (fecha_adjudicacion >= ? OR fecha_publicacion >= ?)
        """, (fecha_corte, fecha_corte)).fetchone()
        
        # Stats vigentes (snapshot actual)
        row_vigentes = conn.execute("""
            SELECT 
                COUNT(*) AS n_vigentes,
                COALESCE(SUM(monto_referencial), 0) AS monto_vigente
            FROM mp_licitaciones_vigentes
            WHERE fecha_cierre >= date('now')
        """).fetchone()
        
        return {
            "periodo_dias": dias_atras,
            "n_adjudicadas": row_global["n_total"] if row_global else 0,
            "monto_total_clp": int(row_global["monto_total"]) if row_global else 0,
            "monto_promedio_clp": int(row_global["monto_promedio"]) if row_global else 0,
            "n_organismos": row_global["n_organismos"] if row_global else 0,
            "n_vigentes": row_vigentes["n_vigentes"] if row_vigentes else 0,
            "monto_vigente_clp": int(row_vigentes["monto_vigente"]) if row_vigentes else 0,
        }
    finally:
        conn.close()


def market_share_aidu(dias_atras: int = 365) -> Dict:
    """
    Cuántas licitaciones del mercado total están dentro del perímetro AIDU
    (categorías CE-XX o GP-XX). Es nuestro % de mercado abordable.
    """
    conn = get_connection()
    try:
        fecha_corte = (date.today() - timedelta(days=dias_atras)).isoformat()
        
        # Total adjudicado en el período
        row_total = conn.execute("""
            SELECT COUNT(*) AS n, COALESCE(SUM(monto_adjudicado), 0) AS monto
            FROM mp_licitaciones_adj
            WHERE monto_adjudicado > 0
              AND (fecha_adjudicacion >= ? OR fecha_publicacion >= ?)
        """, (fecha_corte, fecha_corte)).fetchone()
        
        # Adjudicado dentro del perímetro AIDU (con categorización)
        row_aidu = conn.execute("""
            SELECT COUNT(DISTINCT l.codigo_externo) AS n,
                   COALESCE(SUM(l.monto_adjudicado), 0) AS monto
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            WHERE l.monto_adjudicado > 0
              AND (l.fecha_adjudicacion >= ? OR l.fecha_publicacion >= ?)
              AND c.cod_servicio_aidu IS NOT NULL
        """, (fecha_corte, fecha_corte)).fetchone()
        
        n_total = row_total["n"] if row_total else 0
        monto_total = row_total["monto"] if row_total else 0
        n_aidu = row_aidu["n"] if row_aidu else 0
        monto_aidu = row_aidu["monto"] if row_aidu else 0
        
        return {
            "n_mercado_total": n_total,
            "monto_mercado_total_clp": int(monto_total),
            "n_perimetro_aidu": n_aidu,
            "monto_perimetro_aidu_clp": int(monto_aidu),
            "share_n_pct": round((n_aidu / n_total * 100), 2) if n_total else 0,
            "share_monto_pct": round((monto_aidu / monto_total * 100), 2) if monto_total else 0,
        }
    finally:
        conn.close()


def distribucion_por_categoria_aidu(dias_atras: int = 365) -> List[Dict]:
    """
    Cuánto se adjudica en cada categoría AIDU.
    Para gráfico de torta o barras.
    """
    conn = get_connection()
    try:
        fecha_corte = (date.today() - timedelta(days=dias_atras)).isoformat()
        rows = conn.execute("""
            SELECT 
                c.cod_servicio_aidu AS categoria,
                COUNT(DISTINCT l.codigo_externo) AS n,
                COALESCE(SUM(l.monto_adjudicado), 0) AS monto
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            WHERE l.monto_adjudicado > 0
              AND (l.fecha_adjudicacion >= ? OR l.fecha_publicacion >= ?)
              AND c.cod_servicio_aidu IS NOT NULL
            GROUP BY c.cod_servicio_aidu
            ORDER BY monto DESC
        """, (fecha_corte, fecha_corte)).fetchall()
        
        return [
            {"categoria": r["categoria"], "n": r["n"], "monto": int(r["monto"])}
            for r in rows
        ]
    finally:
        conn.close()


def distribucion_por_region(dias_atras: int = 365, solo_aidu: bool = True) -> List[Dict]:
    """
    Tamaño del mercado por región. Si solo_aidu=True, filtra a regiones AIDU.
    """
    conn = get_connection()
    try:
        fecha_corte = (date.today() - timedelta(days=dias_atras)).isoformat()
        rows = conn.execute("""
            SELECT 
                COALESCE(NULLIF(region, ''), 'Sin región') AS region,
                COUNT(*) AS n,
                COALESCE(SUM(monto_adjudicado), 0) AS monto
            FROM mp_licitaciones_adj
            WHERE monto_adjudicado > 0
              AND (fecha_adjudicacion >= ? OR fecha_publicacion >= ?)
            GROUP BY region
            ORDER BY monto DESC
        """, (fecha_corte, fecha_corte)).fetchall()
        
        result = [
            {"region": r["region"], "n": r["n"], "monto": int(r["monto"])}
            for r in rows
        ]
        
        if solo_aidu:
            result = [
                r for r in result
                if any(rn in r["region"] for rn in REGIONES_AIDU_NOMBRES)
            ]
        return result
    finally:
        conn.close()


def top_organismos_compradores(limit: int = 10, dias_atras: int = 365) -> List[Dict]:
    """
    Ranking de organismos públicos por monto adjudicado.
    Para detectar mejores prospectos.
    """
    conn = get_connection()
    try:
        fecha_corte = (date.today() - timedelta(days=dias_atras)).isoformat()
        rows = conn.execute("""
            SELECT 
                organismo,
                COUNT(*) AS n_licitaciones,
                COALESCE(SUM(monto_adjudicado), 0) AS monto_total,
                COALESCE(AVG(monto_adjudicado), 0) AS ticket_promedio
            FROM mp_licitaciones_adj
            WHERE monto_adjudicado > 0
              AND organismo IS NOT NULL AND organismo != ''
              AND (fecha_adjudicacion >= ? OR fecha_publicacion >= ?)
            GROUP BY organismo
            ORDER BY monto_total DESC
            LIMIT ?
        """, (fecha_corte, fecha_corte, limit)).fetchall()
        
        return [
            {
                "organismo": r["organismo"],
                "n_licitaciones": r["n_licitaciones"],
                "monto_total": int(r["monto_total"]),
                "ticket_promedio": int(r["ticket_promedio"]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def evolucion_mensual(meses_atras: int = 12) -> List[Dict]:
    """
    Evolución mensual del mercado (n licitaciones + monto total).
    Para gráfico de línea estilo bolsa.
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT 
                strftime('%Y-%m', COALESCE(fecha_adjudicacion, fecha_publicacion)) AS mes,
                COUNT(*) AS n,
                COALESCE(SUM(monto_adjudicado), 0) AS monto
            FROM mp_licitaciones_adj
            WHERE monto_adjudicado > 0
              AND COALESCE(fecha_adjudicacion, fecha_publicacion) >= date('now', ?)
            GROUP BY mes
            ORDER BY mes ASC
        """, (f'-{meses_atras} months',)).fetchall()
        
        return [
            {"mes": r["mes"], "n": r["n"], "monto": int(r["monto"])}
            for r in rows
        ]
    finally:
        conn.close()


def stats_base_datos() -> Dict:
    """
    Estadísticas de la base de datos local.
    Para mostrar al usuario "manejas X registros".
    """
    conn = get_connection()
    try:
        n_vigentes = conn.execute("SELECT COUNT(*) FROM mp_licitaciones_vigentes").fetchone()[0]
        n_adj = conn.execute("SELECT COUNT(*) FROM mp_licitaciones_adj").fetchone()[0]
        n_categorizadas = conn.execute(
            "SELECT COUNT(DISTINCT codigo_externo) FROM mp_categorizacion_aidu"
        ).fetchone()[0]
        
        # Rango temporal
        row_rango = conn.execute("""
            SELECT 
                MIN(COALESCE(fecha_adjudicacion, fecha_publicacion)) AS desde,
                MAX(COALESCE(fecha_adjudicacion, fecha_publicacion)) AS hasta
            FROM mp_licitaciones_adj
            WHERE COALESCE(fecha_adjudicacion, fecha_publicacion) IS NOT NULL
        """).fetchone()
        
        return {
            "n_vigentes": n_vigentes,
            "n_historicas": n_adj,
            "n_categorizadas_aidu": n_categorizadas,
            "rango_desde": row_rango["desde"] if row_rango else None,
            "rango_hasta": row_rango["hasta"] if row_rango else None,
            "total_registros": n_vigentes + n_adj,
        }
    finally:
        conn.close()
