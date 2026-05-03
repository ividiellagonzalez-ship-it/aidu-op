"""
AIDU Op · Inteligencia de Precios v2 (Sprint 11.3)
====================================================
Calcula tarifas de mercado (CLP/HH, CLP/m²) y compara contra tu costo HH.

Cómo funciona:
1. Para cada licitación adjudicada, busca HH (de aidu_indicadores_extraidos
   o de tabla maestra según categoría AIDU)
2. Calcula tarifa = monto_adjudicado / HH
3. Agrega por categoría AIDU × tipo licitación (LE/LP/LR/LQ/AGIL)
4. Compara contra tu costo HH para mostrar margen
"""
from __future__ import annotations
from typing import Dict, List, Optional
import statistics
from app.db.migrator import get_connection


# Costo HH AIDU (CLP)
COSTO_HH_AIDU = 92040  # 2 UF × 46.020 CLP/UF


def tarifas_por_categoria_y_tipo() -> List[Dict]:
    """
    Calcula CLP/HH por categoría AIDU × tipo licitación.
    """
    conn = get_connection()
    try:
        sql = """
            SELECT 
                c.cod_servicio_aidu AS cat,
                COALESCE(NULLIF(l.tipo, ''), 'Sin tipo') AS tipo,
                l.codigo_externo,
                l.monto_adjudicado,
                COALESCE(i.hh_estimadas_aidu, h.hh_tipicas) AS hh
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            LEFT JOIN aidu_indicadores_extraidos i ON i.codigo_externo = l.codigo_externo
            LEFT JOIN aidu_homologacion_categoria h ON h.cod_servicio_aidu = c.cod_servicio_aidu
            WHERE l.monto_adjudicado > 0
              AND COALESCE(i.hh_estimadas_aidu, h.hh_tipicas) > 0
        """
        rows = conn.execute(sql).fetchall()
        
        agrupado = {}
        for r in rows:
            key = (r["cat"], r["tipo"])
            if key not in agrupado:
                agrupado[key] = {"cat": r["cat"], "tipo": r["tipo"],
                                  "n": 0, "monto": 0, "hh": 0, "ratios": []}
            ratio = r["monto_adjudicado"] / r["hh"] if r["hh"] > 0 else 0
            if 0 < ratio < 10_000_000:
                agrupado[key]["n"] += 1
                agrupado[key]["monto"] += r["monto_adjudicado"]
                agrupado[key]["hh"] += r["hh"]
                agrupado[key]["ratios"].append(ratio)
        
        resultados = []
        for key, g in agrupado.items():
            if g["n"] == 0 or not g["ratios"]:
                continue
            ratios = g["ratios"]
            mediana = statistics.median(ratios) if len(ratios) > 1 else ratios[0]
            margen = ((mediana - COSTO_HH_AIDU) / COSTO_HH_AIDU * 100) if COSTO_HH_AIDU else 0
            resultados.append({
                "categoria": g["cat"],
                "tipo": g["tipo"],
                "n_licitaciones": g["n"],
                "monto_total": int(g["monto"]),
                "hh_total": int(g["hh"]),
                "clp_hh_promedio": int(sum(ratios) / len(ratios)),
                "clp_hh_mediana": int(mediana),
                "clp_hh_min": int(min(ratios)),
                "clp_hh_max": int(max(ratios)),
                "margen_vs_aidu_pct": round(margen, 1),
                "costo_hh_aidu": COSTO_HH_AIDU,
            })
        
        resultados.sort(key=lambda x: x["clp_hh_mediana"], reverse=True)
        return resultados
    finally:
        conn.close()


def tarifas_por_categoria() -> List[Dict]:
    """Versión simplificada por categoría (sin tipo)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT 
                c.cod_servicio_aidu AS cat,
                l.monto_adjudicado,
                COALESCE(i.hh_estimadas_aidu, h.hh_tipicas) AS hh
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            LEFT JOIN aidu_indicadores_extraidos i ON i.codigo_externo = l.codigo_externo
            LEFT JOIN aidu_homologacion_categoria h ON h.cod_servicio_aidu = c.cod_servicio_aidu
            WHERE l.monto_adjudicado > 0
              AND COALESCE(i.hh_estimadas_aidu, h.hh_tipicas) > 0
        """).fetchall()
        
        agrupado = {}
        for r in rows:
            cat = r["cat"]
            if cat not in agrupado:
                agrupado[cat] = []
            ratio = r["monto_adjudicado"] / r["hh"] if r["hh"] > 0 else 0
            if 0 < ratio < 10_000_000:
                agrupado[cat].append(ratio)
        
        out = []
        for cat, ratios in agrupado.items():
            if not ratios:
                continue
            mediana = statistics.median(ratios) if len(ratios) > 1 else ratios[0]
            margen = ((mediana - COSTO_HH_AIDU) / COSTO_HH_AIDU * 100)
            out.append({
                "categoria": cat,
                "n_licitaciones": len(ratios),
                "clp_hh_mediana": int(mediana),
                "clp_hh_promedio": int(sum(ratios) / len(ratios)),
                "clp_hh_min": int(min(ratios)),
                "clp_hh_max": int(max(ratios)),
                "margen_vs_aidu_pct": round(margen, 1),
                "costo_hh_aidu": COSTO_HH_AIDU,
            })
        out.sort(key=lambda x: x["clp_hh_mediana"], reverse=True)
        return out
    finally:
        conn.close()


