"""
AIDU Op · Match Score Engine
=============================
Calcula score 0-100 de qué tan bien una licitación calza con el perfil AIDU.

Pesos:
- Categoría AIDU (40%): si está categorizada con confianza > 0.7
- Región (25%): O'Higgins primero, luego RM, otras regiones bajan
- Monto sweet spot (25%): $3M-$15M = 100, fuera del rango decae
- Mandante recurrente (10%): si AIDU ya trabajó con este organismo

El score se calcula en runtime (no se persiste) para que cambios en 
configuración del usuario impacten inmediatamente.
"""
from typing import Dict, List, Optional, Tuple
from app.db.migrator import get_connection


# Configuración por defecto AIDU
DEFAULT_CONFIG = {
    "regiones_prioritarias": {
        "VI Región del Libertador Bernardo O'Higgins": 100,
        "Región del Libertador Bernardo O'Higgins": 100,
        "O'Higgins": 100,
        "Región Metropolitana de Santiago": 70,
        "Metropolitana": 70,
        "RM": 70,
        "VII Región del Maule": 60,
        "Maule": 60,
        "V Región de Valparaíso": 50,
        "Valparaíso": 50,
    },
    "monto_min_sweet_spot": 3_000_000,
    "monto_max_sweet_spot": 15_000_000,
    "monto_min_aceptable": 1_500_000,
    "monto_max_aceptable": 30_000_000,
    "categorias_activas": [
        "CE-01", "CE-02", "CE-03", "CE-04", "CE-05", "CE-06",
        "GP-01", "GP-02", "GP-04", "GP-05",
        "IA-01", "IA-02", "IA-03",
        "CAP-01",
    ],
}


def _score_categoria(cod_servicio: Optional[str], confianza: Optional[float], 
                      categorias_activas: List[str]) -> Tuple[float, str]:
    """0-100 según calidad del match de categoría."""
    if not cod_servicio:
        return 0.0, "Sin categoría AIDU"
    
    if cod_servicio not in categorias_activas:
        return 20.0, f"{cod_servicio} (no priorizada)"
    
    if confianza is None:
        return 60.0, f"{cod_servicio} (sin confianza)"
    
    # Escala lineal: confianza 0.5 = 50pts, 1.0 = 100pts
    score = max(0, min(100, confianza * 100))
    return score, f"{cod_servicio} ({confianza:.0%})"


def _score_region(region: Optional[str], regiones_priorizadas: Dict[str, int]) -> Tuple[float, str]:
    """0-100 según prioridad de región."""
    if not region:
        return 30.0, "Sin región"
    
    region_norm = region.strip()
    for key, val in regiones_priorizadas.items():
        if key.lower() in region_norm.lower() or region_norm.lower() in key.lower():
            return float(val), region_norm
    
    return 40.0, f"{region_norm} (otra)"


def _score_monto(monto: Optional[int], min_sweet: int, max_sweet: int,
                 min_acept: int, max_acept: int) -> Tuple[float, str]:
    """100pts en sweet spot, decae fuera, 0 si fuera de rango aceptable."""
    if not monto or monto <= 0:
        return 30.0, "Sin monto"
    
    if min_sweet <= monto <= max_sweet:
        return 100.0, f"${monto/1_000_000:.1f}M (sweet spot)"
    
    if monto < min_acept or monto > max_acept:
        return 0.0, f"${monto/1_000_000:.1f}M (fuera de rango)"
    
    # Decaimiento lineal entre rango aceptable y sweet spot
    if monto < min_sweet:
        # Entre min_acept y min_sweet: 30 a 100
        ratio = (monto - min_acept) / (min_sweet - min_acept)
        score = 30 + ratio * 70
    else:
        # Entre max_sweet y max_acept: 100 a 30
        ratio = (max_acept - monto) / (max_acept - max_sweet)
        score = 30 + ratio * 70
    
    return score, f"${monto/1_000_000:.1f}M"


