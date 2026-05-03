"""
AIDU Op · Refresh diario de cierres
====================================
Re-consulta licitaciones cuyo fecha_cierre está entre HOY y +7 días.

Uso:
- Captura cambios de estado (Publicada → Adjudicada)
- Captura UrlAcceso canónica gratis (incluida en respuesta detallada)
- Detecta cambios upstream (correcciones MP, cambios monto, fecha)
- Actualiza historial de cambios automáticamente vía UPSERT inteligente

Costo aproximado: 50-200 calls/día (depende de cuántas vigentes están por cerrar)
Tiempo: 2-5 minutos diarios.
"""
from __future__ import annotations
from typing import Dict, List, Optional, Callable
import logging
from datetime import datetime, timedelta
from app.db.migrator import get_connection
from app.api.mercadopublico import MercadoPublicoClient
from app.core.descarga_historica import _persistir_licitaciones

logger = logging.getLogger(__name__)


def listar_codigos_por_cerrar(dias_horizonte: int = 7) -> List[str]:
    """
    Retorna códigos de licitaciones vigentes cuyo fecha_cierre está entre
    hoy y +dias_horizonte. Estas son las prioritarias para refresh.
    """
    conn = get_connection()
    try:
        hoy = datetime.now().date()
        limite = hoy + timedelta(days=dias_horizonte)
        
        rows = conn.execute("""
            SELECT codigo_externo
            FROM mp_licitaciones_vigentes
            WHERE fecha_cierre IS NOT NULL
              AND fecha_cierre != ''
              AND date(fecha_cierre) >= date(?)
              AND date(fecha_cierre) <= date(?)
            ORDER BY fecha_cierre ASC
        """, (hoy.isoformat(), limite.isoformat())).fetchall()
        
        return [r["codigo_externo"] for r in rows]
    finally:
        conn.close()


def refresh_cierres_proximos(
    ticket: Optional[str] = None,
    dias_horizonte: int = 7,
    progress_callback: Optional[Callable] = None
) -> Dict:
    """
    Refresca todas las licitaciones que cierran en los próximos N días.
    
    Para cada código:
    1. Llama API obtener_por_codigo() → respuesta detallada
    2. UPSERT con merge inteligente (en descarga_historica) detecta cambios
    3. Si pasó a Adjudicada, se actualiza estado + URL canónica + monto
    4. Historial registra automáticamente cualquier cambio
    
    progress_callback(actual, total, codigo) opcional.
    """
    codigos = listar_codigos_por_cerrar(dias_horizonte=dias_horizonte)
    total = len(codigos)
    
    stats = {
        "total_revisados": total,
        "nuevas": 0,
        "actualizadas": 0,
        "sin_cambios": 0,
        "fallidas": 0,
        "cambios_detectados": 0,
        "pasaron_a_adjudicada": 0,
    }
    
    if total == 0:
        return stats
    
    client = MercadoPublicoClient(ticket=ticket)
    
    for i, codigo in enumerate(codigos, start=1):
        try:
            detalle = client.obtener_por_codigo(codigo)
            if not detalle:
                stats["fallidas"] += 1
                continue
            
            # Determinar tabla destino según estado
            estado = detalle.get("Estado", "").lower()
            if "adjudic" in estado or "cerrad" in estado or "desierta" in estado:
                # Pasó a adjudicada → mover a tabla adj
                res = _persistir_licitaciones([detalle], "mp_licitaciones_adj", fuente="refresh_cierres")
                if res.get("nuevas", 0) > 0:
                    stats["pasaron_a_adjudicada"] += 1
            else:
                # Sigue vigente → actualizar en vigentes
                res = _persistir_licitaciones([detalle], "mp_licitaciones_vigentes", fuente="refresh_cierres")
            
            stats["nuevas"] += res.get("nuevas", 0)
            stats["actualizadas"] += res.get("actualizadas", 0)
            stats["sin_cambios"] += res.get("sin_cambios", 0)
            stats["cambios_detectados"] += res.get("cambios_detectados", 0)
            
            if progress_callback and (i % 10 == 0 or i == total):
                progress_callback(i, total, codigo)
        except Exception as e:
            logger.error(f"Error refrescando {codigo}: {e}")
            stats["fallidas"] += 1
    
    return stats


def obtener_url_canonica_lazy(codigo: str, ticket: Optional[str] = None) -> Optional[str]:
    """
    Obtiene la URL canónica de MP bajo demanda y la persiste en BD.
    
    Si la URL ya está en BD, la retorna sin llamar API.
    Si no está, hace 1 call a obtener_por_codigo() y persiste el resultado.
    """
    conn = get_connection()
    try:
        # 1) ¿Ya está en BD?
        for tabla in ["mp_licitaciones_vigentes", "mp_licitaciones_adj"]:
            row = conn.execute(
                f"SELECT url_mp_canonica FROM {tabla} WHERE codigo_externo = ?",
                (codigo,)
            ).fetchone()
            if row and row["url_mp_canonica"]:
                return row["url_mp_canonica"]
        
        # 2) No está → consultar API
        client = MercadoPublicoClient(ticket=ticket)
        detalle = client.obtener_por_codigo(codigo)
        if not detalle:
            return None
        
        url_canonica = (
            detalle.get("UrlAcceso") or
            detalle.get("urlAcceso") or
            None
        )
        if not url_canonica:
            return None
        
        # 3) Persistir
        for tabla in ["mp_licitaciones_vigentes", "mp_licitaciones_adj"]:
            existe = conn.execute(
                f"SELECT codigo_externo FROM {tabla} WHERE codigo_externo = ?",
                (codigo,)
            ).fetchone()
            if existe:
                conn.execute(
                    f"UPDATE {tabla} SET url_mp_canonica = ? WHERE codigo_externo = ?",
                    (url_canonica, codigo)
                )
                conn.commit()
                break
        
        return url_canonica
    finally:
        conn.close()
