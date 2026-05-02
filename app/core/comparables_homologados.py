"""
AIDU Op · Comparables Homologados
==================================
Búsqueda inteligente de licitaciones similares con homologación VISIBLE.

A diferencia de comparables.py (que es genérico), este módulo:
1. Busca matches por categoría AIDU + región + rango de monto
2. Aplica factores de homologación explícitos:
   - Inflación temporal (IPC anualizado)
   - Diferencia de monto referencial (factor de tamaño)
   - Diferencia de región (Santiago vs regiones)
3. Devuelve cada comparable con su precio normalizado Y la fórmula visible
4. Permite ranking por similitud (0-100%) con criterios explícitos

Esto es el INSUMO PRINCIPAL para que Ignacio decida si oferta o no.
"""
from typing import Dict, List, Optional
from datetime import datetime, date
import statistics

from app.db.migrator import get_connection


# ============================================================
# FACTORES DE HOMOLOGACIÓN
# ============================================================
# IPC anualizado promedio Chile últimos años (referencia conservadora)
IPC_ANUAL_PCT = 4.5

# Multiplicadores de región (descuento esperado vs Santiago)
# Santiago = baseline 1.0; Regiones = típicamente 5-10% menor competencia
FACTOR_REGION = {
    "Metropolitana de Santiago": 1.00,
    "Metropolitana": 1.00,
    "O'Higgins": 0.95,
    "Valparaíso": 0.97,
    "Maule": 0.94,
    "Biobío": 0.96,
    # Resto de regiones más alejadas
    "DEFAULT": 0.92,
}


def _factor_temporal(fecha_adj_str: str) -> float:
    """Factor de inflación entre la fecha de adjudicación y hoy."""
    if not fecha_adj_str:
        return 1.0
    try:
        fecha_adj = datetime.fromisoformat(fecha_adj_str).date()
        anios_diff = (date.today() - fecha_adj).days / 365.25
        if anios_diff <= 0:
            return 1.0
        return (1 + IPC_ANUAL_PCT / 100) ** anios_diff
    except Exception:
        return 1.0


def _factor_region(region_comp: Optional[str], region_actual: Optional[str]) -> float:
    """
    Factor de homologación cuando los proyectos son de regiones distintas.
    Si misma región, retorna 1.0. Si distinta, retorna ratio.
    """
    if not region_comp or not region_actual:
        return 1.0
    if region_comp == region_actual:
        return 1.0
    # Si comparable es de Santiago y actual es regional, comparable era más caro
    fc = FACTOR_REGION.get(region_comp, FACTOR_REGION["DEFAULT"])
    fa = FACTOR_REGION.get(region_actual, FACTOR_REGION["DEFAULT"])
    if fc == 0:
        return 1.0
    return fa / fc


def _calcular_similitud(
    cod_aidu_comp: str, cod_aidu_actual: str,
    region_comp: Optional[str], region_actual: Optional[str],
    monto_comp: int, monto_actual: int,
    fecha_adj_str: Optional[str]
) -> int:
    """
    Calcula score de similitud 0-100 con criterios explícitos:
    - Categoría AIDU exacta: 40 pts
    - Misma región: 20 pts
    - Monto similar (±25%): 25 pts (decae linealmente)
    - Reciente (<1 año): 15 pts (decae con antigüedad)
    """
    score = 0
    
    # Categoría
    if cod_aidu_comp == cod_aidu_actual:
        score += 40
    elif cod_aidu_comp and cod_aidu_actual and cod_aidu_comp[:2] == cod_aidu_actual[:2]:
        # Misma familia de servicios
        score += 25
    
    # Región
    if region_comp and region_actual and region_comp == region_actual:
        score += 20
    elif region_comp and region_actual:
        score += 5  # Al menos hay datos de región
    
    # Monto
    if monto_comp and monto_actual:
        ratio = min(monto_comp, monto_actual) / max(monto_comp, monto_actual)
        score += int(ratio * 25)
    
    # Recencia
    if fecha_adj_str:
        try:
            fecha_adj = datetime.fromisoformat(fecha_adj_str).date()
            dias = (date.today() - fecha_adj).days
            if dias <= 365:
                score += 15
            elif dias <= 730:
                score += 10
            elif dias <= 1095:
                score += 5
        except Exception:
            pass
    
    return min(score, 100)


