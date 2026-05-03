"""
AIDU Op · Inteligencia de Competencia
======================================
Análisis de competidores directos desde las tablas relacionales v18.

Funciones clave:
- competidores_top_por_categoria_aidu: ranking general por CE/GP
- competidores_por_organismo: quién gana más en cada organismo
- competencia_directa_de_aidu: proveedores que coinciden en categoría + región AIDU
- patron_favoritismo: organismos donde un proveedor gana repetidamente
- competidores_para_licitacion: top competidores históricos para un código específico

Es la base del diferenciador comercial: AIDU sabe quién es la competencia
ANTES de ofertar.
"""
from __future__ import annotations
from typing import Dict, List, Optional
import json
from app.db.migrator import get_connection


def competidores_top_por_categoria_aidu(
    cod_servicio: Optional[str] = None,
    region: Optional[str] = None,
    limit: int = 10
) -> List[Dict]:
    """
    Top proveedores por categoría AIDU (CE-XX o GP-XX) y opcionalmente región.
    
    Returns lista de dicts con: rut, nombre, n_adjudicaciones, monto_total,
    categorias, regiones.
    """
    conn = get_connection()
    try:
        sql = """
            SELECT 
                a.rut_proveedor AS rut,
                COALESCE(MAX(a.nombre_proveedor), '') AS nombre,
                COUNT(DISTINCT a.codigo_externo) AS n_adjudicaciones,
                COALESCE(SUM(a.monto_linea), 0) AS monto_total,
                GROUP_CONCAT(DISTINCT c.cod_servicio_aidu) AS categorias,
                GROUP_CONCAT(DISTINCT l.region) AS regiones
            FROM mp_adjudicaciones a
            INNER JOIN mp_licitaciones_adj l ON l.codigo_externo = a.codigo_externo
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = a.codigo_externo
            WHERE a.rut_proveedor IS NOT NULL AND a.rut_proveedor != ''
        """
        params = []
        
        if cod_servicio:
            sql += " AND c.cod_servicio_aidu = ?"
            params.append(cod_servicio)
        
        if region:
            sql += " AND l.region LIKE ?"
            params.append(f"%{region}%")
        
        sql += """
            GROUP BY a.rut_proveedor
            ORDER BY n_adjudicaciones DESC, monto_total DESC
            LIMIT ?
        """
        params.append(limit)
        
        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "rut": r["rut"],
                "nombre": r["nombre"],
                "n_adjudicaciones": r["n_adjudicaciones"],
                "monto_total": int(r["monto_total"]),
                "categorias": (r["categorias"] or "").split(",") if r["categorias"] else [],
                "regiones": (r["regiones"] or "").split(",") if r["regiones"] else [],
            }
            for r in rows
        ]
    finally:
        conn.close()


def competidores_por_organismo(organismo: str, limit: int = 10) -> List[Dict]:
    """
    Quiénes ganan más en un organismo comprador específico.
    Útil cuando AIDU quiere postular a un organismo donde no ha trabajado.
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT 
                a.rut_proveedor AS rut,
                COALESCE(MAX(a.nombre_proveedor), '') AS nombre,
                COUNT(DISTINCT a.codigo_externo) AS n_adjudicaciones,
                COALESCE(SUM(a.monto_linea), 0) AS monto_total,
                COALESCE(AVG(a.monto_linea), 0) AS ticket_promedio
            FROM mp_adjudicaciones a
            INNER JOIN mp_licitaciones_adj l ON l.codigo_externo = a.codigo_externo
            WHERE a.rut_proveedor IS NOT NULL AND a.rut_proveedor != ''
              AND l.organismo = ?
            GROUP BY a.rut_proveedor
            ORDER BY n_adjudicaciones DESC
            LIMIT ?
        """, (organismo, limit)).fetchall()
        
        return [
            {
                "rut": r["rut"],
                "nombre": r["nombre"],
                "n_adjudicaciones": r["n_adjudicaciones"],
                "monto_total": int(r["monto_total"]),
                "ticket_promedio": int(r["ticket_promedio"]),
            }
            for r in rows
        ]
    finally:
        conn.close()