def _score_mandante(organismo: Optional[str]) -> Tuple[float, str]:
    """100 si AIDU ya trabajó con este organismo, 50 si neutro."""
    if not organismo:
        return 50.0, "Sin organismo"
    
    conn = get_connection()
    try:
        # ¿Hay algún proyecto AIDU previo con este organismo?
        n = conn.execute(
            "SELECT COUNT(*) FROM aidu_proyectos WHERE organismo = ? AND estado IN ('ADJUDICADA', 'OFERTADA')",
            (organismo,)
        ).fetchone()[0]
        
        if n > 0:
            return 100.0, f"Organismo recurrente ({n} proyectos)"
        
        # Perfil del organismo
        perfil = conn.execute(
            "SELECT n_licitaciones_aidu FROM mp_organismos_perfil WHERE organismo = ?",
            (organismo,)
        ).fetchone()
        
        if perfil and perfil[0] and perfil[0] >= 3:
            return 80.0, f"Activo en categorías AIDU ({perfil[0]} licit.)"
        
        return 50.0, "Mandante neutro"
    finally:
        conn.close()


def _score_recencia(fecha_publicacion: Optional[str]) -> Tuple[float, str]:
    """0-100 según qué tan reciente es la licitación.
    Las recientes (< 30 días) son más probables de estar vigentes para postular.
    """
    if not fecha_publicacion:
        return 50.0, "Sin fecha"
    
    try:
        from datetime import datetime
        # Soportar varios formatos
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                fecha = datetime.strptime(fecha_publicacion[:19], fmt[:len(fecha_publicacion[:19])])
                break
            except ValueError:
                continue
        else:
            # Solo año-mes-día
            fecha = datetime.fromisoformat(fecha_publicacion[:10])
        
        dias = (datetime.now() - fecha).days
        
        if dias < 0:
            return 100.0, "Muy reciente"
        if dias <= 30:
            return 100.0, f"Hace {dias}d"
        if dias <= 90:
            return 80.0, f"Hace {dias}d"
        if dias <= 180:
            return 60.0, f"Hace {dias}d"
        if dias <= 365:
            return 40.0, f"Hace {dias // 30}m"
        return 20.0, f"Hace {dias // 365}a"
    except Exception:
        return 50.0, "Fecha err."


def calcular_match_score(licitacion: Dict, config: Optional[Dict] = None) -> Dict:
    """
    Calcula score 0-100 + desglose para una licitación.
    
    Args:
        licitacion: dict con keys codigo_externo, region, monto_referencial, 
                    organismo, cod_servicio_aidu, confianza
        config: dict opcional para sobreescribir DEFAULT_CONFIG
    
    Returns:
        {
            "score": int 0-100,
            "desglose": {
                "categoria": (score, label),
                "region": (score, label),
                "monto": (score, label),
                "mandante": (score, label),
            },
            "explicacion": str corta para tooltip
        }
    """
    cfg = {**DEFAULT_CONFIG, **(config or {})}
    
    s_cat, l_cat = _score_categoria(
        licitacion.get("cod_servicio_aidu"),
        licitacion.get("confianza"),
        cfg["categorias_activas"]
    )
    s_reg, l_reg = _score_region(licitacion.get("region"), cfg["regiones_prioritarias"])
    s_mon, l_mon = _score_monto(
        licitacion.get("monto_referencial"),
        cfg["monto_min_sweet_spot"], cfg["monto_max_sweet_spot"],
        cfg["monto_min_aceptable"], cfg["monto_max_aceptable"]
    )
    s_man, l_man = _score_mandante(licitacion.get("organismo"))
    s_rec, l_rec = _score_recencia(licitacion.get("fecha_publicacion"))
    
    # Pesos: 35 / 20 / 20 / 10 / 15 (recencia)
    # La recencia es CLAVE: una licitación de 2024 ya cerró, no sirve postular
    score_total = (
        s_cat * 0.35 +
        s_reg * 0.20 +
        s_mon * 0.20 +
        s_man * 0.10 +
        s_rec * 0.15
    )
    score_total = max(0, min(100, round(score_total)))
    
    return {
        "score": int(score_total),
        "desglose": {
            "categoria": (round(s_cat), l_cat),
            "region": (round(s_reg), l_reg),
            "monto": (round(s_mon), l_mon),
            "mandante": (round(s_man), l_man),
            "recencia": (round(s_rec), l_rec),
        },
        "explicacion": f"{l_cat} · {l_reg} · {l_mon} · {l_rec}"
    }


