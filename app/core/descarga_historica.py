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


def _registrar_cambio_historial(conn, codigo: str, campo: str, valor_ant, valor_nuevo, hash_ant: str, hash_nuevo: str, fuente_cambio: str):
    """Persiste un cambio detectado en mp_historial_cambios."""
    try:
        conn.execute("""
            INSERT INTO mp_historial_cambios
            (codigo_externo, campo, valor_anterior, valor_nuevo, hash_anterior, hash_nuevo, fuente_cambio)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            codigo, campo,
            str(valor_ant) if valor_ant is not None else None,
            str(valor_nuevo) if valor_nuevo is not None else None,
            hash_ant, hash_nuevo, fuente_cambio
        ))
    except Exception as e:
        logger.warning(f"No se pudo registrar cambio en historial para {codigo}.{campo}: {e}")


def _detectar_cambios(antiguo: dict, nuevo: dict, campos_monitoreados: list) -> list:
    """
    Compara valores antiguo vs nuevo en los campos monitoreados.
    Retorna lista de tuplas (campo, valor_ant, valor_nuevo) para los que cambiaron.
    """
    cambios = []
    for campo in campos_monitoreados:
        val_ant = antiguo.get(campo) if isinstance(antiguo, dict) else getattr(antiguo, campo, None)
        val_nuevo = nuevo.get(campo)
        # Normalizar para comparación: None == "" == 0 son distintos
        if val_ant != val_nuevo:
            # Excepto si ambos son falsy "vacíos" (None, "", 0)
            if (val_ant in (None, "", 0)) and (val_nuevo in (None, "", 0)):
                continue
            cambios.append((campo, val_ant, val_nuevo))
    return cambios


def _persistir_licitaciones(licitaciones_raw, tabla: str = "mp_licitaciones_vigentes", fuente: str = "api_diaria") -> Dict:
    """
    UPSERT con merge inteligente:
    1. Si NO existe → INSERT con hash + fuente
    2. Si SÍ existe:
       - Calcular hash nuevo
       - Si hash difiere → detectar campos cambiados, registrar diff en historial,
         luego UPDATE
       - Si hash igual → skip silencioso (no escribimos nada, no contamos)
    
    Tras INSERT/UPDATE → llamar enriquecer_codigo() para repoblar tablas relacionales.
    
    DEFENSIVO: detecta si las columnas v18 (hash_raw_json, fuente) existen en la
    tabla. Si no existen, opera en modo legacy sin romper.
    """
    if not licitaciones_raw:
        return {"nuevas": 0, "actualizadas": 0, "sin_cambios": 0, "fallidas": 0, "cambios_detectados": 0}
    
    # Import lazy para evitar circulares
    try:
        from app.core.enriquecimiento import enriquecer_codigo, _hash_raw
    except ImportError:
        # Si el módulo no existe, modo legacy completo
        enriquecer_codigo = None
        import hashlib
        def _hash_raw(s):
            return hashlib.sha256((s or "").encode()).hexdigest()[:16] if s else ""
    
    nuevas = 0
    actualizadas = 0
    sin_cambios = 0
    fallidas = 0
    cambios_detectados = 0
    
    # Campos cuyo cambio es relevante para auditar
    campos_monitoreados_vigentes = ["nombre", "monto_referencial", "fecha_cierre", "estado"]
    campos_monitoreados_adj = ["nombre", "monto_adjudicado", "fecha_adjudicacion", "n_oferentes", "estado"]
    campos_monitoreados = campos_monitoreados_adj if tabla == "mp_licitaciones_adj" else campos_monitoreados_vigentes
    
    conn = get_connection()
    try:
        # Detectar columnas disponibles en la tabla destino (defensivo)
        cols_existentes = {row[1] for row in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        tiene_hash = "hash_raw_json" in cols_existentes
        tiene_fuente = "fuente" in cols_existentes
        tiene_url_canonica = "url_mp_canonica" in cols_existentes
        # Detectar si tabla historial existe
        tiene_historial = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mp_historial_cambios'"
        ).fetchone())
        
        for lic in licitaciones_raw:
            try:
                codigo = lic.get("CodigoExterno") or lic.get("codigo_externo")
                if not codigo:
                    fallidas += 1
                    continue
                
                # Calcular hash del raw nuevo (siempre, por si tiene_hash sea True)
                raw_str_nuevo = json.dumps(lic, ensure_ascii=False)
                hash_nuevo = _hash_raw(raw_str_nuevo) if tiene_hash else ""
                
                # ¿Existe?
                if tiene_hash:
                    existe = conn.execute(
                        f"SELECT codigo_externo, hash_raw_json FROM {tabla} WHERE codigo_externo = ?",
                        (codigo,)
                    ).fetchone()
                else:
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
                    "raw_json": raw_str_nuevo,
                    "hash_raw_json": hash_nuevo,
                    "fuente": fuente,
                }
                
                if tabla == "mp_licitaciones_adj":
                    datos["fecha_adjudicacion"] = _parse_fecha(adjudicacion.get("Fecha")) or _parse_fecha(lic.get("FechaAdjudicacion"))
                    datos["monto_adjudicado"] = lic.get("MontoAdjudicado") or 0
                    datos["n_oferentes"] = adjudicacion.get("NumeroOferentes") or 0
                    datos["proveedor_adjudicado"] = ""
                    datos["proveedor_rut"] = ""
                    datos["pondera_precio_pct"] = 0
                
                if existe:
                    if tiene_hash:
                        hash_anterior = existe["hash_raw_json"] if existe["hash_raw_json"] else ""
                        # Si hash igual → skip silencioso (idempotencia)
                        if hash_anterior == hash_nuevo and hash_anterior:
                            sin_cambios += 1
                            continue
                        
                        # Hash distinto → detectar diferencias específicas
                        if hash_anterior and tiene_historial:
                            cols_str = ", ".join(campos_monitoreados)
                            row_ant = conn.execute(
                                f"SELECT {cols_str} FROM {tabla} WHERE codigo_externo = ?",
                                (codigo,)
                            ).fetchone()
                            antiguo = dict(row_ant) if row_ant else {}
                            cambios = _detectar_cambios(antiguo, datos, campos_monitoreados)
                            for campo, va, vn in cambios:
                                _registrar_cambio_historial(conn, codigo, campo, va, vn, hash_anterior, hash_nuevo, fuente)
                                cambios_detectados += 1
                    
                    # Construir UPDATE dinámico según columnas disponibles
                    if tabla == "mp_licitaciones_adj":
                        sets = ["nombre=?", "descripcion=?", "monto_adjudicado=?", "fecha_adjudicacion=?", "n_oferentes=?", "raw_json=?"]
                        vals = [datos["nombre"], datos["descripcion"], datos["monto_adjudicado"],
                                datos["fecha_adjudicacion"], datos["n_oferentes"], datos["raw_json"]]
                        if tiene_url_canonica:
                            sets.append("url_mp_canonica=COALESCE(?, url_mp_canonica)")
                            vals.append(datos["url_mp_canonica"])
                        if tiene_hash:
                            sets.append("hash_raw_json=?")
                            vals.append(datos["hash_raw_json"])
                        if tiene_fuente:
                            sets.append("fuente=?")
                            vals.append(datos["fuente"])
                        vals.append(codigo)
                        conn.execute(f"UPDATE {tabla} SET {', '.join(sets)} WHERE codigo_externo=?", vals)
                    else:
                        sets = ["nombre=?", "descripcion=?", "fecha_cierre=?", "monto_referencial=?", "raw_json=?"]
                        vals = [datos["nombre"], datos["descripcion"], datos["fecha_cierre"],
                                datos["monto_referencial"], datos["raw_json"]]
                        if tiene_url_canonica:
                            sets.append("url_mp_canonica=COALESCE(?, url_mp_canonica)")
                            vals.append(datos["url_mp_canonica"])
                        if tiene_hash:
                            sets.append("hash_raw_json=?")
                            vals.append(datos["hash_raw_json"])
                        if tiene_fuente:
                            sets.append("fuente=?")
                            vals.append(datos["fuente"])
                        vals.append(codigo)
                        conn.execute(f"UPDATE {tabla} SET {', '.join(sets)} WHERE codigo_externo=?", vals)
                    actualizadas += 1
                else:
                    # INSERT dinámico según columnas disponibles
                    if tabla == "mp_licitaciones_adj":
                        cols = ["codigo_externo", "nombre", "descripcion", "organismo", "organismo_codigo",
                                "region", "comuna", "tipo", "fecha_publicacion", "fecha_cierre", "fecha_adjudicacion",
                                "monto_referencial", "monto_adjudicado", "moneda", "n_oferentes",
                                "proveedor_adjudicado", "proveedor_rut", "estado", "pondera_precio_pct", "raw_json"]
                        vals = [datos["codigo_externo"], datos["nombre"], datos["descripcion"],
                                datos["organismo"], datos["organismo_codigo"],
                                datos["region"], datos["comuna"], datos["tipo"],
                                datos["fecha_publicacion"], datos["fecha_cierre"], datos["fecha_adjudicacion"],
                                datos["monto_referencial"], datos["monto_adjudicado"], datos["moneda"], datos["n_oferentes"],
                                datos["proveedor_adjudicado"], datos["proveedor_rut"], "Adjudicada", datos["pondera_precio_pct"],
                                datos["raw_json"]]
                    else:
                        cols = ["codigo_externo", "nombre", "descripcion", "organismo", "organismo_codigo",
                                "region", "comuna", "tipo", "fecha_publicacion", "fecha_cierre",
                                "monto_referencial", "moneda", "estado", "raw_json"]
                        vals = [datos["codigo_externo"], datos["nombre"], datos["descripcion"],
                                datos["organismo"], datos["organismo_codigo"],
                                datos["region"], datos["comuna"], datos["tipo"],
                                datos["fecha_publicacion"], datos["fecha_cierre"],
                                datos["monto_referencial"], datos["moneda"], datos["estado"],
                                datos["raw_json"]]
                    
                    # Agregar columnas v18 si existen
                    if tiene_url_canonica:
                        cols.append("url_mp_canonica")
                        vals.append(datos["url_mp_canonica"])
                    if tiene_hash:
                        cols.append("hash_raw_json")
                        vals.append(datos["hash_raw_json"])
                    if tiene_fuente:
                        cols.append("fuente")
                        vals.append(datos["fuente"])
                    
                    placeholders = ", ".join(["?"] * len(vals))
                    cols_str = ", ".join(cols)
                    conn.execute(f"INSERT INTO {tabla} ({cols_str}) VALUES ({placeholders})", vals)
                    nuevas += 1
                
                # Enriquecer (defensivo: solo si está disponible y hay tablas v18)
                if enriquecer_codigo is not None:
                    try:
                        enriquecer_codigo(codigo, conn=conn, fuente_cambio=fuente)
                    except Exception as e:
                        logger.debug(f"Skip enriquecimiento {codigo}: {e}")
            except Exception as e:
                logger.error(f"Error persistiendo {codigo}: {e}")
                fallidas += 1
                continue
        
        conn.commit()
    finally:
        conn.close()
    
    return {
        "nuevas": nuevas, 
        "actualizadas": actualizadas, 
        "sin_cambios": sin_cambios,
        "fallidas": fallidas,
        "cambios_detectados": cambios_detectados,
    }


def descargar_rango(
    fecha_inicio: date,
    fecha_fin: date,
    incluir_adjudicadas: bool = True,
    incluir_vigentes: bool = True,
    incluir_agiles: bool = True,
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
        incluir_agiles: descargar Compras Ágiles (Tipo='AGIL', <100 UTM)
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
        "total_agiles": 0,
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
            n_agil = 0
            
            if incluir_vigentes:
                vigentes = client.listar_vigentes_por_fecha(fecha)
                if vigentes:
                    res_v = _persistir_licitaciones(vigentes, "mp_licitaciones_vigentes", fuente="api_historica")
                    n_vig = res_v.get("nuevas", 0) + res_v.get("actualizadas", 0)
            
            if incluir_adjudicadas:
                adjudicadas = client.listar_adjudicadas_por_fecha(fecha)
                if adjudicadas:
                    res_a = _persistir_licitaciones(adjudicadas, "mp_licitaciones_adj", fuente="api_historica")
                    n_adj = res_a.get("nuevas", 0) + res_a.get("actualizadas", 0)
            
            # Sprint 11.2: Compras Ágiles
            if incluir_agiles:
                try:
                    agiles = client.listar_agiles_por_fecha(fecha)
                    if agiles:
                        # Las Compras Ágiles vigentes van a la tabla vigentes con tipo='AGIL'
                        # Las cerradas/adjudicadas van a tabla adj
                        agiles_vigentes = [a for a in agiles if str(a.get("Estado", "")).lower() in ("publicada", "vigente", "activa")]
                        agiles_cerradas = [a for a in agiles if a not in agiles_vigentes]
                        
                        if agiles_vigentes:
                            res_av = _persistir_licitaciones(agiles_vigentes, "mp_licitaciones_vigentes", fuente="api_agil")
                            n_agil += res_av.get("nuevas", 0) + res_av.get("actualizadas", 0)
                        if agiles_cerradas:
                            res_ac = _persistir_licitaciones(agiles_cerradas, "mp_licitaciones_adj", fuente="api_agil")
                            n_agil += res_ac.get("nuevas", 0) + res_ac.get("actualizadas", 0)
                except Exception as e_agil:
                    logger.warning(f"Error AGIL {fecha}: {e_agil}")
            
            _registrar_dia_descargado(fecha, n_vig, n_adj)
            
            stats["dias_procesados"] += 1
            stats["total_vigentes"] += n_vig
            stats["total_adjudicadas"] += n_adj
            stats["total_agiles"] += n_agil
            
            if progress_callback:
                progress_callback(i, total, fecha, n_vig, n_adj, f"ok · {n_agil} AGIL" if n_agil else "ok")
        
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
