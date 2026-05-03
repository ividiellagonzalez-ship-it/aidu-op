"""
AIDU Op · Descarga histórica masiva
====================================
Permite descargar el histórico de Mercado Público de forma retroactiva,
con control de progreso y posibilidad de pausar/reanudar.

Estrategia:
- Descarga día a día desde fecha_inicio hasta fecha_fin
- Cada día consulta licitaciones publicadas Y adjudicadas (vía cliente API)
- Guarda en BD local de forma incremental (resilient: si se cae, retoma)
- Reporta progreso vía callback (para UI con barra de progreso)
"""
from __future__ import annotations
from typing import Callable, Dict, Optional
from datetime import date, timedelta
import logging
import json
from app.api.mercadopublico import MercadoPublicoClient
from app.db.migrator import get_connection

logger = logging.getLogger(__name__)


def _registrar_dia_descargado(fecha: date, n_vigentes: int, n_adj: int):
    """Marca un día como ya descargado para no repetir trabajo."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mp_descargas_diarias (
                fecha TEXT PRIMARY KEY,
                n_vigentes INTEGER DEFAULT 0,
                n_adjudicadas INTEGER DEFAULT 0,
                fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO mp_descargas_diarias 
            (fecha, n_vigentes, n_adjudicadas, fecha_descarga)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
        """, (fecha.isoformat(), n_vigentes, n_adj))
        conn.commit()
    finally:
        conn.close()


