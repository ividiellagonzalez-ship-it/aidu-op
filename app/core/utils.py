"""
AIDU Op · Utilidades comunes
=============================
Funciones helper usadas en toda la app. Centralizadas para evitar
duplicación y facilitar cambios de formato.
"""
from datetime import datetime, date
from typing import Optional, Union


def formato_clp(monto: Optional[Union[int, float]]) -> str:
    """Formatea un monto en pesos chilenos: 1500000 → '$1.500.000'"""
    if monto is None or monto == 0:
        return "—"
    try:
        return f"${int(monto):,}".replace(",", ".")
    except (ValueError, TypeError):
        return "—"


def formato_clp_corto(monto: Optional[Union[int, float]]) -> str:
    """Versión corta para tarjetas: 7500000 → '$7.5M'"""
    if monto is None or monto == 0:
        return "—"
    try:
        m = int(monto)
        if m >= 1_000_000:
            return f"${m/1_000_000:.1f}M"
        elif m >= 1_000:
            return f"${m/1_000:.0f}K"
        return f"${m}"
    except (ValueError, TypeError):
        return "—"


def calcular_dias_cierre(fecha_cierre: Optional[str]) -> Optional[int]:
    """Calcula días desde hoy hasta la fecha de cierre. Negativo si ya pasó."""
    if not fecha_cierre:
        return None
    try:
        if isinstance(fecha_cierre, str):
            # Soporta formato 'YYYY-MM-DD' o 'YYYY-MM-DD HH:MM:SS'
            fecha = datetime.strptime(fecha_cierre[:10], "%Y-%m-%d").date()
        elif isinstance(fecha_cierre, (date, datetime)):
            fecha = fecha_cierre.date() if isinstance(fecha_cierre, datetime) else fecha_cierre
        else:
            return None
        hoy = date.today()
        return (fecha - hoy).days
    except (ValueError, TypeError):
        return None


def emoji_dias(dias: Optional[int]) -> str:
    """Emoji visual según urgencia. ≤3 días = rojo, ≤7 = amarillo, >7 = verde."""
    if dias is None:
        return "⚪"
    if dias < 0:
        return "⏱️"  # Ya cerró
    if dias <= 3:
        return "🔴"
    if dias <= 7:
        return "🟡"
    if dias <= 14:
        return "🟢"
    return "🔵"


def formato_fecha_corta(fecha: Optional[str]) -> str:
    """Formatea fecha: '2026-05-09' → '09/05/2026'"""
    if not fecha:
        return "—"
    try:
        if isinstance(fecha, str):
            d = datetime.strptime(fecha[:10], "%Y-%m-%d")
        else:
            d = fecha
        return d.strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return str(fecha)[:10] if fecha else "—"


def safe_int(valor, default: int = 0) -> int:
    """Conversión segura a int. Útil para datos de BD que pueden ser None."""
    if valor is None:
        return default
    try:
        return int(valor)
    except (ValueError, TypeError):
        return default


def safe_float(valor, default: float = 0.0) -> float:
    """Conversión segura a float."""
    if valor is None:
        return default
    try:
        return float(valor)
    except (ValueError, TypeError):
        return default


def truncar_texto(texto: Optional[str], max_len: int = 100) -> str:
    """Trunca texto largo agregando '...' al final."""
    if not texto:
        return ""
    if len(texto) <= max_len:
        return texto
    return texto[:max_len].rsplit(" ", 1)[0] + "..."


def formato_porcentaje(valor: Optional[float], decimales: int = 1) -> str:
    """Formatea porcentaje: 0.225 → '22.5%' o 22.5 → '22.5%'"""
    if valor is None:
        return "—"
    try:
        # Si viene como decimal (0-1), multiplicar
        v = float(valor)
        if 0 < v < 1:
            v = v * 100
        return f"{v:.{decimales}f}%"
    except (ValueError, TypeError):
        return "—"


def color_match_score(score: Optional[int]) -> str:
    """Color hex según match score. >=80 verde, 60-79 azul, 40-59 amarillo, <40 gris."""
    if score is None:
        return "#94A3B8"
    if score >= 80:
        return "#15803D"
    if score >= 60:
        return "#1E40AF"
    if score >= 40:
        return "#D97706"
    return "#94A3B8"


def color_estado(estado: str) -> str:
    """Color hex según estado pipeline."""
    mapa = {
        "PROSPECTO": "#64748B",
        "ESTUDIO": "#0891B2",
        "EN_PREPARACION": "#7C3AED",
        "LISTO_OFERTAR": "#D97706",
        "OFERTADO": "#1E40AF",
        "ADJUDICADO": "#15803D",
        "PERDIDO": "#DC2626",
        "DESCARTADO": "#94A3B8",
    }
    return mapa.get(estado, "#64748B")


def badge_html(texto: str, color: str = "#1E40AF", bg: Optional[str] = None) -> str:
    """Genera un badge HTML inline. Útil en tarjetas y headers."""
    if bg is None:
        # Color de fondo derivado del color principal con transparencia
        bg = f"{color}20"
    return (
        f"<span style='display:inline-block; padding:2px 8px; border-radius:12px; "
        f"background:{bg}; color:{color}; font-size:11px; font-weight:600;'>{texto}</span>"
    )
