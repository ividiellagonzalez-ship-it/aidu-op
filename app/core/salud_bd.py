"""
AIDU Op · Salud de la Base de Datos
=====================================
Métricas de confianza para AIDU como operador comercial:

- Cobertura: % de días sin lagunas en últimos 365 días
- Frescura: hace cuánto fue el último sync
- Calidad: % de licitaciones con datos enriquecidos completos

Cada métrica tiene umbrales:
- 🟢 verde: BD saludable
- 🟡 amarillo: atención
- 🔴 rojo: crítico

Estado global = el peor de los 3.
"""
from __future__ import annotations
from typing import Dict, List
from datetime import datetime, timedelta
from app.db.migrator import get_connection


def _semaforo(valor: float, verde: float, amarillo: float, mayor_es_mejor: bool = True) -> str:
    """
    Devuelve emoji según umbrales.
    mayor_es_mejor=True → valor alto = verde
    mayor_es_mejor=False → valor bajo = verde (ej: horas desde último sync)
    """
    if mayor_es_mejor:
        if valor >= verde:
            return "🟢"
        elif valor >= amarillo:
            return "🟡"
        return "🔴"
    else:
        if valor <= verde:
            return "🟢"
        elif valor <= amarillo:
            return "🟡"
        return "🔴"


def cobertura_bd(dias_horizonte: int = 365) -> Dict:
    """
    % de días en últimos N días que tienen al menos 1 licitación adjudicada.
    Mide si hay lagunas en la descarga histórica.
    """
    conn = get_connection()
    try:
        hoy = datetime.now().date()
        desde = hoy - timedelta(days=dias_horizonte)
        
        rows = conn.execute("""
            SELECT DISTINCT date(fecha_publicacion) AS dia
            FROM mp_licitaciones_adj
            WHERE fecha_publicacion IS NOT NULL
              AND date(fecha_publicacion) >= date(?)
              AND date(fecha_publicacion) <= date(?)
        """, (desde.isoformat(), hoy.isoformat())).fetchall()
        
        dias_con_data = len(rows)
        pct = (dias_con_data / dias_horizonte * 100) if dias_horizonte > 0 else 0
        
        return {
            "pct": round(pct, 1),
            "dias_con_data": dias_con_data,
            "dias_total": dias_horizonte,
            "semaforo": _semaforo(pct, verde=85, amarillo=60, mayor_es_mejor=True),
        }
    finally:
        conn.close()


def frescura_bd() -> Dict:
    """
    Cuántas horas desde la última actualización de la BD.
    Verde <24h, amarillo <72h, rojo >72h
    """
    conn = get_connection()
    try:
        # Buscar el max(fecha_extraccion) entre tablas relevantes
        candidatos = []
        
        for tabla in ["mp_licitaciones_vigentes", "mp_licitaciones_adj"]:
            try:
                row = conn.execute(
                    f"SELECT MAX(fecha_extraccion) AS ultima FROM {tabla} WHERE fecha_extraccion IS NOT NULL"
                ).fetchone()
                if row and row["ultima"]:
                    candidatos.append(row["ultima"])
            except Exception:
                pass
        
        if not candidatos:
            return {
                "horas": None,
                "ultima_sync": None,
                "semaforo": "🔴",
                "texto": "Nunca",
            }
        
        ultima_str = max(candidatos)
        try:
            ultima = datetime.fromisoformat(ultima_str)
        except Exception:
            ultima = datetime.strptime(ultima_str[:19], "%Y-%m-%d %H:%M:%S")
        
        ahora = datetime.now()
        delta = ahora - ultima
        horas = delta.total_seconds() / 3600
        
        if horas < 1:
            texto = f"hace {int(delta.total_seconds() / 60)} min"
        elif horas < 24:
            texto = f"hace {int(horas)}h"
        else:
            dias = int(horas / 24)
            texto = f"hace {dias}d"
        
        return {
            "horas": round(horas, 1),
            "ultima_sync": ultima_str,
            "semaforo": _semaforo(horas, verde=24, amarillo=72, mayor_es_mejor=False),
            "texto": texto,
        }
    finally:
        conn.close()


