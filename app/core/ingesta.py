"""
AIDU Op · Motor de ingesta
===========================
Toma datos crudos del API Mercado Público, los normaliza,
los categoriza con scoring AIDU, y los persiste en SQLite.

Flujo:
1. Recibe JSON del API (1 licitación o lista)
2. Extrae campos relevantes
3. Calcula score de match con cada categoría AIDU
4. UPSERT en mp_licitaciones_adj
5. Inserta items y categorización
"""
import logging
import re
from datetime import date
from typing import Dict, List, Tuple, Optional
import json

from app.db.migrator import get_connection

logger = logging.getLogger(__name__)


def _safe_int(v) -> Optional[int]:
    """Convierte a int, None si no es posible"""
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _safe_str(v) -> Optional[str]:
    """Convierte a str, None si vacío"""
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def _extraer_pondera_precio(eval_str: Optional[str]) -> Optional[int]:
    """Extrae el % de ponderación del precio del campo evaluación"""
    if not eval_str:
        return None
    match = re.search(r"Precio\s+(\d+)\s*%", eval_str, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def _normalizar_licitacion(raw: Dict) -> Dict:
    """
    Normaliza la respuesta del API a nuestro esquema interno.
    Los nombres de campos varían según el endpoint, manejamos ambos casos.
    """
    # Listado vs detalle tienen diferentes claves
    return {
        "codigo_externo": _safe_str(raw.get("CodigoExterno") or raw.get("Codigo")),
        "nombre": _safe_str(raw.get("Nombre")),
        "descripcion": _safe_str(raw.get("Descripcion")),
        "organismo": _safe_str(
            raw.get("Comprador", {}).get("NombreOrganismo")
            if isinstance(raw.get("Comprador"), dict)
            else raw.get("NombreOrganismo")
        ),
        "organismo_codigo": _safe_str(
            raw.get("Comprador", {}).get("CodigoOrganismo")
            if isinstance(raw.get("Comprador"), dict)
            else raw.get("CodigoOrganismo")
        ),
        "region": _safe_str(
            raw.get("Comprador", {}).get("RegionUnidad")
            if isinstance(raw.get("Comprador"), dict)
            else raw.get("Region")
        ),
        "comuna": _safe_str(
            raw.get("Comprador", {}).get("ComunaUnidad")
            if isinstance(raw.get("Comprador"), dict)
            else raw.get("Comuna")
        ),
        "tipo": _safe_str(raw.get("Tipo")),
        "fecha_publicacion": _safe_str(
            raw.get("Fechas", {}).get("FechaPublicacion")
            if isinstance(raw.get("Fechas"), dict)
            else raw.get("FechaPublicacion")
        ),
        "fecha_cierre": _safe_str(
            raw.get("Fechas", {}).get("FechaCierre")
            if isinstance(raw.get("Fechas"), dict)
            else raw.get("FechaCierre")
        ),
        "fecha_adjudicacion": _safe_str(
            raw.get("Fechas", {}).get("FechaAdjudicacion")
            if isinstance(raw.get("Fechas"), dict)
            else raw.get("FechaAdjudicacion")
        ),
        "monto_referencial": _safe_int(raw.get("MontoEstimado")),
        "monto_adjudicado": _safe_int(
            raw.get("Adjudicacion", {}).get("MontoAdjudicado")
            if isinstance(raw.get("Adjudicacion"), dict)
            else None
        ),
        "estado": _safe_str(raw.get("Estado") or raw.get("CodigoEstado")),
        "pondera_precio_pct": _extraer_pondera_precio(
            json.dumps(raw.get("Items", "")) + str(raw.get("Descripcion", ""))
        ),
        "raw_json": json.dumps(raw, ensure_ascii=False),
    }


def _calcular_match_aidu(licitacion: Dict, conn) -> List[Tuple[str, float]]:
    """
    Calcula score de match con cada categoría AIDU.
    Retorna lista de (cod_servicio, confianza) ordenada por confianza desc.
    Usa keywords definidas en aidu_servicios_keywords.
    """
    texto = " ".join(filter(None, [
        licitacion.get("nombre", ""),
        licitacion.get("descripcion", ""),
    ])).lower()

    if not texto:
        return []

    matches = []
    servicios = conn.execute(
        "SELECT cod_servicio, keywords, keywords_excluyentes FROM aidu_servicios_keywords"
    ).fetchall()

    for srv in servicios:
        keywords = [k.strip().lower() for k in (srv["keywords"] or "").split(",") if k.strip()]
        excluyentes = [k.strip().lower() for k in (srv["keywords_excluyentes"] or "").split(",") if k.strip()]

        # Si tiene palabra excluyente → score 0
        if any(ex in texto for ex in excluyentes):
            continue

        hits = sum(1 for kw in keywords if kw in texto)
        if hits == 0:
            continue

        # Score: proporción de keywords matched, ponderado por longitud
        score = min(1.0, hits / max(3, len(keywords) * 0.4))
        if score >= 0.3:  # umbral mínimo para considerarlo match
            matches.append((srv["cod_servicio"], round(score, 3)))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:3]  # top 3


