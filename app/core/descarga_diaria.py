"""
AIDU Op · Job de Descarga Diaria MP
=====================================
Descarga licitaciones vigentes desde Mercado Público.
Diseñado para correr en GitHub Actions cron (7am Chile).

Uso:
    python -m app.core.descarga_diaria

    # O programáticamente:
    from app.core.descarga_diaria import ejecutar_descarga
    resultado = ejecutar_descarga(dias_atras=2)
"""
import logging
import json
from datetime import date, timedelta
from typing import Dict, List, Optional

from app.api.mercadopublico import MercadoPublicoClient
from app.db.migrator import get_connection
from app.core.ingesta import _calcular_match_aidu

logger = logging.getLogger(__name__)


def ejecutar_descarga(dias_atras: int = 2, ticket: Optional[str] = None) -> Dict:
    """
    Descarga licitaciones VIGENTES (publicadas) de los últimos N días.
    
    Returns:
        Dict con stats: nuevas, actualizadas, fallidas, total_descargado
    """
    cliente = MercadoPublicoClient(ticket=ticket)
    
    licitaciones_raw = cliente.descargar_vigentes_recientes(dias_atras=dias_atras)
    
    if not licitaciones_raw:
        logger.warning("Sin licitaciones nuevas descargadas")
        return {
            "nuevas": 0, "actualizadas": 0, "fallidas": 0,
            "total_descargado": 0, "categorizadas_aidu": 0,
        }
    
    nuevas = 0
    actualizadas = 0
    fallidas = 0
    categorizadas = 0
    
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
                    "SELECT codigo_externo FROM mp_licitaciones_vigentes WHERE codigo_externo = ?",
                    (codigo,)
                ).fetchone()
                
                # Mapear campos del API a la BD
                # Campo URL canónica: la API retorna en consultas detalladas;
                # en consultas por fecha NO viene siempre. Cuando viene, la guardamos.
                url_canonica_api = (
                    lic.get("UrlAcceso") or 
                    lic.get("urlAcceso") or 
                    lic.get("url_acceso") or
                    None
                )
                
                datos = {
                    "codigo_externo": codigo,
                    "nombre": lic.get("Nombre") or lic.get("nombre", ""),
                    "descripcion": lic.get("Descripcion") or lic.get("descripcion", ""),
                    "organismo": (lic.get("Comprador", {}) if isinstance(lic.get("Comprador"), dict) else {}).get("NombreOrganismo") or lic.get("organismo", ""),
                    "organismo_codigo": (lic.get("Comprador", {}) if isinstance(lic.get("Comprador"), dict) else {}).get("CodigoOrganismo", ""),
                    "region": lic.get("Region") or (lic.get("Comprador", {}) if isinstance(lic.get("Comprador"), dict) else {}).get("RegionUnidad") or "",
                    "comuna": lic.get("Comuna") or (lic.get("Comprador", {}) if isinstance(lic.get("Comprador"), dict) else {}).get("ComunaUnidad") or "",
                    "tipo": lic.get("Tipo", ""),
                    "fecha_publicacion": _parse_fecha(lic.get("FechaPublicacion") or lic.get("fecha_publicacion")),
                    "fecha_cierre": _parse_fecha(lic.get("FechaCierre") or lic.get("fecha_cierre")),
                    "monto_referencial": lic.get("MontoEstimado") or lic.get("monto_referencial") or 0,
                    "moneda": lic.get("Moneda", "CLP"),
                    "estado": "publicada",
                    "url_mp_canonica": url_canonica_api,
                    "raw_json": json.dumps(lic, ensure_ascii=False),
                }
                
                if existe:
                    # Actualizar (incluye url_mp_canonica si la API la provee)
                    conn.execute("""
                        UPDATE mp_licitaciones_vigentes
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
                    # Insertar nueva
                    conn.execute("""
                        INSERT INTO mp_licitaciones_vigentes (
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
                    
                    # Categorizar AIDU automáticamente
                    try:
                        matches = _calcular_match_aidu(
                            {"nombre": datos["nombre"], "descripcion": datos["descripcion"]},
                            conn
                        )
                        for cod_aidu, confianza in matches[:1]:  # Top 1
                            conn.execute("""
                                INSERT OR REPLACE INTO mp_categorizacion_aidu
                                (codigo_externo, cod_servicio_aidu, confianza)
                                VALUES (?, ?, ?)
                            """, (codigo, cod_aidu, confianza))
                            categorizadas += 1
                    except Exception as e:
                        logger.warning(f"Categorización fallida {codigo}: {e}")
                
                conn.commit()
                
            except Exception as e:
                logger.error(f"Error procesando licitación: {e}")
                fallidas += 1
        
    finally:
        conn.close()
    
    resultado = {
        "nuevas": nuevas,
        "actualizadas": actualizadas,
        "fallidas": fallidas,
        "total_descargado": len(licitaciones_raw),
        "categorizadas_aidu": categorizadas,
    }
    
    logger.info(f"✅ Descarga completada: {resultado}")
    return resultado


def _parse_fecha(fecha_str) -> Optional[str]:
    """Normaliza fechas del API MP a formato ISO YYYY-MM-DD."""
    if not fecha_str:
        return None
    try:
        # API MP devuelve fechas tipo "2026-05-09T17:00:00"
        if isinstance(fecha_str, str) and "T" in fecha_str:
            return fecha_str.split("T")[0]
        return str(fecha_str)[:10]
    except Exception:
        return None


def listar_vigentes(
    region: Optional[str] = None,
    categoria_aidu: Optional[str] = None,
    dias_max_cierre: Optional[int] = None,
    limit: int = 100,
) -> List[Dict]:
    """
    Lista licitaciones vigentes con filtros.
    Para usar en la UI del tab '🔥 Hoy'.
    """
    conn = get_connection()
    try:
        sql = """
            SELECT 
                v.codigo_externo, v.nombre, v.descripcion,
                v.organismo, v.region, v.comuna,
                v.fecha_publicacion, v.fecha_cierre,
                v.monto_referencial, v.tipo,
                c.cod_servicio_aidu, c.confianza,
                v.fecha_descarga, v.url_mp_canonica,
                CAST(julianday(v.fecha_cierre) - julianday('now') AS INTEGER) as dias_para_cierre
            FROM mp_licitaciones_vigentes v
            LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = v.codigo_externo
            WHERE 1=1
        """
        params = []
        
        if region and region != "Todas":
            sql += " AND v.region LIKE ?"
            params.append(f"%{region}%")
        
        if categoria_aidu and categoria_aidu != "Todas":
            sql += " AND c.cod_servicio_aidu = ?"
            params.append(categoria_aidu)
        
        if dias_max_cierre is not None:
            sql += " AND CAST(julianday(v.fecha_cierre) - julianday('now') AS INTEGER) <= ?"
            params.append(dias_max_cierre)
        
        sql += " ORDER BY v.fecha_cierre ASC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def stats_vigentes() -> Dict:
    """Stats rápidas para mostrar en el tab Hoy."""
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM mp_licitaciones_vigentes").fetchone()[0]
        
        hoy_24h = conn.execute("""
            SELECT COUNT(*) FROM mp_licitaciones_vigentes 
            WHERE fecha_descarga >= datetime('now', '-1 day')
        """).fetchone()[0]
        
        cierran_3d = conn.execute("""
            SELECT COUNT(*) FROM mp_licitaciones_vigentes 
            WHERE CAST(julianday(fecha_cierre) - julianday('now') AS INTEGER) BETWEEN 0 AND 3
        """).fetchone()[0]
        
        con_match_aidu = conn.execute("""
            SELECT COUNT(DISTINCT v.codigo_externo) 
            FROM mp_licitaciones_vigentes v
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = v.codigo_externo
        """).fetchone()[0]
        
        ultima_actualizacion = conn.execute("""
            SELECT MAX(fecha_descarga) FROM mp_licitaciones_vigentes
        """).fetchone()[0]
        
        return {
            "total_vigentes": total,
            "publicadas_24h": hoy_24h,
            "cierran_proximos_3_dias": cierran_3d,
            "con_match_aidu": con_match_aidu,
            "ultima_actualizacion": ultima_actualizacion,
        }
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    print("🚀 Iniciando descarga diaria MP...")
    resultado = ejecutar_descarga(dias_atras=2)
    print(f"\n📊 Resultado:")
    for k, v in resultado.items():
        print(f"  {k}: {v}")
