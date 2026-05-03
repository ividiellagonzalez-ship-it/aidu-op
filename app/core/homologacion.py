"""
AIDU Op · Homologación de licitaciones
========================================
Convierte cada licitación en indicadores comparables para inteligencia de precios.

Componentes:
1. SEED: valores típicos conservadores por categoría AIDU (editable desde UI)
2. HEURÍSTICAS: extraen plazo, m², entregables del texto disponible
3. CALCULADORES: derivan CLP/HH, CLP/m², CLP/entregable

La extracción usa nombre + descripción + raw_json de la licitación. Cuando
descargues bases técnicas (PDFs anexos) podrás llamar a las mismas heurísticas
sobre el texto completo del PDF.

Cascada de fallback para HH:
  1. hh_estimadas_aidu en aidu_indicadores_extraidos (si fue calculado)
  2. hh_tipicas de la tabla maestra para esa categoría
  3. None
"""
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import re
import json
import logging
from app.db.migrator import get_connection

logger = logging.getLogger(__name__)


# ============================================================
# SEED CONSERVADOR de la tabla maestra
# ============================================================
# Valores iniciales basados en juicio técnico AIDU.
# El usuario los edita desde la UI cuando los desee ajustar.

SEED_HOMOLOGACION = [
    # CE - Cálculo Estructural
    {
        "cod": "CE-01", "nombre": "Cálculo estructural simple",
        "linea": "Estructural",
        "hh": 80, "plazo": 30,
        "entregables": "Memoria de cálculo, Planos estructurales, Especificaciones técnicas",
        "aplica_m2": 1, "m2_ref": 200,
        "notas": "Edificaciones simples hasta 2 pisos, casas habitación, ampliaciones menores."
    },
    {
        "cod": "CE-02", "nombre": "Cálculo estructural medio",
        "linea": "Estructural",
        "hh": 200, "plazo": 60,
        "entregables": "Memoria, Planos, Especificaciones, Revisión sísmica, Detalles",
        "aplica_m2": 1, "m2_ref": 800,
        "notas": "Edificios 3-6 pisos, equipamiento institucional, naves industriales medianas."
    },
    {
        "cod": "CE-03", "nombre": "Cálculo estructural complejo",
        "linea": "Estructural",
        "hh": 480, "plazo": 90,
        "entregables": "Memoria avanzada, Planos detallados, Modelo BIM, Especificaciones, Revisión sísmica integral",
        "aplica_m2": 1, "m2_ref": 2000,
        "notas": "Edificios altura, hospitales, infraestructura crítica, estructuras especiales."
    },
    {
        "cod": "CE-04", "nombre": "Peritaje estructural",
        "linea": "Estructural",
        "hh": 40, "plazo": 15,
        "entregables": "Informe de peritaje, Registro fotográfico, Recomendaciones técnicas",
        "aplica_m2": 0, "m2_ref": 0,
        "notas": "Diagnósticos, evaluación post-sismo, evaluación de daños."
    },
    {
        "cod": "CE-05", "nombre": "ITO estructural",
        "linea": "Estructural",
        "hh": 320, "plazo": 120,
        "entregables": "Informes mensuales ITO, Registro fotográfico, Acta de revisión, Informe final",
        "aplica_m2": 0, "m2_ref": 0,
        "notas": "Inspección Técnica de Obra. HH dependen del plazo de obra."
    },
    {
        "cod": "CE-06", "nombre": "Revisión estructural independiente",
        "linea": "Estructural",
        "hh": 60, "plazo": 20,
        "entregables": "Informe de revisión, Observaciones técnicas, Verificación normativa",
        "aplica_m2": 0, "m2_ref": 0,
        "notas": "Revisor estructural según OGUC. Cumplimiento normativo NCh."
    },
    # GP - Gestión de Proyectos
    {
        "cod": "GP-01", "nombre": "PMO básico",
        "linea": "Gestión",
        "hh": 120, "plazo": 30,
        "entregables": "Carta Gantt, Dashboard de seguimiento, Informes semanales",
        "aplica_m2": 0, "m2_ref": 0,
        "notas": "Setup PMO inicial, plan de proyecto, herramientas de control."
    },
    {
        "cod": "GP-02", "nombre": "Gerenciamiento de proyectos",
        "linea": "Gestión",
        "hh": 480, "plazo": 180,
        "entregables": "Plan integral, Informes mensuales, Control financiero, Reporte de hitos",
        "aplica_m2": 0, "m2_ref": 0,
        "notas": "Gerencia integral de proyecto. HH dependen del plazo del contrato."
    },
    {
        "cod": "GP-03", "nombre": "Optimización de procesos",
        "linea": "Gestión",
        "hh": 160, "plazo": 45,
        "entregables": "Diagnóstico, Mapa de procesos as-is/to-be, Plan de implementación",
        "aplica_m2": 0, "m2_ref": 0,
        "notas": "Levantamiento BPM, optimización operacional."
    },
    {
        "cod": "GP-04", "nombre": "BPM e implementación",
        "linea": "Gestión",
        "hh": 320, "plazo": 90,
        "entregables": "Levantamiento BPMN, Procedimientos, Capacitación, KPIs",
        "aplica_m2": 0, "m2_ref": 0,
        "notas": "Business Process Management completo con implementación."
    },
    {
        "cod": "GP-05", "nombre": "Asesoría en agilidad",
        "linea": "Gestión",
        "hh": 80, "plazo": 30,
        "entregables": "Diagnóstico de madurez, Plan de transformación ágil, Talleres",
        "aplica_m2": 0, "m2_ref": 0,
        "notas": "Scrum/Kanban, transformación ágil organizacional."
    },
    {
        "cod": "GP-06", "nombre": "Control de gestión",
        "linea": "Gestión",
        "hh": 200, "plazo": 60,
        "entregables": "KPIs definidos, Tablero de control, Procedimientos, Capacitación",
        "aplica_m2": 0, "m2_ref": 0,
        "notas": "Setup sistema control gestión, indicadores estratégicos y operacionales."
    },
]


