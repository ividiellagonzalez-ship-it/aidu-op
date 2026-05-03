"""
AIDU Op · Enriquecimiento de BD desde raw_json
================================================
Extrae datos relacionales (proveedores, items, adjudicaciones, organismos, fechas)
desde el campo raw_json que ya capturamos en cada licitación.

NO consume API. Procesa registros existentes.

Uso típico:
    enriquecer_todo()              # Procesa toda la BD
    enriquecer_codigo(codigo)      # Procesa una sola licitación
    
Es idempotente: re-ejecutarlo limpia y reconstruye las tablas v18 desde raw_json.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Callable
import json
import hashlib
import logging
from collections import defaultdict
from datetime import datetime
from app.db.migrator import get_connection

logger = logging.getLogger(__name__)


def _hash_raw(raw_str: str) -> str:
    """SHA256 del raw_json (truncado a 16 chars para readability)."""
    if not raw_str:
        return ""
    return hashlib.sha256(raw_str.encode('utf-8')).hexdigest()[:16]


def _parse_fecha(s) -> Optional[str]:
    """Extrae fecha ISO YYYY-MM-DD desde formato API."""
    if not s:
        return None
    s = str(s).strip()
    if not s or s.upper() == 'NULL':
        return None
    if "T" in s:
        s = s.split("T")[0]
    return s[:10] if len(s) >= 10 else None


def _safe_get(d: dict, key: str, default=None):
    """Get tolerante: si no es dict o no tiene la key, retorna default."""
    if not isinstance(d, dict):
        return default
    return d.get(key, default)


def _extraer_items(raw: dict, codigo: str) -> List[Dict]:
    """
    Extrae items desde raw['Items']['Listado'][i] o raw['Items'] (lista directa).
    Retorna lista de dicts listos para INSERT.
    """
    items_root = raw.get("Items")
    if not items_root:
        return []
    
    if isinstance(items_root, dict):
        listado = items_root.get("Listado", []) or []
    elif isinstance(items_root, list):
        listado = items_root
    else:
        return []
    
    if not isinstance(listado, list):
        listado = [listado] if listado else []
    
    items = []
    for it in listado:
        if not isinstance(it, dict):
            continue
        items.append({
            "codigo_externo": codigo,
            "correlativo": it.get("Correlativo") or it.get("correlativo"),
            "codigo_unspsc": str(it.get("CodigoProducto") or it.get("codigoProducto") or "") or None,
            "codigo_categoria": it.get("CodigoCategoria") or it.get("codigoCategoria"),
            "categoria_nombre": it.get("Categoria") or it.get("categoria"),
            "nombre_producto": it.get("NombreProducto") or it.get("nombreProducto") or "",
            "descripcion": it.get("Descripcion") or it.get("descripcion"),
            "unidad_medida": it.get("UnidadMedida") or it.get("unidadMedida"),
            "cantidad": it.get("Cantidad") or it.get("cantidad"),
            "_adjudicacion_item": it.get("Adjudicacion") or it.get("adjudicacion"),
        })
    return items


def _extraer_adjudicaciones_de_items(items: List[Dict], codigo: str) -> List[Dict]:
    """
    Por cada item con Adjudicacion, extrae linea de adjudicación al proveedor.
    """
    adjs = []
    for item in items:
        adj_data = item.get("_adjudicacion_item")
        if not adj_data:
            continue
        
        # Puede venir como dict único o lista (multi-adjudicación por item)
        if isinstance(adj_data, dict):
            adj_list = [adj_data]
        elif isinstance(adj_data, list):
            adj_list = adj_data
        else:
            continue
        
        for adj in adj_list:
            if not isinstance(adj, dict):
                continue
            rut = adj.get("RutProveedor") or adj.get("rutProveedor")
            if not rut:
                continue
            cantidad = adj.get("CantidadAdjudicada") or adj.get("cantidadAdjudicada") or 0
            unitario = adj.get("MontoUnitario") or adj.get("montoUnitario") or 0
            try:
                cantidad_f = float(cantidad) if cantidad else 0
                unitario_i = int(float(unitario)) if unitario else 0
            except (ValueError, TypeError):
                cantidad_f = 0
                unitario_i = 0
            
            adjs.append({
                "codigo_externo": codigo,
                "item_correlativo": item.get("correlativo"),
                "rut_proveedor": str(rut).strip(),
                "nombre_proveedor": adj.get("NombreProveedor") or adj.get("nombreProveedor") or "",
                "cantidad_adjudicada": cantidad_f,
                "monto_unitario": unitario_i,
                "monto_linea": int(cantidad_f * unitario_i),
            })
    return adjs


def _extraer_fechas(raw: dict, codigo: str) -> Optional[Dict]:
    """Extrae fechas detalladas desde raw['Fechas']."""
    fechas_root = raw.get("Fechas") or raw.get("fechas")
    
    # Fechas posibles tanto en root como en sub-dict
    fechas_dict = {
        "codigo_externo": codigo,
        "fecha_creacion": _parse_fecha(_safe_get(fechas_root, "FechaCreacion") or raw.get("FechaCreacion")),
        "fecha_publicacion": _parse_fecha(_safe_get(fechas_root, "FechaPublicacion") or raw.get("FechaPublicacion")),
        "fecha_cierre": _parse_fecha(_safe_get(fechas_root, "FechaCierre") or raw.get("FechaCierre")),
        "fecha_inicio_foro": _parse_fecha(_safe_get(fechas_root, "FechaInicio")),
        "fecha_final_foro": _parse_fecha(_safe_get(fechas_root, "FechaFinal")),
        "fecha_pub_respuestas": _parse_fecha(_safe_get(fechas_root, "FechaPubRespuestas")),
        "fecha_acto_apertura_tecnica": _parse_fecha(_safe_get(fechas_root, "FechaActoAperturaTecnica")),
        "fecha_acto_apertura_economica": _parse_fecha(_safe_get(fechas_root, "FechaActoAperturaEconomica")),
        "fecha_estimada_adjudicacion": _parse_fecha(_safe_get(fechas_root, "FechaEstimadaAdjudicacion")),
        "fecha_adjudicacion": _parse_fecha(_safe_get(fechas_root, "FechaAdjudicacion") or raw.get("FechaAdjudicacion")),
        "fecha_visita_terreno": _parse_fecha(_safe_get(fechas_root, "FechaVisitaTerreno")),
        "fecha_entrega_antecedentes": _parse_fecha(_safe_get(fechas_root, "FechaEntregaAntecedentes")),
        "fecha_estimada_firma": _parse_fecha(_safe_get(fechas_root, "FechaEstimadaFirma")),
    }
    
    # Solo retornar si al menos una fecha tiene valor
    if any(v for k, v in fechas_dict.items() if k != "codigo_externo"):
        return fechas_dict
    return None


def _extraer_organismo(raw: dict) -> Optional[Dict]:
    """Extrae datos de organismo comprador."""
    comprador = raw.get("Comprador") or raw.get("comprador")
    if not isinstance(comprador, dict):
        return None
    
    codigo_org = comprador.get("CodigoOrganismo") or comprador.get("codigoOrganismo")
    nombre_org = comprador.get("NombreOrganismo") or comprador.get("nombreOrganismo") or ""
    
    if not codigo_org and not nombre_org:
        return None
    
    return {
        "codigo": str(codigo_org or nombre_org).strip(),
        "nombre": nombre_org,
        "region": comprador.get("RegionUnidad") or comprador.get("regionUnidad") or "",
        "comuna": comprador.get("ComunaUnidad") or comprador.get("comunaUnidad") or "",
    }


def enriquecer_codigo(codigo: str, conn=None, fuente_cambio: str = 'enriquecimiento') -> Dict:
    """
    Procesa una sola licitación: extrae items, adjudicaciones, fechas, organismo.
    Persiste en las tablas v18.
    
    Returns: dict con stats {items, adjudicaciones, fechas, organismo, hash}
    """
    cerrar_local = False
    if conn is None:
        conn = get_connection()
        cerrar_local = True
    
    stats = {"items": 0, "adjudicaciones": 0, "fechas": 0, "organismo": 0, "hash": None}
    
    try:
        # Buscar raw_json en vigentes o adj
        row = conn.execute(
            "SELECT raw_json FROM mp_licitaciones_adj WHERE codigo_externo = ?",
            (codigo,)
        ).fetchone()
        if not row or not row["raw_json"]:
            row = conn.execute(
                "SELECT raw_json FROM mp_licitaciones_vigentes WHERE codigo_externo = ?",
                (codigo,)
            ).fetchone()
        if not row or not row["raw_json"]:
            return stats
        
        raw_str = row["raw_json"]
        raw = json.loads(raw_str)
        stats["hash"] = _hash_raw(raw_str)
        
        # 1) Items (limpiar previos para idempotencia)
        items = _extraer_items(raw, codigo)
        if items:
            conn.execute("DELETE FROM mp_licitaciones_items WHERE codigo_externo = ?", (codigo,))
            for it in items:
                conn.execute("""
                    INSERT INTO mp_licitaciones_items 
                    (codigo_externo, correlativo, codigo_unspsc, codigo_categoria,
                     categoria_nombre, nombre_producto, descripcion, unidad_medida, cantidad)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    it["codigo_externo"], it["correlativo"], it["codigo_unspsc"],
                    it["codigo_categoria"], it["categoria_nombre"], it["nombre_producto"],
                    it["descripcion"], it["unidad_medida"], it["cantidad"]
                ))
            stats["items"] = len(items)
        
        # 2) Adjudicaciones (desde items)
        adjs = _extraer_adjudicaciones_de_items(items, codigo)
        if adjs:
            conn.execute("DELETE FROM mp_adjudicaciones WHERE codigo_externo = ?", (codigo,))
            for adj in adjs:
                conn.execute("""
                    INSERT INTO mp_adjudicaciones
                    (codigo_externo, item_correlativo, rut_proveedor, nombre_proveedor,
                     cantidad_adjudicada, monto_unitario, monto_linea)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    adj["codigo_externo"], adj["item_correlativo"], adj["rut_proveedor"],
                    adj["nombre_proveedor"], adj["cantidad_adjudicada"],
                    adj["monto_unitario"], adj["monto_linea"]
                ))
            stats["adjudicaciones"] = len(adjs)
        
        # 3) Fechas
        fechas = _extraer_fechas(raw, codigo)
        if fechas:
            conn.execute("""
                INSERT OR REPLACE INTO mp_fechas_clave
                (codigo_externo, fecha_creacion, fecha_publicacion, fecha_cierre,
                 fecha_inicio_foro, fecha_final_foro, fecha_pub_respuestas,
                 fecha_acto_apertura_tecnica, fecha_acto_apertura_economica,
                 fecha_estimada_adjudicacion, fecha_adjudicacion, fecha_visita_terreno,
                 fecha_entrega_antecedentes, fecha_estimada_firma, fecha_actualizacion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
            """, (
                fechas["codigo_externo"], fechas["fecha_creacion"], fechas["fecha_publicacion"],
                fechas["fecha_cierre"], fechas["fecha_inicio_foro"], fechas["fecha_final_foro"],
                fechas["fecha_pub_respuestas"], fechas["fecha_acto_apertura_tecnica"],
                fechas["fecha_acto_apertura_economica"], fechas["fecha_estimada_adjudicacion"],
                fechas["fecha_adjudicacion"], fechas["fecha_visita_terreno"],
                fechas["fecha_entrega_antecedentes"], fechas["fecha_estimada_firma"]
            ))
            stats["fechas"] = 1
        
        # 4) Organismo
        org = _extraer_organismo(raw)
        if org:
            existe = conn.execute(
                "SELECT codigo FROM mp_organismos WHERE codigo = ?", (org["codigo"],)
            ).fetchone()
            if not existe:
                conn.execute("""
                    INSERT INTO mp_organismos (codigo, nombre, region, comuna)
                    VALUES (?, ?, ?, ?)
                """, (org["codigo"], org["nombre"], org["region"], org["comuna"]))
                stats["organismo"] = 1
            else:
                conn.execute("""
                    UPDATE mp_organismos 
                    SET nombre=?, region=?, comuna=?, fecha_actualizacion=datetime('now', 'localtime')
                    WHERE codigo=?
                """, (org["nombre"], org["region"], org["comuna"], org["codigo"]))
        
        # 5) Persistir hash en la licitación
        conn.execute(
            "UPDATE mp_licitaciones_adj SET hash_raw_json=? WHERE codigo_externo=?",
            (stats["hash"], codigo)
        )
        conn.execute(
            "UPDATE mp_licitaciones_vigentes SET hash_raw_json=? WHERE codigo_externo=?",
            (stats["hash"], codigo)
        )
        
        if cerrar_local:
            conn.commit()
    finally:
        if cerrar_local:
            conn.close()
    
    return stats


def _recalcular_proveedores(conn) -> int:
    """
    Reconstruye mp_proveedores desde mp_adjudicaciones.
    Retorna cantidad de proveedores únicos.
    """
    conn.execute("DELETE FROM mp_proveedores")
    
    # Agregados por RUT con region/categoria desde licitaciones
    rows = conn.execute("""
        SELECT 
            a.rut_proveedor,
            COALESCE(MAX(a.nombre_proveedor), '') AS nombre,
            COUNT(DISTINCT a.codigo_externo) AS n_adj,
            COALESCE(SUM(a.monto_linea), 0) AS monto_total,
            MIN(l.fecha_adjudicacion) AS primera,
            MAX(l.fecha_adjudicacion) AS ultima,
            GROUP_CONCAT(DISTINCT l.region) AS regiones,
            GROUP_CONCAT(DISTINCT c.cod_servicio_aidu) AS categorias
        FROM mp_adjudicaciones a
        LEFT JOIN mp_licitaciones_adj l ON l.codigo_externo = a.codigo_externo
        LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = a.codigo_externo
        WHERE a.rut_proveedor IS NOT NULL AND a.rut_proveedor != ''
        GROUP BY a.rut_proveedor
    """).fetchall()
    
    for r in rows:
        regiones_json = json.dumps(
            [x for x in (r["regiones"] or "").split(",") if x] if r["regiones"] else []
        )
        categorias_json = json.dumps(
            [x for x in (r["categorias"] or "").split(",") if x] if r["categorias"] else []
        )
        conn.execute("""
            INSERT INTO mp_proveedores 
            (rut, nombre, n_adjudicaciones, monto_total_adjudicado,
             primera_adjudicacion, ultima_adjudicacion,
             regiones_operacion, categorias_aidu_principales,
             fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, (
            r["rut_proveedor"], r["nombre"], r["n_adj"], r["monto_total"],
            r["primera"], r["ultima"], regiones_json, categorias_json
        ))
    
    return len(rows)


def _recalcular_organismos(conn) -> int:
    """
    Reconstruye agregados de mp_organismos desde mp_licitaciones_adj.
    """
    rows = conn.execute("""
        SELECT 
            COALESCE(NULLIF(organismo_codigo, ''), organismo) AS codigo,
            organismo AS nombre,
            region,
            comuna,
            COUNT(*) AS n_lic,
            COALESCE(SUM(monto_adjudicado), 0) AS monto_total,
            COALESCE(AVG(monto_adjudicado), 0) AS ticket_prom,
            MIN(fecha_publicacion) AS primera,
            MAX(fecha_publicacion) AS ultima
        FROM mp_licitaciones_adj
        WHERE organismo IS NOT NULL AND organismo != ''
        GROUP BY codigo
    """).fetchall()
    
    for r in rows:
        # Proveedor favorito: el que más veces aparece adjudicado
        fav = conn.execute("""
            SELECT a.rut_proveedor, COUNT(*) AS n
            FROM mp_adjudicaciones a
            INNER JOIN mp_licitaciones_adj l ON l.codigo_externo = a.codigo_externo
            WHERE l.organismo = ? AND a.rut_proveedor != ''
            GROUP BY a.rut_proveedor
            ORDER BY n DESC
            LIMIT 1
        """, (r["nombre"],)).fetchone()
        
        n_proveedores_distintos = conn.execute("""
            SELECT COUNT(DISTINCT a.rut_proveedor)
            FROM mp_adjudicaciones a
            INNER JOIN mp_licitaciones_adj l ON l.codigo_externo = a.codigo_externo
            WHERE l.organismo = ?
        """, (r["nombre"],)).fetchone()[0]
        
        conn.execute("""
            INSERT OR REPLACE INTO mp_organismos
            (codigo, nombre, region, comuna, n_licitaciones, monto_total_comprado,
             ticket_promedio, n_proveedores_distintos, primera_licitacion, ultima_licitacion,
             proveedor_favorito_rut, proveedor_favorito_n_veces, fecha_actualizacion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, (
            r["codigo"], r["nombre"], r["region"], r["comuna"],
            r["n_lic"], int(r["monto_total"]), int(r["ticket_prom"]),
            n_proveedores_distintos, r["primera"], r["ultima"],
            fav["rut_proveedor"] if fav else None,
            fav["n"] if fav else 0,
        ))
    
    return len(rows)


def enriquecer_todo(progress_callback: Optional[Callable] = None) -> Dict:
    """
    Procesa toda la BD: enriquece todos los registros con raw_json,
    luego reconstruye los maestros (proveedores, organismos).
    
    progress_callback(actual, total, codigo) opcional.
    """
    conn = get_connection()
    try:
        # Lista todos los códigos con raw_json
        codigos = []
        for tabla in ["mp_licitaciones_adj", "mp_licitaciones_vigentes"]:
            rows = conn.execute(
                f"SELECT codigo_externo FROM {tabla} WHERE raw_json IS NOT NULL AND raw_json != ''"
            ).fetchall()
            codigos.extend([r["codigo_externo"] for r in rows])
        codigos = list(set(codigos))
        
        total = len(codigos)
        stats_global = {
            "total": total,
            "procesados": 0,
            "items_total": 0,
            "adjudicaciones_total": 0,
            "fechas_total": 0,
            "organismos_nuevos": 0,
            "errores": 0,
        }
        
        for i, codigo in enumerate(codigos, start=1):
            try:
                stats = enriquecer_codigo(codigo, conn=conn)
                stats_global["procesados"] += 1
                stats_global["items_total"] += stats["items"]
                stats_global["adjudicaciones_total"] += stats["adjudicaciones"]
                stats_global["fechas_total"] += stats["fechas"]
                stats_global["organismos_nuevos"] += stats["organismo"]
                
                if progress_callback and (i % 50 == 0 or i == total):
                    progress_callback(i, total, codigo)
            except Exception as e:
                logger.error(f"Error enriqueciendo {codigo}: {e}")
                stats_global["errores"] += 1
        
        # Reconstruir maestros
        n_prov = _recalcular_proveedores(conn)
        n_org = _recalcular_organismos(conn)
        
        stats_global["proveedores_unicos"] = n_prov
        stats_global["organismos_unicos"] = n_org
        
        conn.commit()
        return stats_global
    finally:
        conn.close()


def stats_enriquecimiento() -> Dict:
    """Estadísticas actuales del enriquecimiento de la BD."""
    conn = get_connection()
    try:
        n_items = conn.execute("SELECT COUNT(*) FROM mp_licitaciones_items").fetchone()[0]
        n_adj = conn.execute("SELECT COUNT(*) FROM mp_adjudicaciones").fetchone()[0]
        n_fechas = conn.execute("SELECT COUNT(*) FROM mp_fechas_clave").fetchone()[0]
        n_prov = conn.execute("SELECT COUNT(*) FROM mp_proveedores").fetchone()[0]
        n_org = conn.execute("SELECT COUNT(*) FROM mp_organismos").fetchone()[0]
        
        # Calidad: % licitaciones con al menos 1 item enriquecido
        n_lic_total = conn.execute(
            "SELECT COUNT(DISTINCT codigo_externo) FROM mp_licitaciones_adj"
        ).fetchone()[0] or 0
        n_lic_con_items = conn.execute(
            "SELECT COUNT(DISTINCT codigo_externo) FROM mp_licitaciones_items"
        ).fetchone()[0]
        
        calidad_pct = round((n_lic_con_items / n_lic_total * 100), 1) if n_lic_total else 0
        
        return {
            "n_items": n_items,
            "n_adjudicaciones": n_adj,
            "n_fechas": n_fechas,
            "n_proveedores": n_prov,
            "n_organismos": n_org,
            "n_licitaciones_con_items": n_lic_con_items,
            "n_licitaciones_total": n_lic_total,
            "calidad_pct": calidad_pct,
        }
    finally:
        conn.close()