def listar_oportunidades(
    filtro_categoria: Optional[str] = None,
    filtro_region: Optional[str] = None,
    monto_min: Optional[int] = None,
    monto_max: Optional[int] = None,
    score_min: int = 0,
    solo_no_en_cartera: bool = True,
    orden: str = "score_desc",
    limit: int = 100,
) -> List[Dict]:
    """
    Lista licitaciones del histórico MP categorizadas como AIDU,
    con match score calculado, filtradas según criterios.
    
    Args:
        filtro_categoria: ej "CE-06" o None para todas
        filtro_region: ej "O'Higgins" o None
        monto_min, monto_max: rango en CLP
        score_min: descarta licitaciones con score < este
        solo_no_en_cartera: True = excluye las que ya están como proyecto AIDU
        orden: "score_desc" | "monto_desc" | "fecha_desc"
        limit: máximo a retornar
    
    Returns:
        Lista de dicts con todos los campos + 'match' (resultado de calcular_match_score)
    """
    conn = get_connection()
    try:
        # Query base: licitaciones con categorización AIDU (o sin ella, según filtro)
        sql = """
            SELECT 
                l.codigo_externo, l.nombre, l.descripcion,
                l.organismo, l.region, l.comuna,
                l.fecha_publicacion, l.fecha_cierre, l.fecha_adjudicacion,
                l.monto_referencial, l.monto_adjudicado, l.estado,
                l.proveedor_adjudicado, l.n_oferentes,
                c.cod_servicio_aidu, c.confianza
            FROM mp_licitaciones_adj l
            LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            WHERE 1=1
        """
        params = []
        
        if filtro_categoria and filtro_categoria != "Todas":
            sql += " AND c.cod_servicio_aidu = ?"
            params.append(filtro_categoria)
        
        if filtro_region and filtro_region != "Todas":
            sql += " AND l.region LIKE ?"
            params.append(f"%{filtro_region}%")
        
        if monto_min is not None:
            sql += " AND l.monto_referencial >= ?"
            params.append(monto_min)
        
        if monto_max is not None:
            sql += " AND l.monto_referencial <= ?"
            params.append(monto_max)
        
        if solo_no_en_cartera:
            sql += " AND l.codigo_externo NOT IN (SELECT codigo_externo FROM aidu_proyectos WHERE codigo_externo IS NOT NULL)"
        
        # Limitar a los que tienen categorización AIDU (con o sin filtro específico)
        if not filtro_categoria or filtro_categoria == "Todas":
            sql += " AND c.cod_servicio_aidu IS NOT NULL"
        
        sql += " LIMIT ?"
        params.append(limit * 5)  # Pedir 5x para luego deduplicar y filtrar por score
        
        rows = conn.execute(sql, params).fetchall()
        
        # Deduplicar por codigo_externo (una licitación puede tener múltiples categorizaciones)
        # Nos quedamos con la de mayor confianza
        vistos = {}
        for r in rows:
            lic = dict(r)
            codigo = lic["codigo_externo"]
            confianza = lic.get("confianza") or 0
            
            if codigo not in vistos or confianza > (vistos[codigo].get("confianza") or 0):
                vistos[codigo] = lic
        
        # Calcular match score para cada una (solo únicas)
        oportunidades = []
        for lic in vistos.values():
            match = calcular_match_score(lic)
            
            if match["score"] < score_min:
                continue
            
            lic["match"] = match
            oportunidades.append(lic)
        
        # Ordenar
        if orden == "score_desc":
            oportunidades.sort(key=lambda x: x["match"]["score"], reverse=True)
        elif orden == "monto_desc":
            oportunidades.sort(key=lambda x: x.get("monto_referencial") or 0, reverse=True)
        elif orden == "fecha_desc":
            oportunidades.sort(key=lambda x: x.get("fecha_publicacion") or "", reverse=True)
        
        return oportunidades[:limit]
    finally:
        conn.close()