def seed_homologacion(forzar: bool = False) -> int:
    """
    Pobla la tabla maestra con valores típicos.
    Si forzar=False, solo inserta los que no existen.
    Si forzar=True, sobreescribe TODOS los valores (cuidado: destruye edits del usuario).
    """
    conn = get_connection()
    insertados = 0
    try:
        for item in SEED_HOMOLOGACION:
            existe = conn.execute(
                "SELECT cod_servicio_aidu FROM aidu_homologacion_categoria WHERE cod_servicio_aidu = ?",
                (item["cod"],)
            ).fetchone()
            
            if existe and not forzar:
                continue
            
            if existe and forzar:
                conn.execute("""
                    UPDATE aidu_homologacion_categoria SET
                        nombre_servicio = ?, linea = ?, hh_tipicas = ?, plazo_dias_tipico = ?,
                        entregables_tipicos = ?, aplica_m2 = ?, m2_referencia = ?, notas = ?,
                        fecha_actualizacion = datetime('now', 'localtime')
                    WHERE cod_servicio_aidu = ?
                """, (
                    item["nombre"], item["linea"], item["hh"], item["plazo"],
                    item["entregables"], item["aplica_m2"], item["m2_ref"], item["notas"],
                    item["cod"]
                ))
            else:
                conn.execute("""
                    INSERT INTO aidu_homologacion_categoria
                    (cod_servicio_aidu, nombre_servicio, linea, hh_tipicas, plazo_dias_tipico,
                     entregables_tipicos, aplica_m2, m2_referencia, notas)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["cod"], item["nombre"], item["linea"], item["hh"], item["plazo"],
                    item["entregables"], item["aplica_m2"], item["m2_ref"], item["notas"]
                ))
                insertados += 1
        conn.commit()
    finally:
        conn.close()
    return insertados


def listar_homologacion() -> List[Dict]:
    """Retorna toda la tabla maestra ordenada por categoría."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT cod_servicio_aidu, nombre_servicio, linea, hh_tipicas,
                   plazo_dias_tipico, entregables_tipicos, aplica_m2,
                   m2_referencia, notas, fecha_actualizacion
            FROM aidu_homologacion_categoria
            ORDER BY linea, cod_servicio_aidu
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def actualizar_homologacion(cod_servicio: str, **campos) -> bool:
    """
    Actualiza un registro de la tabla maestra.
    Acepta: hh_tipicas, plazo_dias_tipico, entregables_tipicos,
            aplica_m2, m2_referencia, notas.
    """
    permitidos = ["hh_tipicas", "plazo_dias_tipico", "entregables_tipicos",
                  "aplica_m2", "m2_referencia", "notas", "nombre_servicio"]
    sets = []
    valores = []
    for k, v in campos.items():
        if k in permitidos:
            sets.append(f"{k} = ?")
            valores.append(v)
    if not sets:
        return False
    sets.append("fecha_actualizacion = datetime('now', 'localtime')")
    
    conn = get_connection()
    try:
        valores.append(cod_servicio)
        conn.execute(
            f"UPDATE aidu_homologacion_categoria SET {', '.join(sets)} WHERE cod_servicio_aidu = ?",
            valores
        )
        conn.commit()
        return True
    finally:
        conn.close()


def obtener_hh_para_categoria(cod_servicio: str) -> Optional[int]:
    """Lookup rápido de HH típicas."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT hh_tipicas FROM aidu_homologacion_categoria WHERE cod_servicio_aidu = ?",
            (cod_servicio,)
        ).fetchone()
        return int(row["hh_tipicas"]) if row else None
    finally:
        conn.close()


# ============================================================
# HEURÍSTICAS DE EXTRACCIÓN
# ============================================================

# Patrones para PLAZO
PATRONES_PLAZO = [
    (r"plazo\s+(?:de\s+)?(?:ejecuci[oó]n\s+(?:de\s+)?)?(\d{1,4})\s*d[ií]as?", "dias"),
    (r"(?:dentro\s+de|en\s+un\s+plazo\s+de)\s+(\d{1,4})\s*d[ií]as?", "dias"),
    (r"plazo\s+(?:de\s+)?(\d{1,3})\s*(?:meses|mes)", "meses"),
    (r"(?:dentro\s+de|en\s+un?\s+plazo\s+de)\s+(\d{1,3})\s*(?:meses|mes)", "meses"),
    (r"(?:plazo|duraci[oó]n)\s+(?:de\s+)?(\d{1,3})\s*(?:semanas|semana)", "semanas"),
    (r"duraci[oó]n\s+(?:del\s+)?(?:contrato|servicio|trabajo)?\s*(?:de|:)?\s*(\d{1,4})\s*d[ií]as?", "dias"),
    (r"(?:plazo|duraci[oó]n)\s+(?:de\s+)?(\d{1,3})\s*(?:a[nñ]os?)", "anos"),
    (r"\ben\s+(\d{1,3})\s*(?:meses|mes)\b", "meses"),
]

# Patrones para M²
PATRONES_M2 = [
    (r"(\d{1,6}(?:[.,]\d{1,3})?)\s*(?:m2|m²|metros?\s*cuadrados?)", 1),
    (r"superficie\s+(?:total|construida|aproximada)?\s*(?:de|:)?\s*(\d{1,6}(?:[.,]\d{1,3})?)", 1),
    (r"\b(\d{1,6})\s*mts?2", 1),
]

# Palabras clave para ENTREGABLES
KEYWORDS_ENTREGABLES = [
    "memoria", "memorias",
    "informe", "informes",
    "plano", "planos",
    "reporte", "reportes",
    "especificaci[oó]n", "especificaciones",
    "an[aá]lisis",
    "diagn[oó]stico",
    "manual", "manuales",
    "procedimiento", "procedimientos",
    "estudio", "estudios",
    "registro", "registros",
    "carta gantt",
    "dashboard",
    "presentaci[oó]n", "presentaciones",
    "minuta", "minutas",
    "acta", "actas",
]


def _extraer_plazo(texto: str) -> Tuple[Optional[int], str]:
    """Extrae plazo en días desde texto. Retorna (días, fuente)."""
    if not texto:
        return None, ""
    texto_lower = texto.lower()
    
    for patron, unidad in PATRONES_PLAZO:
        m = re.search(patron, texto_lower, re.IGNORECASE)
        if m:
            try:
                valor = int(m.group(1))
                if unidad == "dias":
                    return valor, f"regex:dias"
                elif unidad == "meses":
                    return valor * 30, f"regex:meses({valor})"
                elif unidad == "semanas":
                    return valor * 7, f"regex:semanas({valor})"
                elif unidad == "anos":
                    return valor * 365, f"regex:anos({valor})"
            except (ValueError, IndexError):
                continue
    return None, ""


def _extraer_m2(texto: str) -> Tuple[Optional[int], str]:
    """Extrae metros cuadrados desde texto."""
    if not texto:
        return None, ""
    texto_lower = texto.lower()
    
    for patron, _ in PATRONES_M2:
        m = re.search(patron, texto_lower, re.IGNORECASE)
        if m:
            try:
                valor_str = m.group(1).replace(",", ".")
                valor = int(float(valor_str))
                # Filtro razonabilidad: 1 m² a 10 millones
                if 1 <= valor <= 10_000_000:
                    return valor, "regex:m2"
            except (ValueError, IndexError):
                continue
    return None, ""


def _extraer_entregables(texto: str) -> Tuple[List[str], str]:
    """Cuenta y lista entregables mencionados."""
    if not texto:
        return [], ""
    texto_lower = texto.lower()
    encontrados = set()
    
    for kw in KEYWORDS_ENTREGABLES:
        if re.search(rf"\b{kw}\b", texto_lower, re.IGNORECASE):
            # Normalizar a forma canónica
            canonico = kw.replace("[oó]", "o").replace("[aá]", "a").rstrip("es").rstrip("s")
            encontrados.add(canonico.capitalize())
    
    return sorted(encontrados), "regex:keywords" if encontrados else ""


def extraer_indicadores_de_licitacion(codigo: str, texto_extra: str = "") -> Dict:
    """
    Aplica heurísticas sobre el texto disponible (nombre + descripción + raw_json).
    texto_extra: texto adicional (ej. PDF de bases técnicas si fue descargado).
    
    Persiste en aidu_indicadores_extraidos.
    """
    conn = get_connection()
    try:
        # Buscar la licitación
        row = conn.execute("""
            SELECT codigo_externo, nombre, descripcion, raw_json
            FROM mp_licitaciones_adj WHERE codigo_externo = ?
        """, (codigo,)).fetchone()
        
        if not row:
            row = conn.execute("""
                SELECT codigo_externo, nombre, descripcion, raw_json
                FROM mp_licitaciones_vigentes WHERE codigo_externo = ?
            """, (codigo,)).fetchone()
        
        if not row:
            return {"error": f"Código {codigo} no encontrado"}
        
        # Construir texto completo a analizar
        partes = [row["nombre"] or "", row["descripcion"] or ""]
        if row["raw_json"]:
            try:
                raw = json.loads(row["raw_json"])
                # Items pueden tener descripción
                items = raw.get("Items", {})
                if isinstance(items, dict):
                    listado = items.get("Listado", []) or []
                    for it in listado if isinstance(listado, list) else [listado]:
                        if isinstance(it, dict):
                            partes.append(it.get("Descripcion", "") or "")
                            partes.append(it.get("NombreProducto", "") or "")
            except Exception:
                pass
        
        if texto_extra:
            partes.append(texto_extra)
        
        texto_completo = " ".join([p for p in partes if p])
        
        # Aplicar heurísticas
        plazo, plazo_fuente = _extraer_plazo(texto_completo)
        m2, m2_fuente = _extraer_m2(texto_completo)
        entregables, entreg_fuente = _extraer_entregables(texto_completo)
        
        # Calcular HH estimadas: si tenemos categoría AIDU, mirar tabla maestra
        hh_estimadas = None
        hh_fuente = ""
        try:
            cat_row = conn.execute(
                "SELECT cod_servicio_aidu FROM mp_categorizacion_aidu WHERE codigo_externo = ?",
                (codigo,)
            ).fetchone()
            if cat_row and cat_row["cod_servicio_aidu"]:
                hh_row = conn.execute(
                    "SELECT hh_tipicas FROM aidu_homologacion_categoria WHERE cod_servicio_aidu = ?",
                    (cat_row["cod_servicio_aidu"],)
                ).fetchone()
                if hh_row:
                    hh_estimadas = int(hh_row["hh_tipicas"])
                    hh_fuente = f"tabla_maestra:{cat_row['cod_servicio_aidu']}"
        except Exception:
            pass
        
        # Si no tenemos HH desde tabla maestra y tenemos plazo, derivar conservador
        if hh_estimadas is None and plazo is not None and plazo > 0:
            # Asumir 2 HH/día calendario como heurística MUY conservadora
            hh_estimadas = max(40, plazo * 2)
            hh_fuente = "derivado:plazo*2hh_dia"
        
        # Persistir
        entregables_str = ", ".join(entregables) if entregables else None
        conn.execute("""
            INSERT OR REPLACE INTO aidu_indicadores_extraidos
            (codigo_externo, plazo_dias, plazo_fuente,
             metros_cuadrados, m2_fuente,
             n_entregables, entregables_lista, entregables_fuente,
             hh_estimadas_aidu, hh_fuente, fecha_extraccion)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'))
        """, (
            codigo, plazo, plazo_fuente,
            m2, m2_fuente,
            len(entregables), entregables_str, entreg_fuente,
            hh_estimadas, hh_fuente
        ))
        conn.commit()
        
        return {
            "codigo": codigo,
            "plazo_dias": plazo,
            "metros_cuadrados": m2,
            "n_entregables": len(entregables),
            "entregables": entregables,
            "hh_estimadas": hh_estimadas,
        }
    finally:
        conn.close()


def extraer_lote(limit: int = 1000, solo_pendientes: bool = True) -> Dict:
    """
    Aplica extracción a un lote de licitaciones.
    solo_pendientes=True: solo procesa las que NO están aún en aidu_indicadores_extraidos.
    """
    conn = get_connection()
    try:
        if solo_pendientes:
            sql = """
                SELECT l.codigo_externo FROM mp_licitaciones_adj l
                LEFT JOIN aidu_indicadores_extraidos i ON i.codigo_externo = l.codigo_externo
                WHERE i.codigo_externo IS NULL
                LIMIT ?
            """
        else:
            sql = "SELECT codigo_externo FROM mp_licitaciones_adj LIMIT ?"
        
        codigos = [r["codigo_externo"] for r in conn.execute(sql, (limit,)).fetchall()]
    finally:
        conn.close()
    
    stats = {"total": len(codigos), "con_plazo": 0, "con_m2": 0, "con_entregables": 0, "con_hh": 0}
    for codigo in codigos:
        try:
            res = extraer_indicadores_de_licitacion(codigo)
            if "error" not in res:
                if res.get("plazo_dias"): stats["con_plazo"] += 1
                if res.get("metros_cuadrados"): stats["con_m2"] += 1
                if res.get("n_entregables", 0) > 0: stats["con_entregables"] += 1
                if res.get("hh_estimadas"): stats["con_hh"] += 1
        except Exception as e:
            logger.warning(f"Error extrayendo {codigo}: {e}")
    
    return stats


def stats_extraccion() -> Dict:
    """Stats globales de extracción."""
    conn = get_connection()
    try:
        n_total_adj = conn.execute("SELECT COUNT(*) FROM mp_licitaciones_adj").fetchone()[0] or 0
        n_extraidas = conn.execute("SELECT COUNT(*) FROM aidu_indicadores_extraidos").fetchone()[0] or 0
        n_con_plazo = conn.execute("SELECT COUNT(*) FROM aidu_indicadores_extraidos WHERE plazo_dias IS NOT NULL").fetchone()[0] or 0
        n_con_m2 = conn.execute("SELECT COUNT(*) FROM aidu_indicadores_extraidos WHERE metros_cuadrados IS NOT NULL").fetchone()[0] or 0
        n_con_hh = conn.execute("SELECT COUNT(*) FROM aidu_indicadores_extraidos WHERE hh_estimadas_aidu IS NOT NULL").fetchone()[0] or 0
        
        return {
            "total_adj": n_total_adj,
            "extraidas": n_extraidas,
            "con_plazo": n_con_plazo,
            "con_m2": n_con_m2,
            "con_hh": n_con_hh,
            "pct_cobertura": round(n_extraidas / n_total_adj * 100, 1) if n_total_adj else 0,
            "pct_plazo": round(n_con_plazo / n_extraidas * 100, 1) if n_extraidas else 0,
            "pct_m2": round(n_con_m2 / n_extraidas * 100, 1) if n_extraidas else 0,
            "pct_hh": round(n_con_hh / n_extraidas * 100, 1) if n_extraidas else 0,
        }
    finally:
        conn.close()
