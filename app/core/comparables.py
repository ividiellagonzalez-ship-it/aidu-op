"""
AIDU Op · Comparables del Mercado
==================================
Busca licitaciones similares en histórico Mercado Público para análisis
comparativo: rangos de precios, descuentos típicos, mandantes activos.
"""
from typing import List, Dict, Optional
import statistics

from app.db.migrator import get_connection


def buscar_comparables(
    cod_servicio_aidu: str,
    region: Optional[str] = None,
    monto_referencia: Optional[int] = None,
    limit: int = 20,
) -> Dict:
    """
    Busca licitaciones del histórico MP similares al proyecto actual.
    
    Estrategia:
    1. Filtra por categoría AIDU del proyecto
    2. Si hay región, prioriza misma región
    3. Si hay monto, prioriza rango ±50%
    4. Calcula estadísticas: descuento medio, n° oferentes promedio, etc.
    """
    conn = get_connection()
    try:
        # Buscar licitaciones que tengan esta categoría AIDU asignada
        query = """
            SELECT 
                m.codigo_externo, m.nombre, m.organismo, m.region,
                m.monto_referencial, m.monto_adjudicado, m.proveedor_adjudicado,
                m.fecha_adjudicacion, m.n_oferentes
            FROM mp_licitaciones_adj m
            INNER JOIN mp_categorizacion_aidu c ON m.codigo_externo = c.codigo_externo
            WHERE c.cod_servicio_aidu = ?
              AND m.monto_adjudicado IS NOT NULL
              AND m.monto_adjudicado > 0
        """
        params = [cod_servicio_aidu]
        
        # Si hay región, ordenar para que misma región aparezca primero
        if region:
            query += " ORDER BY (CASE WHEN m.region = ? THEN 0 ELSE 1 END), m.fecha_adjudicacion DESC"
            params.append(region)
        else:
            query += " ORDER BY m.fecha_adjudicacion DESC"
        
        query += f" LIMIT {limit}"
        
        rows = conn.execute(query, params).fetchall()
        comparables = [dict(r) for r in rows]
        
        # Calcular estadísticas
        descuentos = []
        oferentes = []
        montos_adj = []
        
        for c in comparables:
            if c["monto_referencial"] and c["monto_adjudicado"]:
                desc = ((c["monto_referencial"] - c["monto_adjudicado"]) / c["monto_referencial"]) * 100
                descuentos.append(desc)
                # Calcular descuento por comparable para mostrarlo
                c["descuento_pct"] = round(desc, 1)
            else:
                c["descuento_pct"] = None
            
            if c["n_oferentes"]:
                oferentes.append(c["n_oferentes"])
            
            if c["monto_adjudicado"]:
                montos_adj.append(c["monto_adjudicado"])
        
        # Mandantes recurrentes (que aparecen más de una vez)
        mandantes = {}
        for c in comparables:
            org = c["organismo"]
            if org:
                mandantes[org] = mandantes.get(org, 0) + 1
        mandantes_top = sorted(mandantes.items(), key=lambda x: -x[1])[:5]
        
        # Proveedores recurrentes (competencia)
        proveedores = {}
        for c in comparables:
            prov = c["proveedor_adjudicado"]
            if prov:
                proveedores[prov] = proveedores.get(prov, 0) + 1
        competencia_top = sorted(proveedores.items(), key=lambda x: -x[1])[:5]
        
        return {
            "comparables": comparables,
            "total_encontrados": len(comparables),
            "stats": {
                "descuento_promedio": round(statistics.mean(descuentos), 1) if descuentos else None,
                "descuento_mediano": round(statistics.median(descuentos), 1) if descuentos else None,
                "descuento_min": round(min(descuentos), 1) if descuentos else None,
                "descuento_max": round(max(descuentos), 1) if descuentos else None,
                "n_oferentes_promedio": round(statistics.mean(oferentes), 1) if oferentes else None,
                "monto_adj_promedio": round(statistics.mean(montos_adj)) if montos_adj else None,
                "monto_adj_mediano": round(statistics.median(montos_adj)) if montos_adj else None,
            },
            "mandantes_recurrentes": [
                {"nombre": m, "cantidad": n} for m, n in mandantes_top
            ],
            "competencia": [
                {"nombre": p, "adjudicaciones": n} for p, n in competencia_top
            ],
        }
    finally:
        conn.close()


def buscar_comparables_proyecto(proyecto_id: int, limit: int = 20) -> Dict:
    """Versión que toma el proyecto_id y obtiene la categoría/región automáticamente."""
    conn = get_connection()
    try:
        p = conn.execute(
            "SELECT cod_servicio_aidu, region, monto_referencial FROM aidu_proyectos WHERE id = ?",
            (proyecto_id,)
        ).fetchone()
    finally:
        conn.close()
    
    if not p or not p["cod_servicio_aidu"]:
        return {
            "comparables": [],
            "total_encontrados": 0,
            "stats": {},
            "mandantes_recurrentes": [],
            "competencia": [],
        }
    
    return buscar_comparables(
        cod_servicio_aidu=p["cod_servicio_aidu"],
        region=p["region"],
        monto_referencia=p["monto_referencial"],
        limit=limit,
    )