def calidad_bd() -> Dict:
    """
    % de licitaciones adjudicadas con datos enriquecidos completos:
    - Tienen al menos 1 item
    - Tienen al menos 1 adjudicación con proveedor
    - Tienen URL canónica
    
    Verde >75%, amarillo 50-75%, rojo <50%
    """
    conn = get_connection()
    try:
        n_total = conn.execute(
            "SELECT COUNT(*) FROM mp_licitaciones_adj"
        ).fetchone()[0] or 0
        
        if n_total == 0:
            return {"pct": 0, "n_completas": 0, "n_total": 0, "semaforo": "🔴", "detalle": {}}
        
        # Componentes
        n_con_items = conn.execute("""
            SELECT COUNT(DISTINCT a.codigo_externo)
            FROM mp_licitaciones_adj a
            INNER JOIN mp_licitaciones_items i ON i.codigo_externo = a.codigo_externo
        """).fetchone()[0]
        
        n_con_proveedor = conn.execute("""
            SELECT COUNT(DISTINCT a.codigo_externo)
            FROM mp_licitaciones_adj a
            INNER JOIN mp_adjudicaciones adj ON adj.codigo_externo = a.codigo_externo
            WHERE adj.rut_proveedor IS NOT NULL AND adj.rut_proveedor != ''
        """).fetchone()[0]
        
        n_con_url = conn.execute("""
            SELECT COUNT(*) FROM mp_licitaciones_adj
            WHERE url_mp_canonica IS NOT NULL AND url_mp_canonica != ''
        """).fetchone()[0]
        
        # Completas = tienen los 3
        n_completas = conn.execute("""
            SELECT COUNT(DISTINCT a.codigo_externo)
            FROM mp_licitaciones_adj a
            INNER JOIN mp_licitaciones_items i ON i.codigo_externo = a.codigo_externo
            INNER JOIN mp_adjudicaciones adj ON adj.codigo_externo = a.codigo_externo
            WHERE a.url_mp_canonica IS NOT NULL AND a.url_mp_canonica != ''
              AND adj.rut_proveedor IS NOT NULL AND adj.rut_proveedor != ''
        """).fetchone()[0]
        
        pct = round((n_completas / n_total * 100), 1) if n_total else 0
        
        return {
            "pct": pct,
            "n_completas": n_completas,
            "n_total": n_total,
            "semaforo": _semaforo(pct, verde=75, amarillo=50, mayor_es_mejor=True),
            "detalle": {
                "con_items": n_con_items,
                "con_proveedor": n_con_proveedor,
                "con_url": n_con_url,
                "pct_items": round(n_con_items / n_total * 100, 1),
                "pct_proveedor": round(n_con_proveedor / n_total * 100, 1),
                "pct_url": round(n_con_url / n_total * 100, 1),
            },
        }
    finally:
        conn.close()


def estado_global() -> Dict:
    """
    Resumen completo + estado global = peor de los 3 semáforos.
    """
    cob = cobertura_bd()
    fre = frescura_bd()
    cal = calidad_bd()
    
    semaforos = [cob["semaforo"], fre["semaforo"], cal["semaforo"]]
    
    # Peor semáforo gana
    if "🔴" in semaforos:
        global_emoji = "🔴"
        global_texto = "BD CRÍTICA"
        global_color = "#DC2626"
    elif "🟡" in semaforos:
        global_emoji = "🟡"
        global_texto = "BD ATENCIÓN"
        global_color = "#D97706"
    else:
        global_emoji = "🟢"
        global_texto = "BD SALUDABLE"
        global_color = "#16A34A"
    
    return {
        "cobertura": cob,
        "frescura": fre,
        "calidad": cal,
        "global_emoji": global_emoji,
        "global_texto": global_texto,
        "global_color": global_color,
    }
