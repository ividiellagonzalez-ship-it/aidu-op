"""
AIDU Op · Precalificación y Bitácora
======================================
Gestiona el checklist de requisitos típicos de licitaciones municipales
y mantiene una bitácora cronológica de cambios por proyecto.
"""
from typing import List, Dict, Optional
from datetime import datetime

from app.db.migrator import get_connection


# Checklist típico para licitaciones de consultoría municipal en Chile
CHECKLIST_TIPICO_MUNICIPAL = [
    # PROVEEDOR
    {"grupo": "Proveedor", "texto": "Inscripción ChileProveedores vigente", "auto_ok": True, "requiere_estado": "PROSPECTO"},
    {"grupo": "Proveedor", "texto": "Certificado de antecedentes tributarios al día (SII F30)", "auto_ok": False, "requiere_estado": "PROSPECTO"},
    {"grupo": "Proveedor", "texto": "Inicio de actividades SII vigente", "auto_ok": True, "requiere_estado": "PROSPECTO"},
    {"grupo": "Proveedor", "texto": "Certificado de cumplimiento de obligaciones laborales (F30-1)", "auto_ok": False, "requiere_estado": "ESTUDIO"},
    
    # EXPERIENCIA
    {"grupo": "Experiencia", "texto": "Experiencia mín. 3 trabajos similares en últimos 5 años", "auto_ok": False, "requiere_estado": "ESTUDIO"},
    {"grupo": "Experiencia", "texto": "Cartas de recomendación de clientes anteriores", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    {"grupo": "Experiencia", "texto": "Currículum del equipo profesional asignado", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    
    # EQUIPO PROFESIONAL
    {"grupo": "Equipo", "texto": "Profesional Ing. Civil titulado (Ignacio)", "auto_ok": True, "requiere_estado": "PROSPECTO"},
    {"grupo": "Equipo", "texto": "Certificado de título profesional", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    {"grupo": "Equipo", "texto": "Certificado Colegio de Ingenieros (si aplica)", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    
    # PROPUESTA
    {"grupo": "Propuesta", "texto": "Propuesta técnica (Anexo Word AIDU)", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    {"grupo": "Propuesta", "texto": "Propuesta económica (Anexo Excel AIDU)", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    {"grupo": "Propuesta", "texto": "Carta de presentación firmada", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    {"grupo": "Propuesta", "texto": "Cronograma de ejecución detallado", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    
    # GARANTÍAS Y FIANZAS
    {"grupo": "Garantías", "texto": "Garantía de seriedad de la oferta (verificar bases)", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    {"grupo": "Garantías", "texto": "Boleta de garantía o póliza de fiel cumplimiento", "auto_ok": False, "requiere_estado": "LISTO_OFERTAR"},
    
    # ANEXOS LEGALES
    {"grupo": "Anexos", "texto": "Anexo 1 - Identificación del oferente", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    {"grupo": "Anexos", "texto": "Anexo 2 - Declaración jurada inhabilidades", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    {"grupo": "Anexos", "texto": "Anexo 3 - Declaración jurada de experiencia", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
    {"grupo": "Anexos", "texto": "Anexo 4 - Declaración no afecto Art. 4° Ley 19.886", "auto_ok": False, "requiere_estado": "EN_PREPARACION"},
]


def inicializar_checklist(proyecto_id: int) -> int:
    """Crea el checklist típico para un proyecto si no lo tiene."""
    conn = get_connection()
    try:
        existe = conn.execute(
            "SELECT COUNT(*) FROM aidu_checklist WHERE proyecto_id = ?",
            (proyecto_id,)
        ).fetchone()[0]
        
        if existe > 0:
            return existe
        
        for orden, item in enumerate(CHECKLIST_TIPICO_MUNICIPAL):
            conn.execute("""
                INSERT INTO aidu_checklist (proyecto_id, grupo, texto, requiere_estado, completado, orden)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                proyecto_id, item["grupo"], item["texto"],
                item["requiere_estado"],
                1 if item.get("auto_ok") else 0,
                orden
            ))
        conn.commit()
        return len(CHECKLIST_TIPICO_MUNICIPAL)
    finally:
        conn.close()


def obtener_checklist(proyecto_id: int) -> List[Dict]:
    """Devuelve el checklist agrupado por categoría."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, grupo, texto, requiere_estado, completado, fecha_completado, orden
            FROM aidu_checklist
            WHERE proyecto_id = ?
            ORDER BY orden ASC
        """, (proyecto_id,)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def toggle_item_checklist(item_id: int, completado: bool) -> None:
    """Marca/desmarca un item del checklist."""
    conn = get_connection()
    try:
        if completado:
            conn.execute("""
                UPDATE aidu_checklist
                SET completado = 1, fecha_completado = datetime('now')
                WHERE id = ?
            """, (item_id,))
        else:
            conn.execute("""
                UPDATE aidu_checklist
                SET completado = 0, fecha_completado = NULL
                WHERE id = ?
            """, (item_id,))
        conn.commit()
    finally:
        conn.close()


def progreso_checklist(proyecto_id: int) -> Dict:
    """Devuelve métricas de progreso del checklist."""
    conn = get_connection()
    try:
        row = conn.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN completado = 1 THEN 1 ELSE 0 END) as completados
            FROM aidu_checklist
            WHERE proyecto_id = ?
        """, (proyecto_id,)).fetchone()
        
        total = row["total"] or 0
        completados = row["completados"] or 0
        pct = round(100 * completados / total) if total > 0 else 0
        
        return {
            "total": total,
            "completados": completados,
            "pendientes": total - completados,
            "porcentaje": pct,
        }
    finally:
        conn.close()


# ============================================================
# BITÁCORA
# ============================================================

def registrar_evento(
    proyecto_id: int,
    tipo: str,
    texto: str,
) -> int:
    """
    Registra un evento en la bitácora del proyecto.
    
    Tipos:
    - estado_cambio: "Cambio de estado: ESTUDIO → EN_PREPARACION"
    - paquete: "Generado Word + Excel"
    - ia: "Análisis estratégico Claude (~$0.01)"
    - nota: nota libre del usuario
    - checklist: "Marcado: 'Inicio actividades SII'"
    - sistema: eventos automáticos del sistema
    """
    conn = get_connection()
    try:
        cursor = conn.execute("""
            INSERT INTO aidu_comunicaciones (proyecto_id, tipo, texto, fecha)
            VALUES (?, ?, ?, datetime('now'))
        """, (proyecto_id, tipo, texto))
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def obtener_bitacora(proyecto_id: int, limit: int = 100) -> List[Dict]:
    """Devuelve la bitácora cronológica (más reciente primero)."""
    conn = get_connection()
    try:
        rows = conn.execute("""
            SELECT id, tipo, texto, fecha
            FROM aidu_comunicaciones
            WHERE proyecto_id = ?
            ORDER BY fecha DESC, id DESC
            LIMIT ?
        """, (proyecto_id, limit)).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