def dias_ya_descargados() -> set:
    """Retorna conjunto de fechas (str ISO) ya descargadas."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mp_descargas_diarias (
                fecha TEXT PRIMARY KEY,
                n_vigentes INTEGER DEFAULT 0,
                n_adjudicadas INTEGER DEFAULT 0,
                fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        rows = conn.execute(
            "SELECT fecha FROM mp_descargas_diarias"
        ).fetchall()
        return {r["fecha"] for r in rows}
    finally:
        conn.close()


def _parse_fecha(s):
    """Parser fechas tolerante."""
    if not s:
        return None
    s = str(s).strip()
    if "T" in s:
        s = s.split("T")[0]
    return s[:10] if len(s) >= 10 else None


def _persistir_licitaciones(licitaciones_raw, tabla: str = "mp_licitaciones_vigentes") -> Dict:
    """
    Persiste un batch de licitaciones en la tabla indicada.
    tabla = 'mp_licitaciones_vigentes' o 'mp_licitaciones_adj'
    """
    if not licitaciones_raw:
        return {"nuevas": 0, "actualizadas": 0, "fallidas": 0}
    
    nuevas = 0
    actualizadas = 0
    fallidas = 0
    
    conn = get_connection()
    try:
        for lic in licitaciones_raw:
            try:
                codigo = lic.get("CodigoExterno") or lic.get("codigo_externo")
                if not codigo:
                    fallidas += 1
                    continue
                
                # Verificar si existe
                existe = conn.execute(
                    f"SELECT codigo_externo FROM {tabla} WHERE codigo_externo = ?",
                    (codigo,)
                ).fetchone()
                
                # URL canónica (cuando la API la provee)
                url_canonica = (
                    lic.get("UrlAcceso") or 
                    lic.get("urlAcceso") or 
                    lic.get("url_acceso") or
                    None
                )
                
                comprador = lic.get("Comprador", {}) if isinstance(lic.get("Comprador"), dict) else {}
                adjudicacion = lic.get("Adjudicacion", {}) if isinstance(lic.get("Adjudicacion"), dict) else {}
                
                datos = {
                    "codigo_externo": codigo,
                    "nombre": lic.get("Nombre") or lic.get("nombre", ""),
                    "descripcion": lic.get("Descripcion") or lic.get("descripcion", ""),
                    "organismo": comprador.get("NombreOrganismo") or lic.get("organismo", ""),
                    "organismo_codigo": comprador.get("CodigoOrganismo", ""),
                    "region": lic.get("Region") or comprador.get("RegionUnidad") or "",
                    "comuna": lic.get("Comuna") or comprador.get("ComunaUnidad") or "",
                    "tipo": lic.get("Tipo", ""),
                    "fecha_publicacion": _parse_fecha(lic.get("FechaPublicacion") or lic.get("fecha_publicacion")),
                    "fecha_cierre": _parse_fecha(lic.get("FechaCierre") or lic.get("fecha_cierre")),
                    "monto_referencial": lic.get("MontoEstimado") or lic.get("monto_referencial") or 0,
                    "moneda": lic.get("Moneda", "CLP"),
                    "estado": lic.get("Estado", "publicada").lower() if isinstance(lic.get("Estado"), str) else "publicada",
                    "url_mp_canonica": url_canonica,
                    "raw_json": json.dumps(lic, ensure_ascii=False),
                }
                
                # Campos extra para adjudicadas
                if tabla == "mp_licitaciones_adj":
                    datos["fecha_adjudicacion"] = _parse_fecha(adjudicacion.get("Fecha")) or _parse_fecha(lic.get("FechaAdjudicacion"))
                    datos["monto_adjudicado"] = lic.get("MontoAdjudicado") or 0
                    datos["n_oferentes"] = adjudicacion.get("NumeroOferentes") or 0
                    datos["proveedor_adjudicado"] = ""  # Se extrae de Items si necesario
                    datos["proveedor_rut"] = ""
                    datos["pondera_precio_pct"] = 0
                
                if existe:
                    # Sólo actualizamos campos que pueden cambiar
                    if tabla == "mp_licitaciones_adj":
                        conn.execute(f"""
                            UPDATE {tabla}
                            SET nombre=?, descripcion=?, monto_adjudicado=?, 
                                fecha_adjudicacion=?, n_oferentes=?,
                                url_mp_canonica=COALESCE(?, url_mp_canonica), raw_json=?
                            WHERE codigo_externo=?
                        """, (
                            datos["nombre"], datos["descripcion"], datos["monto_adjudicado"],
                            datos["fecha_adjudicacion"], datos["n_oferentes"],
                            datos["url_mp_canonica"], datos["raw_json"], codigo
                        ))
                    else:
                        conn.execute(f"""
                            UPDATE {tabla}
                            SET nombre=?, descripcion=?, fecha_cierre=?, monto_referencial=?,
                                url_mp_canonica=COALESCE(?, url_mp_canonica), raw_json=?
                            WHERE codigo_externo=?
                        """, (
                            datos["nombre"], datos["descripcion"], datos["fecha_cierre"],
                            datos["monto_referencial"], datos["url_mp_canonica"],
                            datos["raw_json"], codigo
                        ))
                    actualizadas += 1
                else:
                    if tabla == "mp_licitaciones_adj":
                        conn.execute(f"""
                            INSERT INTO {tabla} (
                                codigo_externo, nombre, descripcion, organismo, organismo_codigo,
                                region, comuna, tipo, fecha_publicacion, fecha_cierre, fecha_adjudicacion,
                                monto_referencial, monto_adjudicado, moneda, n_oferentes,
                                proveedor_adjudicado, proveedor_rut, estado, pondera_precio_pct,
                                url_mp_canonica, raw_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            datos["codigo_externo"], datos["nombre"], datos["descripcion"],
                            datos["organismo"], datos["organismo_codigo"],
                            datos["region"], datos["comuna"], datos["tipo"],
                            datos["fecha_publicacion"], datos["fecha_cierre"], datos["fecha_adjudicacion"],
                            datos["monto_referencial"], datos["monto_adjudicado"], datos["moneda"], datos["n_oferentes"],
                            datos["proveedor_adjudicado"], datos["proveedor_rut"], "Adjudicada", datos["pondera_precio_pct"],
                            datos["url_mp_canonica"], datos["raw_json"]
                        ))
                    else:
                        conn.execute(f"""
                            INSERT INTO {tabla} (
                                codigo_externo, nombre, descripcion, organismo, organismo_codigo,
                                region, comuna, tipo, fecha_publicacion, fecha_cierre,
                                monto_referencial, moneda, estado, url_mp_canonica, raw_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            datos["codigo_externo"], datos["nombre"], datos["descripcion"],
                            datos["organismo"], datos["organismo_codigo"],
                            datos["region"], datos["comuna"], datos["tipo"],
                            datos["fecha_publicacion"], datos["fecha_cierre"],
                            datos["monto_referencial"], datos["moneda"], datos["estado"],
                            datos["url_mp_canonica"], datos["raw_json"]
                        ))
                    nuevas += 1
            except Exception as e:
                logger.error(f"Error persistiendo {codigo}: {e}")
                fallidas += 1
                continue
        
        conn.commit()
    finally:
        conn.close()
    
    return {"nuevas": nuevas, "actualizadas": actualizadas, "fallidas": fallidas}


def descargar_rango(
    fecha_inicio: date,
    fecha_fin: date,
    incluir_adjudicadas: bool = True,
    incluir_vigentes: bool = True,
    saltar_descargados: bool = True,
    progress_callback: Optional[Callable] = None,
) -> Dict:
    """
    Descarga licitaciones día a día en un rango de fechas.
    
    Args:
        fecha_inicio: primer día (inclusive)
        fecha_fin: último día (inclusive)
        incluir_adjudicadas: descargar licitaciones adjudicadas
        incluir_vigentes: descargar licitaciones vigentes/publicadas
        saltar_descargados: no re-descargar días ya procesados
        progress_callback: función(dia_actual, total, fecha, n_vigentes, n_adj, status)
    
    Returns:
        Dict con resumen
    """
    if fecha_inicio > fecha_fin:
        raise ValueError("fecha_inicio debe ser <= fecha_fin")
    
    client = MercadoPublicoClient()
    
    fechas = []
    cursor = fecha_inicio
    while cursor <= fecha_fin:
        fechas.append(cursor)
        cursor += timedelta(days=1)
    
    total = len(fechas)
    descargados_set = dias_ya_descargados() if saltar_descargados else set()
    
    stats = {
        "total_dias": total,
        "dias_procesados": 0,
        "dias_saltados": 0,
        "dias_con_error": 0,
        "total_vigentes": 0,
        "total_adjudicadas": 0,
    }
    
    for i, fecha in enumerate(fechas, start=1):
        fecha_str = fecha.isoformat()
        
        if saltar_descargados and fecha_str in descargados_set:
            stats["dias_saltados"] += 1
            if progress_callback:
                progress_callback(i, total, fecha, 0, 0, "saltado")
            continue
        
        try:
            n_vig = 0
            n_adj = 0
            
            if incluir_vigentes:
                vigentes = client.listar_vigentes_por_fecha(fecha)
                if vigentes:
                    res_v = _persistir_licitaciones(vigentes, "mp_licitaciones_vigentes")
                    n_vig = res_v.get("nuevas", 0) + res_v.get("actualizadas", 0)
            
            if incluir_adjudicadas:
                adjudicadas = client.listar_adjudicadas_por_fecha(fecha)
                if adjudicadas:
                    res_a = _persistir_licitaciones(adjudicadas, "mp_licitaciones_adj")
                    n_adj = res_a.get("nuevas", 0) + res_a.get("actualizadas", 0)
            
            _registrar_dia_descargado(fecha, n_vig, n_adj)
            
            stats["dias_procesados"] += 1
            stats["total_vigentes"] += n_vig
            stats["total_adjudicadas"] += n_adj
            
            if progress_callback:
                progress_callback(i, total, fecha, n_vig, n_adj, "ok")
        
        except Exception as e:
            logger.error(f"Error descargando {fecha}: {e}")
            stats["dias_con_error"] += 1
            if progress_callback:
                progress_callback(i, total, fecha, 0, 0, f"error: {e}")
    
    return stats


def progreso_descarga_historica() -> Dict:
    """Retorna estado de descarga histórica para mostrar al usuario."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mp_descargas_diarias (
                fecha TEXT PRIMARY KEY,
                n_vigentes INTEGER DEFAULT 0,
                n_adjudicadas INTEGER DEFAULT 0,
                fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        
        row = conn.execute("""
            SELECT 
                COUNT(*) AS n_dias,
                MIN(fecha) AS desde,
                MAX(fecha) AS hasta,
                SUM(n_vigentes) AS total_vig,
                SUM(n_adjudicadas) AS total_adj
            FROM mp_descargas_diarias
        """).fetchone()
        
        return {
            "n_dias_descargados": row["n_dias"] if row else 0,
            "fecha_desde": row["desde"] if row else None,
            "fecha_hasta": row["hasta"] if row else None,
            "total_vigentes_acumulado": row["total_vig"] or 0 if row else 0,
            "total_adjudicadas_acumulado": row["total_adj"] or 0 if row else 0,
        }
    finally:
        conn.close()