def buscar_comparables_homologados(
    cod_servicio_aidu: str,
    region: Optional[str] = None,
    monto_referencial: Optional[int] = None,
    limit: int = 15
) -> Dict:
    """
    Busca licitaciones adjudicadas similares y las HOMOLOGA al contexto actual.
    
    Para cada comparable devuelve:
    - Datos originales (monto adj real, fecha, mandante, descuento real)
    - Monto adjudicado HOMOLOGADO (ajustado por inflación + región)
    - Factores aplicados (visibles)
    - Score de similitud (0-100)
    
    Returns:
        {
            "comparables": [...],
            "estadisticas_homologadas": {
                "monto_adj_promedio_homologado": int,
                "descuento_promedio_pct": float,
                "rango_min_homologado": int,
                "rango_max_homologado": int
            },
            "n_comparables": int,
            "criterios_homologacion": {...}
        }
    """
    if not cod_servicio_aidu:
        return _empty_result()
    
    conn = get_connection()
    try:
        # Query: licitaciones con esa categoría AIDU + adjudicadas
        query = """
            SELECT 
                m.codigo_externo, m.nombre, m.organismo, m.region,
                m.monto_referencial, m.monto_adjudicado, m.proveedor_adjudicado,
                m.fecha_adjudicacion, m.n_oferentes,
                c.cod_servicio_aidu
            FROM mp_licitaciones_adj m
            INNER JOIN mp_categorizacion_aidu c ON m.codigo_externo = c.codigo_externo
            WHERE c.cod_servicio_aidu = ?
              AND m.monto_adjudicado IS NOT NULL
              AND m.monto_adjudicado > 0
            ORDER BY m.fecha_adjudicacion DESC
            LIMIT ?
        """
        rows = conn.execute(query, (cod_servicio_aidu, limit * 2)).fetchall()  # *2 para tener margen
    finally:
        conn.close()
    
    if not rows:
        return _empty_result(criterios={
            "categoria_buscada": cod_servicio_aidu,
            "razon": "Sin comparables en categoría"
        })
    
    comparables = []
    for r in rows:
        c = dict(r)
        
        # Aplicar homologaciones
        f_temp = _factor_temporal(c.get("fecha_adjudicacion"))
        f_reg = _factor_region(c.get("region"), region)
        
        monto_adj = c.get("monto_adjudicado") or 0
        monto_adj_homol = int(monto_adj * f_temp * f_reg)
        
        # Descuento original
        ref = c.get("monto_referencial") or 0
        if ref > 0:
            descuento_pct_orig = round(((ref - monto_adj) / ref) * 100, 1)
        else:
            descuento_pct_orig = None
        
        # Score similitud
        score = _calcular_similitud(
            c.get("cod_servicio_aidu", ""), cod_servicio_aidu,
            c.get("region"), region,
            monto_adj, monto_referencial or monto_adj,
            c.get("fecha_adjudicacion")
        )
        
        comparables.append({
            **c,
            "monto_adjudicado_homologado": monto_adj_homol,
            "factor_temporal": round(f_temp, 3),
            "factor_region": round(f_reg, 3),
            "factor_total": round(f_temp * f_reg, 3),
            "descuento_pct": descuento_pct_orig,
            "similitud": score,
        })
    
    # Ordenar por similitud
    comparables.sort(key=lambda x: -x["similitud"])
    comparables = comparables[:limit]
    
    # Estadísticas homologadas
    montos_homol = [c["monto_adjudicado_homologado"] for c in comparables if c["monto_adjudicado_homologado"]]
    descuentos = [c["descuento_pct"] for c in comparables if c["descuento_pct"] is not None]
    
    return {
        "comparables": comparables,
        "n_comparables": len(comparables),
        "estadisticas_homologadas": {
            "monto_adj_promedio": int(statistics.mean(montos_homol)) if montos_homol else 0,
            "monto_adj_mediana": int(statistics.median(montos_homol)) if montos_homol else 0,
            "monto_adj_min": min(montos_homol) if montos_homol else 0,
            "monto_adj_max": max(montos_homol) if montos_homol else 0,
            "descuento_promedio_pct": round(statistics.mean(descuentos), 1) if descuentos else 0,
            "descuento_mediana_pct": round(statistics.median(descuentos), 1) if descuentos else 0,
        },
        "criterios_homologacion": {
            "ipc_anual_pct": IPC_ANUAL_PCT,
            "categoria_buscada": cod_servicio_aidu,
            "region_buscada": region or "Cualquiera",
            "monto_referencia": monto_referencial or 0,
            "explicacion": (
                f"Cada comparable se ajusta por (1) inflación: IPC {IPC_ANUAL_PCT}% anual desde su fecha de adjudicación, "
                f"y (2) región: factor {FACTOR_REGION.get(region or 'DEFAULT', 0.92):.2f} aplicado si la región difiere. "
                f"Score de similitud pondera categoría AIDU (40pts), región (20pts), monto similar (25pts), recencia (15pts)."
            )
        }
    }


def _empty_result(criterios: Optional[Dict] = None) -> Dict:
    return {
        "comparables": [],
        "n_comparables": 0,
        "estadisticas_homologadas": {
            "monto_adj_promedio": 0, "monto_adj_mediana": 0,
            "monto_adj_min": 0, "monto_adj_max": 0,
            "descuento_promedio_pct": 0, "descuento_mediana_pct": 0,
        },
        "criterios_homologacion": criterios or {}
    }