def categorias_disponibles() -> List[Tuple[str, int]]:
    """Lista categorías AIDU con conteo de licitaciones disponibles (no en cartera)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT 
                c.cod_servicio_aidu,
                COUNT(*) as n
            FROM mp_categorizacion_aidu c
            JOIN mp_licitaciones_adj l ON l.codigo_externo = c.codigo_externo
            WHERE c.cod_servicio_aidu IS NOT NULL
              AND l.codigo_externo NOT IN (SELECT codigo_externo FROM aidu_proyectos WHERE codigo_externo IS NOT NULL)
            GROUP BY c.cod_servicio_aidu
            ORDER BY n DESC
        """).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


def regiones_disponibles() -> List[Tuple[str, int]]:
    """Lista regiones con conteo de licitaciones AIDU."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT 
                l.region,
                COUNT(*) as n
            FROM mp_licitaciones_adj l
            JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            WHERE l.region IS NOT NULL AND l.region != ''
              AND l.codigo_externo NOT IN (SELECT codigo_externo FROM aidu_proyectos WHERE codigo_externo IS NOT NULL)
            GROUP BY l.region
            ORDER BY n DESC
            LIMIT 20
        """).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        conn.close()


def convertir_a_proyecto(codigo_externo: str) -> int:
    """
    Convierte una licitación del histórico MP en un proyecto AIDU 
    (estado PROSPECTO). Devuelve proyecto_id creado.
    """
    conn = get_connection()
    try:
        lic = conn.execute("""
            SELECT 
                l.codigo_externo, l.nombre, l.descripcion,
                l.organismo, l.region, l.monto_referencial,
                l.fecha_publicacion, l.fecha_cierre,
                c.cod_servicio_aidu
            FROM mp_licitaciones_adj l
            LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
            WHERE l.codigo_externo = ?
        """, (codigo_externo,)).fetchone()
        
        if not lic:
            raise ValueError(f"Licitación {codigo_externo} no encontrada")
        
        # Verificar si ya existe
        existe = conn.execute(
            "SELECT id FROM aidu_proyectos WHERE codigo_externo = ?",
            (codigo_externo,)
        ).fetchone()
        if existe:
            return existe[0]
        
        cursor = conn.execute("""
            INSERT INTO aidu_proyectos (
                codigo_externo, nombre, descripcion, organismo, region,
                monto_referencial, fecha_publicacion, fecha_cierre,
                cod_servicio_aidu, estado, fecha_creacion, fecha_modificacion
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROSPECTO', datetime('now'), datetime('now'))
        """, (
            lic["codigo_externo"], lic["nombre"], lic["descripcion"],
            lic["organismo"], lic["region"], lic["monto_referencial"],
            lic["fecha_publicacion"], lic["fecha_cierre"],
            lic["cod_servicio_aidu"]
        ))
        conn.commit()
        proyecto_id = cursor.lastrowid
        
        # Registrar evento creación en bitácora
        try:
            conn.execute("""
                INSERT INTO aidu_comunicaciones (proyecto_id, tipo, texto, fecha)
                VALUES (?, 'sistema', ?, datetime('now'))
            """, (proyecto_id, f"Proyecto creado desde oportunidad MP ({codigo_externo})"))
            conn.commit()
        except Exception:
            pass
        
        return proyecto_id
    finally:
        conn.close()