def upsert_licitacion(raw: Dict) -> Tuple[bool, bool]:
    """
    UPSERT de una licitación en la BD.
    Retorna (insertada, actualizada): la primera es True si era nueva.
    """
    norm = _normalizar_licitacion(raw)
    if not norm.get("codigo_externo"):
        logger.warning("Licitación sin código, ignorada")
        return False, False

    conn = get_connection()
    try:
        # Check si ya existe
        existing = conn.execute(
            "SELECT codigo_externo FROM mp_licitaciones_adj WHERE codigo_externo = ?",
            (norm["codigo_externo"],)
        ).fetchone()

        if existing:
            # UPDATE: solo campos no-nulos del nuevo registro
            conn.execute("""
                UPDATE mp_licitaciones_adj SET
                    nombre = COALESCE(?, nombre),
                    descripcion = COALESCE(?, descripcion),
                    organismo = COALESCE(?, organismo),
                    region = COALESCE(?, region),
                    monto_referencial = COALESCE(?, monto_referencial),
                    monto_adjudicado = COALESCE(?, monto_adjudicado),
                    fecha_adjudicacion = COALESCE(?, fecha_adjudicacion),
                    pondera_precio_pct = COALESCE(?, pondera_precio_pct),
                    raw_json = ?
                WHERE codigo_externo = ?
            """, (
                norm["nombre"], norm["descripcion"], norm["organismo"], norm["region"],
                norm["monto_referencial"], norm["monto_adjudicado"], norm["fecha_adjudicacion"],
                norm["pondera_precio_pct"], norm["raw_json"], norm["codigo_externo"]
            ))
            conn.commit()
            return False, True
        else:
            # INSERT
            conn.execute("""
                INSERT INTO mp_licitaciones_adj (
                    codigo_externo, nombre, descripcion, organismo, organismo_codigo,
                    region, comuna, tipo, fecha_publicacion, fecha_cierre, fecha_adjudicacion,
                    monto_referencial, monto_adjudicado, estado, pondera_precio_pct, raw_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                norm["codigo_externo"], norm["nombre"], norm["descripcion"], norm["organismo"],
                norm["organismo_codigo"], norm["region"], norm["comuna"], norm["tipo"],
                norm["fecha_publicacion"], norm["fecha_cierre"], norm["fecha_adjudicacion"],
                norm["monto_referencial"], norm["monto_adjudicado"], norm["estado"],
                norm["pondera_precio_pct"], norm["raw_json"]
            ))

            # Categorización AIDU
            matches = _calcular_match_aidu(norm, conn)
            for cod_srv, conf in matches:
                conn.execute("""
                    INSERT OR REPLACE INTO mp_categorizacion_aidu
                        (codigo_externo, cod_servicio_aidu, confianza, metodo)
                    VALUES (?, ?, ?, 'keywords')
                """, (norm["codigo_externo"], cod_srv, conf))

            conn.commit()
            return True, False
    finally:
        conn.close()


def ingestar_lote(licitaciones: List[Dict], fecha: Optional[date] = None) -> Dict[str, int]:
    """
    Ingesta un lote de licitaciones, retorna estadísticas.
    Registra entrada en mp_ingesta_log.
    """
    import time
    inicio = time.time()
    n_insertadas = 0
    n_actualizadas = 0
    n_errores = 0

    for lic in licitaciones:
        try:
            ins, upd = upsert_licitacion(lic)
            if ins:
                n_insertadas += 1
            elif upd:
                n_actualizadas += 1
        except Exception as e:
            n_errores += 1
            logger.error(f"Error ingestando {lic.get('CodigoExterno')}: {e}")

    duracion = time.time() - inicio

    # Log de ingesta
    conn = get_connection()
    try:
        conn.execute("""
            INSERT INTO mp_ingesta_log (
                fecha_consultada, n_licitaciones_descargadas, n_nuevas, n_actualizadas,
                duracion_segundos, estado
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            fecha.isoformat() if fecha else None,
            len(licitaciones), n_insertadas, n_actualizadas,
            round(duracion, 2),
            "OK" if n_errores == 0 else "PARCIAL"
        ))
        conn.commit()
    finally:
        conn.close()

    return {
        "total": len(licitaciones),
        "nuevas": n_insertadas,
        "actualizadas": n_actualizadas,
        "errores": n_errores,
        "duracion": round(duracion, 2)
    }