def clp_m2_por_categoria() -> List[Dict]:
    """CLP/m² para categorías que aplican (CE-01/02/03)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT 
                c.cod_servicio_aidu AS cat,
                l.monto_adjudicado,
                i.metros_cuadrados
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            INNER JOIN aidu_indicadores_extraidos i ON i.codigo_externo = l.codigo_externo
            INNER JOIN aidu_homologacion_categoria h ON h.cod_servicio_aidu = c.cod_servicio_aidu
            WHERE h.aplica_m2 = 1
              AND i.metros_cuadrados > 0
              AND l.monto_adjudicado > 0
        """).fetchall()
        
        agrupado = {}
        for r in rows:
            cat = r["cat"]
            if cat not in agrupado:
                agrupado[cat] = []
            ratio = r["monto_adjudicado"] / r["metros_cuadrados"]
            if 100 <= ratio <= 1_000_000:
                agrupado[cat].append(ratio)
        
        out = []
        for cat, ratios in agrupado.items():
            if not ratios:
                continue
            out.append({
                "categoria": cat,
                "n_muestras": len(ratios),
                "clp_m2_mediana": int(statistics.median(ratios) if len(ratios) > 1 else ratios[0]),
                "clp_m2_promedio": int(sum(ratios) / len(ratios)),
                "clp_m2_min": int(min(ratios)),
                "clp_m2_max": int(max(ratios)),
            })
        out.sort(key=lambda x: x["clp_m2_mediana"], reverse=True)
        return out
    finally:
        conn.close()


def benchmark_tipo_licitacion() -> List[Dict]:
    """Compara CLP/HH entre tipos LE/LP/LR/LQ/AGIL."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT 
                COALESCE(NULLIF(l.tipo, ''), 'Sin tipo') AS tipo,
                l.monto_adjudicado,
                COALESCE(i.hh_estimadas_aidu, h.hh_tipicas) AS hh
            FROM mp_licitaciones_adj l
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            LEFT JOIN aidu_indicadores_extraidos i ON i.codigo_externo = l.codigo_externo
            LEFT JOIN aidu_homologacion_categoria h ON h.cod_servicio_aidu = c.cod_servicio_aidu
            WHERE l.monto_adjudicado > 0
              AND COALESCE(i.hh_estimadas_aidu, h.hh_tipicas) > 0
        """).fetchall()
        
        agrupado = {}
        for r in rows:
            tipo = r["tipo"]
            if tipo not in agrupado:
                agrupado[tipo] = []
            ratio = r["monto_adjudicado"] / r["hh"] if r["hh"] > 0 else 0
            if 0 < ratio < 10_000_000:
                agrupado[tipo].append(ratio)
        
        out = []
        for tipo, ratios in agrupado.items():
            if not ratios:
                continue
            mediana = statistics.median(ratios) if len(ratios) > 1 else ratios[0]
            margen = ((mediana - COSTO_HH_AIDU) / COSTO_HH_AIDU * 100)
            out.append({
                "tipo": tipo,
                "n": len(ratios),
                "clp_hh_mediana": int(mediana),
                "clp_hh_promedio": int(sum(ratios) / len(ratios)),
                "margen_vs_aidu_pct": round(margen, 1),
            })
        out.sort(key=lambda x: x["clp_hh_mediana"], reverse=True)
        return out
    finally:
        conn.close()


def stats_globales_inteligencia() -> Dict:
    """Resumen para mostrar al inicio de la sección."""
    cats = tarifas_por_categoria()
    tipos = benchmark_tipo_licitacion()
    
    return {
        "n_categorias_con_data": len(cats),
        "n_tipos_con_data": len(tipos),
        "mejor_categoria": cats[0] if cats else None,
        "peor_categoria": cats[-1] if cats else None,
        "mejor_tipo": tipos[0] if tipos else None,
        "costo_hh_aidu": COSTO_HH_AIDU,
    }