def competencia_directa_aidu(
    categorias_aidu: Optional[List[str]] = None,
    regiones: Optional[List[str]] = None,
    limit: int = 20
) -> List[Dict]:
    """
    Tu competencia DIRECTA: proveedores que ganan en TUS categorías y TUS regiones.
    Es decir, los que están peleando exactamente por tu mismo nicho.
    
    Si categorias_aidu o regiones es None, usa todo el perímetro AIDU.
    """
    if categorias_aidu is None:
        categorias_aidu = []  # vacío = todas
    if regiones is None:
        regiones = []  # vacío = todas
    
    conn = get_connection()
    try:
        sql = """
            SELECT 
                a.rut_proveedor AS rut,
                COALESCE(MAX(a.nombre_proveedor), '') AS nombre,
                COUNT(DISTINCT a.codigo_externo) AS n_adjudicaciones,
                COALESCE(SUM(a.monto_linea), 0) AS monto_total,
                COALESCE(AVG(a.monto_linea), 0) AS ticket_promedio,
                GROUP_CONCAT(DISTINCT c.cod_servicio_aidu) AS categorias,
                GROUP_CONCAT(DISTINCT l.region) AS regiones,
                COUNT(DISTINCT l.organismo) AS n_organismos_distintos
            FROM mp_adjudicaciones a
            INNER JOIN mp_licitaciones_adj l ON l.codigo_externo = a.codigo_externo
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = a.codigo_externo
            WHERE a.rut_proveedor IS NOT NULL AND a.rut_proveedor != ''
              AND c.cod_servicio_aidu IS NOT NULL
        """
        params = []
        
        if categorias_aidu:
            placeholders = ",".join(["?"] * len(categorias_aidu))
            sql += f" AND c.cod_servicio_aidu IN ({placeholders})"
            params.extend(categorias_aidu)
        
        if regiones:
            # Construir OR dinámico
            cond_regiones = " OR ".join(["l.region LIKE ?" for _ in regiones])
            sql += f" AND ({cond_regiones})"
            params.extend([f"%{r}%" for r in regiones])
        
        sql += """
            GROUP BY a.rut_proveedor
            ORDER BY n_adjudicaciones DESC, monto_total DESC
            LIMIT ?
        """
        params.append(limit)
        
        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "rut": r["rut"],
                "nombre": r["nombre"],
                "n_adjudicaciones": r["n_adjudicaciones"],
                "monto_total": int(r["monto_total"]),
                "ticket_promedio": int(r["ticket_promedio"]),
                "categorias": (r["categorias"] or "").split(",") if r["categorias"] else [],
                "regiones": (r["regiones"] or "").split(",") if r["regiones"] else [],
                "n_organismos_distintos": r["n_organismos_distintos"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def patron_favoritismo(min_repeticiones: int = 3, limit: int = 20) -> List[Dict]:
    """
    Detecta organismos que adjudican repetidamente al mismo proveedor.
    Indicador de relación recurrente / posible favoritismo / barrera de entrada.
    
    Returns: lista ordenada por n_veces DESC.
    """
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT 
                l.organismo,
                a.rut_proveedor,
                MAX(a.nombre_proveedor) AS nombre_proveedor,
                COUNT(DISTINCT a.codigo_externo) AS n_veces,
                COALESCE(SUM(a.monto_linea), 0) AS monto_acumulado,
                MIN(l.fecha_adjudicacion) AS desde,
                MAX(l.fecha_adjudicacion) AS hasta
            FROM mp_adjudicaciones a
            INNER JOIN mp_licitaciones_adj l ON l.codigo_externo = a.codigo_externo
            WHERE a.rut_proveedor IS NOT NULL AND a.rut_proveedor != ''
              AND l.organismo IS NOT NULL AND l.organismo != ''
            GROUP BY l.organismo, a.rut_proveedor
            HAVING n_veces >= ?
            ORDER BY n_veces DESC, monto_acumulado DESC
            LIMIT ?
        """, (min_repeticiones, limit)).fetchall()
        
        return [
            {
                "organismo": r["organismo"],
                "rut_proveedor": r["rut_proveedor"],
                "nombre_proveedor": r["nombre_proveedor"],
                "n_veces": r["n_veces"],
                "monto_acumulado": int(r["monto_acumulado"]),
                "desde": r["desde"],
                "hasta": r["hasta"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def competidores_para_licitacion(codigo_externo: str, limit: int = 10) -> List[Dict]:
    """
    Para una licitación específica que está vigente: quiénes son los competidores
    históricos más probables, dado:
    - Mismo organismo
    - Misma categoría AIDU
    - Misma región
    
    Returns ranking de los proveedores que más han ganado en ese contexto.
    """
    conn = get_connection()
    try:
        # Obtener metadatos de la licitación target
        target = conn.execute("""
            SELECT v.organismo, v.region, c.cod_servicio_aidu
            FROM mp_licitaciones_vigentes v
            LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = v.codigo_externo
            WHERE v.codigo_externo = ?
        """, (codigo_externo,)).fetchone()
        
        if not target:
            # Tal vez es adjudicada
            target = conn.execute("""
                SELECT l.organismo, l.region, c.cod_servicio_aidu
                FROM mp_licitaciones_adj l
                LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
                WHERE l.codigo_externo = ?
            """, (codigo_externo,)).fetchone()
        
        if not target:
            return []
        
        # Buscar proveedores históricos en ese contexto
        sql = """
            SELECT 
                a.rut_proveedor AS rut,
                COALESCE(MAX(a.nombre_proveedor), '') AS nombre,
                COUNT(DISTINCT a.codigo_externo) AS n_ganadas,
                COALESCE(SUM(a.monto_linea), 0) AS monto_total,
                COALESCE(AVG(a.monto_linea), 0) AS ticket_promedio,
                MAX(l.fecha_adjudicacion) AS ultima_adjudicacion
            FROM mp_adjudicaciones a
            INNER JOIN mp_licitaciones_adj l ON l.codigo_externo = a.codigo_externo
            LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = a.codigo_externo
            WHERE a.rut_proveedor IS NOT NULL AND a.rut_proveedor != ''
              AND a.codigo_externo != ?
        """
        params = [codigo_externo]
        
        # Construir relevancia: scoring por overlap
        if target["organismo"]:
            sql += " AND (l.organismo = ? OR l.region LIKE ? OR c.cod_servicio_aidu = ?)"
            params.extend([
                target["organismo"],
                f"%{target['region']}%" if target["region"] else "%",
                target["cod_servicio_aidu"] or ""
            ])
        
        sql += """
            GROUP BY a.rut_proveedor
            ORDER BY n_ganadas DESC, monto_total DESC
            LIMIT ?
        """
        params.append(limit)
        
        rows = conn.execute(sql, params).fetchall()
        return [
            {
                "rut": r["rut"],
                "nombre": r["nombre"],
                "n_ganadas": r["n_ganadas"],
                "monto_total": int(r["monto_total"]),
                "ticket_promedio": int(r["ticket_promedio"]),
                "ultima_adjudicacion": r["ultima_adjudicacion"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def stats_competencia() -> Dict:
    """Resumen ejecutivo de competencia para Dashboard."""
    conn = get_connection()
    try:
        n_proveedores = conn.execute("SELECT COUNT(*) FROM mp_proveedores").fetchone()[0]
        
        if n_proveedores == 0:
            return {
                "n_proveedores_totales": 0,
                "top_3_por_n_adj": [],
                "top_3_por_monto": [],
                "patron_favoritismo_n": 0,
            }
        
        top_n = conn.execute("""
            SELECT rut, nombre, n_adjudicaciones 
            FROM mp_proveedores 
            ORDER BY n_adjudicaciones DESC LIMIT 3
        """).fetchall()
        
        top_monto = conn.execute("""
            SELECT rut, nombre, monto_total_adjudicado 
            FROM mp_proveedores 
            ORDER BY monto_total_adjudicado DESC LIMIT 3
        """).fetchall()
        
        n_favoritismo = conn.execute("""
            SELECT COUNT(*) FROM (
                SELECT l.organismo, a.rut_proveedor
                FROM mp_adjudicaciones a
                INNER JOIN mp_licitaciones_adj l ON l.codigo_externo = a.codigo_externo
                WHERE a.rut_proveedor IS NOT NULL AND a.rut_proveedor != ''
                GROUP BY l.organismo, a.rut_proveedor
                HAVING COUNT(DISTINCT a.codigo_externo) >= 3
            )
        """).fetchone()[0]
        
        return {
            "n_proveedores_totales": n_proveedores,
            "top_3_por_n_adj": [{"nombre": r["nombre"], "n": r["n_adjudicaciones"]} for r in top_n],
            "top_3_por_monto": [{"nombre": r["nombre"], "monto": r["monto_total_adjudicado"]} for r in top_monto],
            "patron_favoritismo_n": n_favoritismo,
        }
    finally:
        conn.close()
