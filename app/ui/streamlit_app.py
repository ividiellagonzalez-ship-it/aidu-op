"""
AIDU Op · UI Streamlit v2
==========================
Interfaz visual completa con:
- Cartera con macro de 5 pasos
- Búsqueda en histórico Mercado Público
- Inteligencia de mercado por categoría AIDU
- Sistema (estado, backups, demo)
- VISTA DE DETALLE COMPLETA del proyecto con:
  * Información general
  * Inteligencia de precios (3 escenarios calculados)
  * Comparables del mercado
  * Competidores recurrentes
  * Cronología/checklist

Lanzar con:
    streamlit run app/ui/streamlit_app.py
"""
import streamlit as st
import sys
import os
from pathlib import Path
from datetime import date, datetime as dt

# Asegurar imports relativos
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db.migrator import get_connection, run_migrations
from app.core.backfill import estado_actual
from app.core.inteligencia_precios import (
    calcular_escenarios_precio,
    obtener_estadisticas_categoria,
    licitaciones_similares,
)
from config.settings import get_version, AIDU_HOME


# ============================================================
# Aplicar migraciones pendientes al inicio (idempotente)
# ============================================================
@st.cache_resource
def _ensure_migrations_applied():
    """Aplica migraciones pendientes una sola vez por sesión Streamlit."""
    try:
        n, applied = run_migrations()
        if n > 0:
            print(f"✅ Aplicadas {n} migraciones: {applied}")
        return True
    except Exception as e:
        print(f"⚠️ Error aplicando migraciones: {e}")
        return False


_ensure_migrations_applied()


# ============================================================
# CONFIG STREAMLIT
# ============================================================
st.set_page_config(
    page_title="AIDU Op",
    page_icon="●",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Sistema de Diseño AIDU Op v2.1 — Profesional
st.markdown("""
<style>
/* ============================================================
   AIDU OP · DESIGN SYSTEM v2.1
   ============================================================ */

/* Tipografía global - Inter via Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    --aidu-blue: #1E40AF;
    --aidu-blue-light: #3B82F6;
    --aidu-blue-dark: #1E3A8A;
    --aidu-success: #15803D;
    --aidu-warning: #D97706;
    --aidu-danger: #DC2626;
    --aidu-gray-50: #F8FAFC;
    --aidu-gray-100: #F1F5F9;
    --aidu-gray-200: #E2E8F0;
    --aidu-gray-300: #CBD5E1;
    --aidu-gray-500: #64748B;
    --aidu-gray-700: #334155;
    --aidu-gray-900: #0F172A;
    
    --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-md: 0 4px 12px rgba(15, 23, 42, 0.06);
    --shadow-lg: 0 10px 25px rgba(15, 23, 42, 0.10);
    
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;
}

/* ============ Aplicar Inter a toda la app ============ */
html, body, [class*="st-"], [class*="css-"], div, p, span, button {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
code, pre, [class*="monospace"] {
    font-family: 'JetBrains Mono', monospace !important;
}

/* ============ Logo AIDU ============ */
.aidu-logo {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 4px;
}
.aidu-logo .dot {
    width: 12px;
    height: 12px;
    background: linear-gradient(135deg, var(--aidu-blue) 0%, var(--aidu-blue-light) 100%);
    border-radius: 50%;
    box-shadow: 0 0 16px rgba(59, 130, 246, 0.5);
}
.aidu-logo .aidu-text {
    font-size: 28px;
    font-weight: 800;
    color: var(--aidu-blue);
    letter-spacing: -1px;
}
.aidu-logo .op-text {
    font-size: 13px;
    color: var(--aidu-gray-700);
    padding: 3px 10px;
    background: var(--aidu-gray-100);
    border-radius: 6px;
    font-weight: 600;
    letter-spacing: 0.5px;
}

/* ============ Tipografía ============ */
h1, h2, h3, h4, h5, h6 {
    font-family: 'Inter', sans-serif !important;
    color: var(--aidu-gray-900) !important;
    letter-spacing: -0.025em;
    font-weight: 700 !important;
}

h1 { font-size: 30px !important; }
h2 { font-size: 24px !important; }
h3 { font-size: 19px !important; }
h4 { font-size: 16px !important; }

/* ============ Métricas profesionales ============ */
div[data-testid="stMetricValue"] {
    font-weight: 700;
    color: var(--aidu-blue);
    font-size: 28px !important;
    letter-spacing: -0.025em;
}
div[data-testid="stMetricLabel"] {
    font-size: 12px !important;
    color: var(--aidu-gray-500) !important;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
div[data-testid="stMetricDelta"] {
    font-size: 12px !important;
    font-weight: 600;
}

/* ============ Botones primarios ============ */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--aidu-blue) 0%, var(--aidu-blue-light) 100%);
    border: none;
    box-shadow: var(--shadow-sm);
    font-weight: 600;
    transition: all 0.2s ease;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-1px);
    box-shadow: var(--shadow-md);
}
.stButton > button {
    border-radius: var(--radius-md);
    font-weight: 500;
    transition: all 0.15s ease;
}

/* ============ Inputs ============ */
.stTextInput input, .stNumberInput input, .stSelectbox > div > div {
    border-radius: var(--radius-sm) !important;
    border-color: var(--aidu-gray-200) !important;
}
.stTextInput input:focus, .stNumberInput input:focus {
    border-color: var(--aidu-blue) !important;
    box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1) !important;
}

/* ============ Estados con tags ============ */
.estado-tag {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}
.estado-PROSPECTO { background: #F1F5F9; color: #475569; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.estado-ESTUDIO { background: #CFFAFE; color: #0E7490; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.estado-EN_PREPARACION { background: #DBEAFE; color: #1E40AF; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.estado-LISTO_OFERTAR { background: #FED7AA; color: #9A3412; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.estado-OFERTADA { background: #E9D5FF; color: #6B21A8; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.estado-ADJUDICADA { background: #BBF7D0; color: #14532D; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }

/* ============ Macro Flow (steppers) ============ */
.macro-flow {
    background: linear-gradient(135deg, var(--aidu-gray-50) 0%, white 100%);
    padding: 16px 20px;
    border-radius: var(--radius-md);
    margin-bottom: 16px;
    display: flex;
    gap: 8px;
    align-items: center;
    border: 1px solid var(--aidu-gray-200);
    box-shadow: var(--shadow-sm);
}
.macro-step {
    flex: 1;
    padding: 10px 14px;
    background: white;
    border-radius: var(--radius-sm);
    text-align: center;
    font-size: 12px;
    font-weight: 600;
    color: var(--aidu-gray-500);
    border: 1px solid var(--aidu-gray-200);
    transition: all 0.2s ease;
}
.macro-arrow { color: var(--aidu-gray-300); font-weight: 700; font-size: 14px; }

/* ============ Tarjetas de oportunidad/proyecto ============ */
.aidu-card {
    background: white;
    border: 1px solid var(--aidu-gray-200);
    border-radius: var(--radius-md);
    padding: 16px 20px;
    margin-bottom: 12px;
    box-shadow: var(--shadow-sm);
    transition: all 0.2s ease;
}
.aidu-card:hover {
    border-color: var(--aidu-blue-light);
    box-shadow: var(--shadow-md);
    transform: translateY(-1px);
}
.aidu-card-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--aidu-gray-900);
    margin-bottom: 6px;
    line-height: 1.3;
}
.aidu-card-meta {
    font-size: 12px;
    color: var(--aidu-gray-500);
    line-height: 1.5;
}
.aidu-card-code {
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 11px;
    color: var(--aidu-gray-300);
}

/* ============ Sidebar profesional ============ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FCFCFD 0%, #F5F7FA 100%);
    border-right: 1px solid var(--aidu-gray-200);
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 8px;
}

/* Items del radio en sidebar como nav vertical */
[data-testid="stSidebar"] [data-baseweb="radio"] {
    margin: 0 !important;
}
[data-testid="stSidebar"] [data-baseweb="radio"] label {
    display: flex;
    align-items: center;
    padding: 10px 14px !important;
    border-radius: var(--radius-md);
    margin: 2px 0 !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    color: var(--aidu-gray-700) !important;
    cursor: pointer;
    transition: all 0.15s ease;
    border: 1px solid transparent;
}
[data-testid="stSidebar"] [data-baseweb="radio"] label:hover {
    background: rgba(30, 64, 175, 0.06);
    color: var(--aidu-blue) !important;
}
[data-testid="stSidebar"] [data-baseweb="radio"] input:checked + div + div {
    color: var(--aidu-blue) !important;
    font-weight: 600 !important;
}
/* Ocultar el círculo del radio */
[data-testid="stSidebar"] [data-baseweb="radio"] [role="radio"] {
    display: none !important;
}

.aidu-sidebar-header {
    padding: 12px 8px 16px;
    border-bottom: 1px solid var(--aidu-gray-200);
    margin-bottom: 16px;
}
.aidu-sidebar-stat {
    padding: 10px 14px;
    background: white;
    border-radius: var(--radius-md);
    border: 1px solid var(--aidu-gray-200);
    margin: 6px 0;
    font-size: 12px;
    color: var(--aidu-gray-700);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.aidu-sidebar-stat strong {
    color: var(--aidu-blue);
    font-size: 18px;
    font-weight: 700;
}

/* ============ Badges ============ */
.aidu-badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    background: var(--aidu-gray-100);
    color: var(--aidu-gray-700);
}
.aidu-badge-blue { background: rgba(30, 64, 175, 0.1); color: var(--aidu-blue); }
.aidu-badge-green { background: rgba(21, 128, 61, 0.1); color: var(--aidu-success); }
.aidu-badge-orange { background: rgba(217, 119, 6, 0.1); color: var(--aidu-warning); }
.aidu-badge-red { background: rgba(220, 38, 38, 0.1); color: var(--aidu-danger); }

/* ============ Sección hero ============ */
.aidu-hero {
    padding: 8px 0 16px;
    border-bottom: 1px solid var(--aidu-gray-200);
    margin-bottom: 24px;
}
.aidu-hero h1 {
    margin: 0 !important;
    font-size: 28px !important;
    color: var(--aidu-gray-900) !important;
}
.aidu-hero p {
    margin: 4px 0 0 !important;
    font-size: 14px;
    color: var(--aidu-gray-500);
}

/* ============ Escenarios de precio ============ */
.escenario-card {
    padding: 18px;
    border-radius: var(--radius-md);
    text-align: center;
    margin: 4px;
    box-shadow: var(--shadow-sm);
    transition: all 0.2s ease;
}
.escenario-card:hover { transform: translateY(-2px); box-shadow: var(--shadow-md); }
.escenario-agresivo { background: linear-gradient(180deg, #FEE2E2 0%, white 60%); border-top: 3px solid var(--aidu-danger); }
.escenario-competitivo { background: linear-gradient(180deg, #FED7AA 0%, white 60%); border-top: 3px solid var(--aidu-warning); }
.escenario-premium { background: linear-gradient(180deg, #BBF7D0 0%, white 60%); border-top: 3px solid var(--aidu-success); }
.esc-label { font-size: 10px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase; color: var(--aidu-gray-500); }
.esc-precio { font-size: 26px; font-weight: 800; margin: 8px 0; color: var(--aidu-gray-900); letter-spacing: -0.5px; }
.esc-margen { font-size: 12px; color: var(--aidu-gray-700); }
.esc-prob { font-size: 16px; font-weight: 700; margin-top: 8px; }

/* ============ Tablas ============ */
[data-testid="stDataFrame"] {
    border: 1px solid var(--aidu-gray-200);
    border-radius: var(--radius-md);
    overflow: hidden;
}

/* ============ Mejoras varias ============ */
hr {
    margin: 24px 0 !important;
    border-color: var(--aidu-gray-200) !important;
}

/* Reducir padding superior global */
.block-container {
    padding-top: 1.5rem !important;
    max-width: 1280px;
}

/* Spinner más sutil */
.stSpinner > div {
    border-top-color: var(--aidu-blue) !important;
}

/* Alertas */
[data-testid="stAlert"] {
    border-radius: var(--radius-md);
    border-width: 1px;
    box-shadow: var(--shadow-sm);
}

/* Expander más limpio */
[data-testid="stExpander"] {
    border-radius: var(--radius-md);
    border: 1px solid var(--aidu-gray-200);
    box-shadow: var(--shadow-sm);
}

/* Code blocks */
code {
    background: var(--aidu-gray-100) !important;
    color: var(--aidu-blue-dark) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-size: 13px !important;
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# SESSION STATE
# ============================================================
if "view_proyecto_id" not in st.session_state:
    st.session_state.view_proyecto_id = None


# ============================================================
# HELPERS
# ============================================================
def formato_clp(n):
    if n is None or n == 0:
        return "$0"
    return f"${int(n):,}".replace(",", ".")


def calcular_dias_cierre(fecha_cierre_str):
    if not fecha_cierre_str:
        return None
    try:
        cierre = dt.fromisoformat(fecha_cierre_str).date()
        return (cierre - date.today()).days
    except Exception:
        return None


def emoji_dias(d):
    if d is None:
        return "⚪"
    if d <= 3:
        return "🔴"
    if d <= 7:
        return "🟡"
    return "🟢"


# ============================================================
# VISTA DE DETALLE DEL PROYECTO
# ============================================================
def render_detalle_proyecto(proyecto_id: int):
    """Renderiza la vista completa de un proyecto"""
    conn = get_connection()
    p = conn.execute("SELECT * FROM aidu_proyectos WHERE id = ?", (proyecto_id,)).fetchone()
    conn.close()

    if not p:
        st.error("Proyecto no encontrado")
        if st.button("← Volver a cartera"):
            st.session_state.view_proyecto_id = None
            st.rerun()
        return

    # Botón volver
    col_back, col_estado = st.columns([1, 5])
    if col_back.button("← Volver a cartera", use_container_width=True):
        st.session_state.view_proyecto_id = None
        st.rerun()

    col_estado.markdown(
        f"<div style='text-align:right; padding-top:6px;'>"
        f"<span class='estado-{p['estado']}'>{p['estado']}</span></div>",
        unsafe_allow_html=True
    )

    # Header del proyecto
    st.markdown(f"### {p['nombre']}")
    st.caption(
        f"📋 `{p['codigo_externo']}` · 🏛️ {p['organismo']} · "
        f"📍 {p['region']} · {p['cod_servicio_aidu']}"
    )

    # KPIs principales del proyecto
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Monto referencial", formato_clp(p["monto_referencial"]))
    dias = calcular_dias_cierre(p["fecha_cierre"])
    col2.metric("Días cierre", f"{emoji_dias(dias)} {dias if dias is not None else '-'}")
    col3.metric("HH estimadas", f"{(p['hh_ignacio_estimado'] or 0) + (p['hh_jorella_estimado'] or 0)} h")
    col4.metric("Categoría", p["cod_servicio_aidu"] or "-")

    st.divider()

    # Tabs internas del proyecto - vista completa
    tab_info, tab_precal, tab_precios, tab_comparables, tab_equipo, tab_acciones, tab_bitacora = st.tabs([
        "📋 Resumen",
        "✅ Precalificación",
        "💰 Inteligencia",
        "📚 Comparables",
        "👥 Equipo & HH",
        "🎯 Acciones",
        "📜 Bitácora",
    ])

    # ======================================
    # TAB: INFORMACIÓN
    # ======================================
    with tab_info:
        st.markdown("##### 📋 Descripción del proyecto")
        st.info(p["descripcion"] or "Sin descripción registrada")

        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("##### 👥 Equipo asignado AIDU")
            st.markdown(f"""
            - **Ignacio (Director Ejecutivo):** {p['hh_ignacio_estimado'] or 0} h
            - **Jorella (Socia Operacional):** {p['hh_jorella_estimado'] or 0} h
            - **Total:** {(p['hh_ignacio_estimado'] or 0) + (p['hh_jorella_estimado'] or 0)} h
            """)

        with col_b:
            st.markdown("##### 📅 Fechas clave")
            st.markdown(f"""
            - **Publicación:** {p['fecha_publicacion'] or '-'}
            - **Cierre:** {p['fecha_cierre'] or '-'}
            - **Creación en sistema:** {p['fecha_creacion']}
            """)

        # Recomendación rápida
        if dias is not None and dias <= 3:
            st.error("🔴 **URGENTE**: Cierre en menos de 3 días")
        elif dias is not None and dias <= 7:
            st.warning("🟡 **Atención**: Cierre en menos de 7 días")
        else:
            st.success("🟢 **Plazo cómodo** para preparar la propuesta")

    # ======================================
    # TAB: PRECALIFICACIÓN
    # ======================================
    with tab_precal:
        from app.core.precalificacion import (
            inicializar_checklist, obtener_checklist, toggle_item_checklist,
            progreso_checklist, registrar_evento
        )
        
        # Inicializar checklist si no existe
        inicializar_checklist(p["id"])
        
        prog = progreso_checklist(p["id"])
        items = obtener_checklist(p["id"])
        
        # Header con progreso
        col_h1, col_h2 = st.columns([3, 1])
        with col_h1:
            st.markdown("##### ✅ Checklist de precalificación")
            st.caption("Requisitos típicos para licitaciones de consultoría municipal en Chile. Marca lo que ya tienes listo.")
        with col_h2:
            st.metric("Progreso", f"{prog['porcentaje']}%", f"{prog['completados']}/{prog['total']}")
        
        # Barra de progreso visual
        st.progress(prog["porcentaje"] / 100, text=f"{prog['completados']} de {prog['total']} items completados")
        
        # Alerta si falta mucho
        if prog["porcentaje"] < 30:
            st.warning(f"⚠️ Quedan {prog['pendientes']} items por completar. Empieza por los del grupo **Proveedor** y **Equipo**.")
        elif prog["porcentaje"] < 70:
            st.info(f"📋 Buen avance. Concéntrate en completar **Propuesta** y **Anexos legales**.")
        elif prog["porcentaje"] < 100:
            st.success(f"🎯 Casi listo. Revisa **Garantías** y verifica cada documento antes de subir a MP.")
        else:
            st.success("🏆 Precalificación completa. Listo para postular.")
        
        st.divider()
        
        # Agrupar items por grupo
        grupos = {}
        for item in items:
            g = item["grupo"]
            if g not in grupos:
                grupos[g] = []
            grupos[g].append(item)
        
        # Mostrar cada grupo
        emoji_grupo = {
            "Proveedor": "🏢",
            "Experiencia": "📊",
            "Equipo": "👥",
            "Propuesta": "📄",
            "Garantías": "🛡️",
            "Anexos": "📎",
        }
        
        for grupo, lista_items in grupos.items():
            n_done = sum(1 for i in lista_items if i["completado"])
            emoji = emoji_grupo.get(grupo, "📌")
            with st.expander(f"{emoji} **{grupo}** · {n_done}/{len(lista_items)}", expanded=(n_done < len(lista_items))):
                for item in lista_items:
                    completado_actual = bool(item["completado"])
                    nuevo_estado = st.checkbox(
                        item["texto"],
                        value=completado_actual,
                        key=f"chk_{item['id']}_{p['id']}",
                        help=f"Requerido en estado: {item['requiere_estado']}"
                    )
                    if nuevo_estado != completado_actual:
                        toggle_item_checklist(item["id"], nuevo_estado)
                        accion = "Marcado ✓" if nuevo_estado else "Desmarcado"
                        registrar_evento(p["id"], "checklist", f"{accion}: {item['texto']}")
                        st.rerun()


    # ======================================
    # TAB: INTELIGENCIA DE PRECIOS
    # ======================================
    with tab_precios:
        st.markdown("##### 💰 Análisis de Precios basado en Histórico Mercado Público")

        with st.spinner("Calculando 3 escenarios..."):
            esc = calcular_escenarios_precio(proyecto_id)

        if "error" in esc:
            st.error(esc["error"])
        else:
            # Stats de mercado
            stats = esc["stats"]
            n_total = stats["n_total"] or 0

            if n_total == 0:
                st.warning(
                    f"⚠️ Sin datos históricos suficientes para {p['cod_servicio_aidu']}. "
                    "Los escenarios usan estimaciones conservadoras. "
                    "Ejecuta el backfill 24m para enriquecer los datos."
                )
            else:
                st.caption(
                    f"📊 Análisis basado en **{n_total} licitaciones similares** del histórico. "
                    f"Descuento mediana del mercado: **{stats['descuento_mediana']:.1f}%**"
                )

            # Costo base AIDU
            costo = esc["costo"]
            with st.expander("⚙️ Costo Base AIDU (transparencia del cálculo)", expanded=False):
                col_c1, col_c2 = st.columns(2)
                col_c1.markdown(f"""
                **Cálculo del costo:**
                - HH × tarifa: {costo['hh_total']} h × ${costo['tarifa_hora_clp']:,.0f} = {formato_clp(costo['costo_hh'])}
                - Viajes ({p['region']}): {formato_clp(costo['viajes'])}
                - Subtotal: {formato_clp(costo['costo_hh'] + costo['viajes'])}
                - Overhead 18%: {formato_clp(costo['overhead'])}
                """)
                col_c2.metric("**Costo total AIDU**", formato_clp(costo["costo_total"]))

            st.markdown("##### 🎯 3 Escenarios de Precio")

            col_a, col_b, col_c = st.columns(3)

            with col_a:
                a = esc["agresivo"]
                color = "#15803D" if a["margen_pct"] >= 15 else "#D97706" if a["margen_pct"] >= 0 else "#DC2626"
                st.markdown(f"""
                <div class='escenario-card escenario-agresivo'>
                    <div class='esc-label'>🥇 ENTRADA</div>
                    <div style='font-weight: 700; font-size: 14px; margin: 8px 0;'>{a['estrategia']}</div>
                    <div class='esc-precio' style='color: #DC2626;'>{formato_clp(a['precio'])}</div>
                    <div class='esc-margen'>Descuento: {a['descuento_pct']}% · Margen: <strong style='color:{color}'>{a['margen_pct']:.1f}%</strong></div>
                    <div class='esc-prob' style='color: #DC2626;'>{a['probabilidad']}% probabilidad</div>
                    <div style='font-size: 11px; color: #64748B; margin-top: 8px;'>{a['descripcion']}</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("Elegir Agresivo", key="elig_a", use_container_width=True):
                    _set_escenario(proyecto_id, "agresivo", a["precio"], a["margen_pct"], a["probabilidad"])
                    st.success("✓ Escenario agresivo seleccionado")

            with col_b:
                c = esc["competitivo"]
                color = "#15803D" if c["margen_pct"] >= 15 else "#D97706" if c["margen_pct"] >= 0 else "#DC2626"
                st.markdown(f"""
                <div class='escenario-card escenario-competitivo'>
                    <div class='esc-label'>⚡ ÓPTIMO ⭐</div>
                    <div style='font-weight: 700; font-size: 14px; margin: 8px 0;'>{c['estrategia']}</div>
                    <div class='esc-precio' style='color: #D97706;'>{formato_clp(c['precio'])}</div>
                    <div class='esc-margen'>Descuento: {c['descuento_pct']}% · Margen: <strong style='color:{color}'>{c['margen_pct']:.1f}%</strong></div>
                    <div class='esc-prob' style='color: #D97706;'>{c['probabilidad']}% probabilidad</div>
                    <div style='font-size: 11px; color: #64748B; margin-top: 8px;'>{c['descripcion']}</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("Elegir Competitivo", key="elig_c", use_container_width=True, type="primary"):
                    _set_escenario(proyecto_id, "competitivo", c["precio"], c["margen_pct"], c["probabilidad"])
                    st.success("✓ Escenario competitivo seleccionado")

            with col_c:
                pr = esc["premium"]
                color = "#15803D" if pr["margen_pct"] >= 15 else "#D97706" if pr["margen_pct"] >= 0 else "#DC2626"
                st.markdown(f"""
                <div class='escenario-card escenario-premium'>
                    <div class='esc-label'>💎 NICHO</div>
                    <div style='font-weight: 700; font-size: 14px; margin: 8px 0;'>{pr['estrategia']}</div>
                    <div class='esc-precio' style='color: #15803D;'>{formato_clp(pr['precio'])}</div>
                    <div class='esc-margen'>Descuento: {pr['descuento_pct']}% · Margen: <strong style='color:{color}'>{pr['margen_pct']:.1f}%</strong></div>
                    <div class='esc-prob' style='color: #15803D;'>{pr['probabilidad']}% probabilidad</div>
                    <div style='font-size: 11px; color: #64748B; margin-top: 8px;'>{pr['descripcion']}</div>
                </div>
                """, unsafe_allow_html=True)
                if st.button("Elegir Premium", key="elig_p", use_container_width=True):
                    _set_escenario(proyecto_id, "premium", pr["precio"], pr["margen_pct"], pr["probabilidad"])
                    st.success("✓ Escenario premium seleccionado")

            # Recomendación honesta
            st.markdown("---")
            mejor = max(["agresivo", "competitivo", "premium"], key=lambda k: esc[k]["margen_pct"] * (esc[k]["probabilidad"] / 100))
            st.info(
                f"💡 **Recomendación AIDU:** según el balance margen × probabilidad, "
                f"el escenario **{mejor}** ({formato_clp(esc[mejor]['precio'])}, "
                f"{esc[mejor]['margen_pct']:.1f}% margen, {esc[mejor]['probabilidad']}% probabilidad) "
                f"es el más conveniente."
            )

            # Si todos los márgenes son negativos, alerta
            if all(esc[k]["margen_pct"] < 0 for k in ["agresivo", "competitivo", "premium"]):
                st.error(
                    "⚠️ **ALERTA:** Todos los escenarios muestran margen negativo. "
                    "El costo AIDU excede los precios de mercado. "
                    "Considera: (1) revisar HH estimadas, (2) NO postular, (3) renegociar alcance con organismo."
                )

            # Competidores recurrentes
            if stats["competidores_recurrentes"]:
                st.markdown("##### 🥇 Competidores recurrentes en esta categoría")
                for comp in stats["competidores_recurrentes"]:
                    st.markdown(f"- **{comp['nombre']}** · {comp['n_adj']} adjudicaciones")

    # ======================================
    # TAB: COMPARABLES
    # ======================================
    with tab_comparables:
        from app.core.comparables import buscar_comparables_proyecto
        from app.core.utils import formato_clp_corto, formato_porcentaje
        
        st.markdown(f"##### 📚 Inteligencia de mercado · categoría {p['cod_servicio_aidu']}")
        st.caption("Análisis basado en licitaciones adjudicadas históricas en la misma categoría AIDU")
        
        with st.spinner("Buscando comparables..."):
            data_comp = buscar_comparables_proyecto(p["id"], limit=20)
        
        if data_comp["total_encontrados"] == 0:
            st.info(f"Sin comparables adjudicados para **{p['cod_servicio_aidu']}**. Ejecuta el backfill 24m desde Configuración para enriquecer datos.")
        else:
            # Stats panel
            stats = data_comp["stats"]
            
            st.markdown("##### 📊 Estadísticas del mercado")
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            col_s1.metric(
                "Comparables",
                data_comp["total_encontrados"],
                help=f"Adjudicaciones históricas en {p['cod_servicio_aidu']}"
            )
            if stats.get("descuento_promedio") is not None:
                col_s2.metric(
                    "Descuento medio",
                    f"{stats['descuento_promedio']}%",
                    delta=f"min {stats.get('descuento_min', 0)}% / max {stats.get('descuento_max', 0)}%",
                    delta_color="off",
                    help="% típico de descuento sobre el referencial al adjudicar"
                )
            if stats.get("monto_adj_mediano"):
                col_s3.metric(
                    "Monto típico",
                    formato_clp_corto(stats["monto_adj_mediano"]),
                    help="Monto mediano adjudicado en esta categoría"
                )
            if stats.get("n_oferentes_promedio"):
                col_s4.metric(
                    "Oferentes promedio",
                    f"{stats['n_oferentes_promedio']:.1f}",
                    help="Promedio de oferentes que postulan"
                )
            
            # Insight automático
            if stats.get("descuento_promedio") is not None:
                desc_prom = stats["descuento_promedio"]
                if desc_prom < 5:
                    st.success(f"💚 **Mercado sano**: descuentos promedio bajos ({desc_prom}%) indican poca presión competitiva")
                elif desc_prom < 12:
                    st.info(f"📊 **Mercado equilibrado**: descuentos promedio razonables ({desc_prom}%)")
                elif desc_prom < 20:
                    st.warning(f"⚠️ **Mercado competitivo**: descuentos altos ({desc_prom}%), evaluar diferenciación")
                else:
                    st.error(f"🔴 **Mercado muy competitivo**: descuentos {desc_prom}%, márgenes apretados")
            
            st.divider()
            
            # Layout en 2 columnas: mandantes y competencia
            col_m, col_c = st.columns(2)
            
            with col_m:
                st.markdown("##### 🏛️ Mandantes recurrentes")
                if data_comp["mandantes_recurrentes"]:
                    for i, m in enumerate(data_comp["mandantes_recurrentes"][:5], 1):
                        st.markdown(
                            f"<div style='padding:6px 10px; background:#F1F5F9; border-radius:6px; margin-bottom:4px; font-size:13px;'>"
                            f"<strong>#{i}</strong> {m['nombre']} <span style='color:#64748B; float:right;'>{m['cantidad']} adj.</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                else:
                    st.caption("Sin datos suficientes")
            
            with col_c:
                st.markdown("##### 🥊 Competencia")
                if data_comp["competencia"]:
                    for i, c in enumerate(data_comp["competencia"][:5], 1):
                        st.markdown(
                            f"<div style='padding:6px 10px; background:#FEF3C7; border-radius:6px; margin-bottom:4px; font-size:13px;'>"
                            f"<strong>#{i}</strong> {c['nombre']} <span style='color:#92400E; float:right;'>{c['adjudicaciones']} adj.</span>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
                else:
                    st.caption("Sin datos de proveedores ganadores")
            
            st.divider()
            
            # Listado detallado
            with st.expander(f"📋 Ver listado detallado ({data_comp['total_encontrados']} licitaciones)", expanded=False):
                for c in data_comp["comparables"]:
                    with st.container(border=True):
                        col1, col2, col3 = st.columns([4, 2, 2])
                        col1.markdown(f"""
                        **{c['nombre']}**  
                        <span style='color:#64748B; font-size:12px;'>
                        🏛️ {c['organismo'] or '—'} · 📍 {c['region'] or '—'}
                        </span><br>
                        <span style='color:#94A3B8; font-family:monospace; font-size:11px;'>{c['codigo_externo']}</span>
                        """, unsafe_allow_html=True)
                        col2.metric("Referencial", formato_clp_corto(c["monto_referencial"]))
                        if c.get("descuento_pct") is not None:
                            col3.metric(
                                "Adjudicado",
                                formato_clp_corto(c["monto_adjudicado"]),
                                f"{c['descuento_pct']:.1f}%",
                                delta_color="inverse"
                            )
                        else:
                            col3.metric("Adjudicado", formato_clp_corto(c["monto_adjudicado"]))

    # ======================================
    # TAB: EQUIPO & HH
    # ======================================
    with tab_equipo:
        st.markdown("##### 👥 Asignación de Equipo y Horas Hombre")
        st.caption("Estima HH por persona y calcula costo base AIDU. Tarifa: 2 UF/h ≈ CLP 78.000/h")
        
        TARIFA_HORA_CLP = 78_000
        
        col_e1, col_e2 = st.columns(2)
        with col_e1:
            st.markdown("**Ignacio (Director Ejecutivo · Ing. Civil)**")
            hh_ig = st.number_input(
                "HH Ignacio",
                min_value=0, max_value=500,
                value=int(p["hh_ignacio_estimado"] or 0),
                step=5,
                key=f"hh_ig_{p['id']}"
            )
            st.caption(f"Costo: {formato_clp(hh_ig * TARIFA_HORA_CLP)}")
        
        with col_e2:
            st.markdown("**Jorella (Socia Operacional · Ing. Comercial)**")
            hh_jo = st.number_input(
                "HH Jorella",
                min_value=0, max_value=500,
                value=int(p["hh_jorella_estimado"] or 0),
                step=5,
                key=f"hh_jo_{p['id']}"
            )
            st.caption(f"Costo: {formato_clp(hh_jo * TARIFA_HORA_CLP)}")
        
        # Botón guardar HH
        if st.button("💾 Guardar HH estimadas", key=f"save_hh_{p['id']}", type="primary"):
            from app.core.precalificacion import registrar_evento
            conn_save = get_connection()
            try:
                conn_save.execute("""
                    UPDATE aidu_proyectos 
                    SET hh_ignacio_estimado = ?, hh_jorella_estimado = ?, fecha_modificacion = datetime('now')
                    WHERE id = ?
                """, (hh_ig, hh_jo, p["id"]))
                conn_save.commit()
                registrar_evento(p["id"], "estimacion", f"HH actualizadas: Ignacio {hh_ig}h, Jorella {hh_jo}h")
                st.success("✅ HH guardadas")
                st.rerun()
            finally:
                conn_save.close()
        
        st.divider()
        
        # Resumen de costos
        total_hh = hh_ig + hh_jo
        costo_base = total_hh * TARIFA_HORA_CLP
        overhead_pct = 18
        costo_overhead = round(costo_base * overhead_pct / 100)
        costo_total = costo_base + costo_overhead
        
        st.markdown("##### 💰 Costo base AIDU")
        col_c1, col_c2, col_c3, col_c4 = st.columns(4)
        col_c1.metric("Total HH", f"{total_hh} h")
        col_c2.metric("Costo HH", formato_clp(costo_base))
        col_c3.metric(f"Overhead ({overhead_pct}%)", formato_clp(costo_overhead))
        col_c4.metric("Costo total", formato_clp(costo_total))
        
        # Comparar con monto referencial
        if p["monto_referencial"] and costo_total > 0:
            margen_max = ((p["monto_referencial"] - costo_total) / p["monto_referencial"]) * 100
            if margen_max > 30:
                st.success(f"💚 Margen máximo posible: **{margen_max:.1f}%** sobre referencial. Espacio para descuento competitivo.")
            elif margen_max > 15:
                st.info(f"📊 Margen máximo posible: **{margen_max:.1f}%** sobre referencial. Margen razonable.")
            elif margen_max > 0:
                st.warning(f"⚠️ Margen máximo posible: **{margen_max:.1f}%** sobre referencial. Margen ajustado, evaluar.")
            else:
                st.error(f"🔴 Pérdida de **{margen_max:.1f}%** al precio referencial. **NO postular** sin redefinir alcance.")


    # ======================================
    # TAB: ACCIONES
    # ======================================
    with tab_acciones:
        st.markdown("##### 🎯 Decisiones de flujo")

        col_a, col_b = st.columns(2)

        with col_a:
            st.markdown(f"**Estado actual:** `{p['estado']}`")
            st.caption("Cambia el estado del proyecto siguiendo el macro de 5 pasos")

            if p["estado"] == "PROSPECTO":
                if st.button("🔬 Pasar a ESTUDIO", use_container_width=True, type="primary"):
                    _cambiar_estado(proyecto_id, "ESTUDIO")
                    st.success("✓ Estado actualizado")
                    st.rerun()

            elif p["estado"] == "ESTUDIO":
                if st.button("📝 Pasar a EN PREPARACIÓN", use_container_width=True, type="primary"):
                    _cambiar_estado(proyecto_id, "EN_PREPARACION")
                    st.success("✓ Estado actualizado")
                    st.rerun()

            elif p["estado"] == "EN_PREPARACION":
                if st.button("🚀 Pasar a LISTO_OFERTAR", use_container_width=True, type="primary"):
                    _cambiar_estado(proyecto_id, "LISTO_OFERTAR", paquete=True)
                    st.success("✓ Paquete marcado como listo")
                    st.rerun()

            elif p["estado"] == "LISTO_OFERTAR":
                if st.button("📤 Marcar como OFERTADA", use_container_width=True, type="primary"):
                    _cambiar_estado(proyecto_id, "OFERTADA")
                    st.success("✓ Marcada como ofertada en MP")
                    st.rerun()

            elif p["estado"] == "OFERTADA":
                col_x, col_y = st.columns(2)
                if col_x.button("🏆 ADJUDICADA", use_container_width=True):
                    _cambiar_estado(proyecto_id, "ADJUDICADA")
                    st.success("¡Felicitaciones!")
                    st.rerun()
                if col_y.button("❌ RECHAZADA", use_container_width=True):
                    _cambiar_estado(proyecto_id, "RECHAZADA")
                    st.rerun()

        with col_b:
            st.markdown("**📦 Decisiones de oferta**")
            if p["escenario_elegido"]:
                st.success(f"✓ Escenario: **{p['escenario_elegido']}**")
                st.metric("Precio ofertado", formato_clp(p["precio_ofertado"]))
                if p["margen_pct"]:
                    st.caption(f"Margen: {p['margen_pct']:.1f}%")
            else:
                st.info("Aún no se ha elegido escenario de precio. Ve a la pestaña 💰 Inteligencia de Precios.")

        st.divider()

        # ============ GENERACIÓN DE PAQUETE ============
        st.markdown("##### 📦 Generación de paquete de postulación")

        col_g, col_v = st.columns(2)

        with col_g:
            if st.button("📄 Generar Word + Excel", use_container_width=True, type="primary"):
                with st.spinner("Generando documentos..."):
                    try:
                        from app.core.generador_paquete import generar_paquete_completo
                        resultado = generar_paquete_completo(proyecto_id)
                        st.success(f"✅ {resultado['n_archivos']} archivos generados")
                        st.session_state[f'pkg_{proyecto_id}'] = resultado
                    except Exception as e:
                        st.error(f"Error: {e}")

        with col_v:
            pkg = st.session_state.get(f'pkg_{proyecto_id}')
            if pkg:
                st.success(f"📂 {pkg['carpeta'].name}")
                for nombre, path in pkg['archivos'].items():
                    with open(path, 'rb') as f:
                        st.download_button(
                            f"⬇️ {path.name}",
                            data=f.read(),
                            file_name=path.name,
                            use_container_width=True,
                            key=f"dl_{proyecto_id}_{nombre}"
                        )

        st.divider()

        # ============ ANÁLISIS IA ============
        st.markdown("##### 🤖 Análisis estratégico con Claude")

        col_ia, col_resultado = st.columns([1, 2])

        with col_ia:
            if st.button("🧠 Analizar con IA", use_container_width=True):
                with st.spinner("Claude analizando..."):
                    try:
                        from app.core.analisis_ia import analizar_proyecto_con_ia
                        resultado_ia = analizar_proyecto_con_ia(proyecto_id)
                        st.session_state[f'ia_{proyecto_id}'] = resultado_ia
                    except Exception as e:
                        st.error(f"Error: {e}")

            # Histórico de análisis previos
            conn = get_connection()
            chats = conn.execute(
                "SELECT * FROM aidu_chat_ia WHERE proyecto_id=? AND rol='assistant' ORDER BY id DESC LIMIT 1",
                (proyecto_id,)
            ).fetchall()
            conn.close()

        with col_resultado:
            ia = st.session_state.get(f'ia_{proyecto_id}')
            if ia:
                if ia.get('error'):
                    st.error(f"⚠️ {ia['error']}")
                    from config.settings import IS_STREAMLIT_CLOUD as _IS_CLOUD
                    if _IS_CLOUD:
                        st.caption("Configura `ANTHROPIC_API_KEY` en Streamlit Cloud → Manage app → Settings → Secrets")
                    else:
                        st.caption("Configura tu API key en `~/AIDU_Op/config/secrets.env`")
                else:
                    st.markdown(ia['analisis'])
                    st.caption(
                        f"💰 ~${ia.get('costo_estimado_usd', 0):.4f} USD · "
                        f"{ia.get('tokens_in', 0) + ia.get('tokens_out', 0)} tokens"
                    )
            elif chats:
                st.markdown("**Análisis previo:**")
                st.markdown(chats[0]['contenido'])
            else:
                st.info("Click en 🧠 Analizar con IA para obtener análisis estratégico de Claude")

        st.divider()

    # ======================================
    # TAB: BITÁCORA
    # ======================================
    with tab_bitacora:
        from app.core.precalificacion import obtener_bitacora, registrar_evento
        
        st.markdown("##### 📜 Historial cronológico del proyecto")
        st.caption("Toda la trazabilidad: cambios de estado, decisiones, análisis IA, checklist. Útil para auditoría.")
        
        # Agregar nota manual
        with st.expander("➕ Agregar nota manual", expanded=False):
            nueva_nota = st.text_area(
                "Nota",
                placeholder="Ej: Llamé a la municipalidad, confirmaron que aceptan ofertas digitales...",
                key=f"nota_{p['id']}",
                height=80
            )
            if st.button("💾 Guardar nota", key=f"save_nota_{p['id']}"):
                if nueva_nota.strip():
                    registrar_evento(p["id"], "nota", nueva_nota.strip())
                    st.success("✅ Nota guardada")
                    st.rerun()
                else:
                    st.warning("La nota no puede estar vacía")
        
        st.divider()
        
        eventos = obtener_bitacora(p["id"], limit=200)
        
        if not eventos:
            st.info("📭 Sin eventos registrados aún. Las acciones que tomes en el sistema quedarán automáticamente registradas aquí.")
        else:
            # Iconos por tipo
            iconos = {
                "estado_cambio": "🔄",
                "paquete": "📦",
                "ia": "🤖",
                "nota": "📝",
                "checklist": "✅",
                "estimacion": "⏱️",
                "sistema": "⚙️",
            }
            
            colores = {
                "estado_cambio": "#1E40AF",
                "paquete": "#15803D",
                "ia": "#7C3AED",
                "nota": "#0891B2",
                "checklist": "#059669",
                "estimacion": "#D97706",
                "sistema": "#64748B",
            }
            
            st.caption(f"**{len(eventos)} eventos** · más reciente arriba")
            
            for ev in eventos:
                icono = iconos.get(ev["tipo"], "📌")
                color = colores.get(ev["tipo"], "#64748B")
                fecha = ev["fecha"][:16] if ev["fecha"] else "-"
                
                st.markdown(f"""
                <div style='display:flex; gap:10px; padding:8px 12px; border-left:3px solid {color}; background:#F8FAFC; margin-bottom:4px; border-radius:4px;'>
                    <div style='font-size:16px;'>{icono}</div>
                    <div style='flex:1;'>
                        <div style='font-size:13px; color:#1E293B;'>{ev["texto"]}</div>
                        <div style='font-size:11px; color:#94A3B8; margin-top:2px;'>
                            <span style='font-family:monospace;'>{fecha}</span> · 
                            <span style='color:{color};'>{ev["tipo"]}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)


# ============================================================
# HELPERS DE BD
# ============================================================
def _cambiar_estado(proyecto_id: int, nuevo_estado: str, paquete: bool = False):
    conn = get_connection()
    # Obtener estado anterior para registrar el cambio
    estado_anterior = conn.execute(
        "SELECT estado FROM aidu_proyectos WHERE id = ?", (proyecto_id,)
    ).fetchone()
    estado_anterior = estado_anterior["estado"] if estado_anterior else "?"
    
    if paquete:
        conn.execute(
            "UPDATE aidu_proyectos SET estado=?, paquete_generado=1, fecha_modificacion=datetime('now','localtime') WHERE id=?",
            (nuevo_estado, proyecto_id)
        )
    else:
        conn.execute(
            "UPDATE aidu_proyectos SET estado=?, fecha_modificacion=datetime('now','localtime') WHERE id=?",
            (nuevo_estado, proyecto_id)
        )
    conn.commit()
    conn.close()
    
    # Registrar en bitácora
    try:
        from app.core.precalificacion import registrar_evento
        registrar_evento(
            proyecto_id, "estado_cambio",
            f"Cambio de estado: {estado_anterior} → {nuevo_estado}"
        )
    except Exception:
        pass


def _set_escenario(proyecto_id: int, escenario: str, precio: int, margen: float, prob: int):
    conn = get_connection()
    conn.execute(
        """UPDATE aidu_proyectos SET
           escenario_elegido=?, precio_ofertado=?, margen_pct=?, probabilidad_estimada=?,
           fecha_modificacion=datetime('now','localtime')
           WHERE id=?""",
        (escenario, precio, margen, prob / 100, proyecto_id)
    )
    conn.commit()
    conn.close()


# ============================================================
# RUTEO PRINCIPAL: si hay proyecto seleccionado, mostrar detalle
# ============================================================
if st.session_state.view_proyecto_id is not None:
    render_detalle_proyecto(st.session_state.view_proyecto_id)
    st.stop()


# ============================================================
# HEADER PROFESIONAL
# ============================================================
estado_h = estado_actual()
n_licitaciones = estado_h.get("licitaciones_historicas", 0)

col_logo, col_status = st.columns([3, 1])

with col_logo:
    st.markdown(f"""
    <div style="display: flex; align-items: center; gap: 14px; padding-top: 4px;">
        <div class="aidu-logo">
            <span class="dot"></span>
            <span class="aidu-text">AIDU</span>
            <span class="op-text">Op</span>
        </div>
        <div style="height: 24px; width: 1px; background: #E2E8F0;"></div>
        <div>
            <div style="font-size: 13px; color: #334155; font-weight: 600; line-height: 1.2;">Sistema Comercial B2G</div>
            <div style="font-size: 11px; color: #94A3B8; line-height: 1.2;">v{get_version()} · Mercado Público Chile</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with col_status:
    if n_licitaciones > 0:
        st.markdown(f"""
        <div style="text-align: right; padding-top: 10px;">
            <div style="display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; background: rgba(21, 128, 61, 0.08); border-radius: 999px; border: 1px solid rgba(21, 128, 61, 0.2);">
                <span style="width: 6px; height: 6px; background: #15803D; border-radius: 50%; box-shadow: 0 0 8px #15803D;"></span>
                <span style="font-size: 12px; font-weight: 600; color: #15803D;">Sistema OK · {n_licitaciones:,} licitaciones</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown(
            "<div style='text-align:right; padding-top:10px;'><span style='display:inline-flex; align-items:center; gap:6px; padding:6px 14px; background:rgba(217, 119, 6, 0.08); border-radius:999px; border:1px solid rgba(217, 119, 6, 0.2); font-size:12px; color:#D97706; font-weight:600;'>⚠️ Sin datos · Configura ticket MP</span></div>",
            unsafe_allow_html=True
        )

st.divider()


# ============================================================
# TABS PRINCIPALES
# ============================================================

def _mostrar_error_tab(nombre_tab: str, error: Exception):
    """Muestra un error de pestaña de forma amigable sin crashear toda la app."""
    import traceback as _tb
    st.error(f"⚠️ Error al cargar la pestaña **{nombre_tab}**")
    with st.expander("Ver detalle técnico", expanded=False):
        st.code(f"{type(error).__name__}: {error}", language="text")
        st.caption("Si el error persiste, recarga la página o reporta este detalle.")
        st.code(_tb.format_exc(), language="python")


# ============================================================
# NAVEGACIÓN PRINCIPAL — Sidebar (v7 mejora UX)
# ============================================================

# CSS adicional para sidebar profesional
st.markdown("""
<style>
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FAFAFA 0%, #F5F5F5 100%);
    border-right: 1px solid #E5E7EB;
}
[data-testid="stSidebar"] .stRadio > label {
    font-size: 14px;
    padding: 10px 12px;
    border-radius: 8px;
    margin: 2px 0;
    transition: all 0.15s ease;
}
[data-testid="stSidebar"] .stRadio > label:hover {
    background: #F1F5F9;
}
.aidu-sidebar-header {
    padding: 16px 12px 8px;
    border-bottom: 1px solid #E5E7EB;
    margin-bottom: 16px;
}
.aidu-sidebar-stat {
    padding: 8px 12px;
    background: white;
    border-radius: 8px;
    border: 1px solid #E5E7EB;
    margin: 4px 0;
    font-size: 12px;
}
.aidu-sidebar-stat strong {
    color: #1E40AF;
    font-size: 16px;
}
</style>
""", unsafe_allow_html=True)

# Importar stats vigentes para el sidebar (lazy)
try:
    from app.core.descarga_diaria import stats_vigentes as _stats_vigentes_func
    _stats_vig = _stats_vigentes_func()
except Exception:
    _stats_vig = {"total_vigentes": 0, "publicadas_24h": 0, "cierran_proximos_3_dias": 0, "con_match_aidu": 0}

with st.sidebar:
    st.markdown("""
    <div class="aidu-sidebar-header">
        <div style="display:flex; align-items:center; gap:8px;">
            <span style="width:10px; height:10px; background:linear-gradient(135deg, #1E40AF 0%, #3B82F6 100%); border-radius:50%; box-shadow:0 0 12px rgba(59, 130, 246, 0.5);"></span>
            <div>
                <div style="font-size:16px; font-weight:700; color:#1E40AF; letter-spacing:-0.5px; line-height:1.2;">AIDU Op</div>
                <div style="font-size:10px; color:#94A3B8; line-height:1.2; margin-top:2px;">Sistema Comercial B2G</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    seccion = st.radio(
        "Navegación",
        ["🔥 Hoy", "📂 Cartera", "🎯 Oportunidades", "📊 Inteligencia", "⚙️ Configuración", "🛠️ Sistema"],
        label_visibility="collapsed",
        key="nav_principal",
    )
    
    st.divider()
    
    st.markdown("""
    <div style='font-size:11px; color:#64748B; font-weight:600; letter-spacing:0.5px; text-transform:uppercase; margin-bottom:8px;'>📡 Estado en vivo</div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="aidu-sidebar-stat">
        <span>🟢 Vigentes hoy</span>
        <strong>{_stats_vig['publicadas_24h']}</strong>
    </div>
    <div class="aidu-sidebar-stat">
        <span>🔴 Cierran ≤3d</span>
        <strong>{_stats_vig['cierran_proximos_3_dias']}</strong>
    </div>
    <div class="aidu-sidebar-stat">
        <span>🎯 Match AIDU</span>
        <strong>{_stats_vig['con_match_aidu']}</strong>
    </div>
    """, unsafe_allow_html=True)
    
    st.divider()
    
    ult_act = _stats_vig.get('ultima_actualizacion') or '—'
    if ult_act != '—':
        ult_act = ult_act[:16]  # Solo fecha + hora corta
    
    st.markdown(f"""
    <div style='font-size:10px; color:#94A3B8; padding:0 8px;'>
        <div>Última sync: <strong style='color:#475569;'>{ult_act}</strong></div>
        <div style='margin-top:6px;'><a href='https://github.com/ividiellagonzalez-ship-it/aidu-op' target='_blank' style='color:#3B82F6; text-decoration:none;'>📦 Ver código →</a></div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# CONTENIDO PRINCIPAL — según sección elegida
# ============================================================

# Booleanos para activar cada sección. Patrón más simple que st.tabs original.
tab_cartera = (seccion == "📂 Cartera")
tab_buscar = (seccion == "🎯 Oportunidades")
tab_intel = (seccion == "📊 Inteligencia")
tab_sistema = (seccion == "🛠️ Sistema")
tab_hoy = (seccion == "🔥 Hoy")
tab_config = (seccion == "⚙️ Configuración")


# ====================
# TAB 1: CARTERA
# ====================
# ============================================================
# TAB: 🔥 HOY (v7 — licitaciones publicadas en últimas 24h)
# ============================================================
if tab_hoy:
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:28px;">🔥 Lo nuevo de hoy</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">Licitaciones publicadas recientemente en Mercado Público que calzan con tu perfil AIDU</p>
    </div>
    """, unsafe_allow_html=True)
    
    try:
        from app.core.descarga_diaria import listar_vigentes, ejecutar_descarga, stats_vigentes
        
        col_a, col_b, col_c, col_d = st.columns(4)
        st_vig = stats_vigentes()
        col_a.metric("📡 Total vigentes", st_vig["total_vigentes"])
        col_b.metric("🟢 Últimas 24h", st_vig["publicadas_24h"])
        col_c.metric("🔴 Cierran ≤3 días", st_vig["cierran_proximos_3_dias"])
        col_d.metric("🎯 Match AIDU", st_vig["con_match_aidu"])
        
        st.divider()
        
        col_filt1, col_filt2, col_filt3, col_filt4 = st.columns([2, 2, 2, 1])
        f_region = col_filt1.selectbox("Región", ["Todas", "O'Higgins", "Metropolitana", "Maule", "Valparaíso"], key="hoy_reg")
        f_categoria = col_filt2.selectbox("Categoría AIDU", ["Todas", "CE-01", "CE-02", "CE-06", "GP-04"], key="hoy_cat")
        f_dias = col_filt3.number_input("Cierre máx (días)", min_value=0, max_value=60, value=15, key="hoy_dias")
        
        with col_filt4:
            st.caption("&nbsp;")
            if st.button("🔄 Sincronizar", use_container_width=True, help="Descarga licitaciones publicadas hoy"):
                with st.spinner("Descargando desde Mercado Público..."):
                    try:
                        resultado = ejecutar_descarga(dias_atras=2)
                        st.success(f"✅ {resultado['nuevas']} nuevas, {resultado['actualizadas']} actualizadas, {resultado['categorizadas_aidu']} categorizadas AIDU")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error en descarga: {e}")
        
        vigentes = listar_vigentes(
            region=f_region if f_region != "Todas" else None,
            categoria_aidu=f_categoria if f_categoria != "Todas" else None,
            dias_max_cierre=f_dias if f_dias > 0 else None,
            limit=50
        )
        
        if not vigentes:
            st.info("📭 Sin licitaciones vigentes con estos filtros.")
            st.markdown("""
            **Posibles causas:**
            - No se ha ejecutado la descarga diaria todavía
            - Los filtros son muy restrictivos
            - El ticket de Mercado Público no está configurado
            
            👉 Click "🔄 Sincronizar" para forzar una descarga manual
            """)
        else:
            st.caption(f"Mostrando {len(vigentes)} licitaciones vigentes")
            
            for v in vigentes:
                dias_cierre = v.get("dias_para_cierre")
                if dias_cierre is not None and dias_cierre <= 3:
                    border_color = "#DC2626"
                elif dias_cierre is not None and dias_cierre <= 7:
                    border_color = "#D97706"
                else:
                    border_color = "#10B981"
                
                cat_aidu = v.get("cod_servicio_aidu") or "Sin categoría"
                
                st.markdown(f"""
                <div style='border-left: 4px solid {border_color}; padding: 12px 16px; background: white; border-radius: 6px; margin-bottom: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);'>
                    <div style='display: flex; justify-content: space-between; align-items: start;'>
                        <div style='flex: 1;'>
                            <div style='font-weight: 600; font-size: 14px; color: #1E293B; margin-bottom: 4px;'>{v['nombre']}</div>
                            <div style='font-size: 12px; color: #64748B;'>
                                🏛️ {v['organismo'] or '—'} · 📍 {v['region'] or '—'} · 🎯 {cat_aidu}
                            </div>
                            <div style='font-size: 11px; color: #94A3B8; font-family: monospace; margin-top: 2px;'>
                                {v['codigo_externo']}
                            </div>
                        </div>
                        <div style='text-align: right; min-width: 140px;'>
                            <div style='font-weight: 700; color: #1E40AF; font-size: 16px;'>{formato_clp(v['monto_referencial'])}</div>
                            <div style='font-size: 11px; color: {border_color}; font-weight: 600; margin-top: 2px;'>
                                {f"⏰ {dias_cierre}d para cerrar" if dias_cierre is not None else "Sin fecha"}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    except Exception as e:
        from app.ui import streamlit_app  # noqa
        st.warning("⚠️ La función 'Hoy' requiere ejecutar la migración 002. Ve a Sistema → Aplicar migraciones.")
        with st.expander("Detalle técnico"):
            st.code(str(e))


# ============================================================
# TAB: ⚙️ CONFIGURACIÓN (v7 — eliminar hardcoded)
# ============================================================
if tab_config:
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:28px;">⚙️ Configuración</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">Personaliza tarifas, sweet spot, regiones y filtros — todo lo que antes estaba hardcoded</p>
    </div>
    """, unsafe_allow_html=True)
    
    try:
        from app.core.configuracion import obtener_config, actualizar_config, resetear_config
        
        cfg = obtener_config()
        
        cfg_tab1, cfg_tab2, cfg_tab3, cfg_tab4 = st.tabs([
            "💰 Economía", "🎯 Sweet Spot", "📍 Filtros", "📧 Notificaciones"
        ])
        
        with cfg_tab1:
            st.markdown("##### Tarifas y márgenes")
            col1, col2 = st.columns(2)
            tarifa = col1.number_input(
                "Tarifa hora (CLP)",
                min_value=0, max_value=500_000,
                value=int(cfg.tarifa_hora_clp), step=5000,
                help="Tu tarifa por hora. Default: 2 UF ≈ CLP 78.000"
            )
            overhead = col2.number_input(
                "Overhead (%)",
                min_value=0.0, max_value=50.0,
                value=float(cfg.overhead_pct), step=1.0,
                help="Costos indirectos sobre tarifa hora"
            )
            
            col3, col4 = st.columns(2)
            margen_obj = col3.number_input(
                "Margen objetivo (%)",
                min_value=0.0, max_value=100.0,
                value=float(cfg.margen_objetivo_pct), step=1.0
            )
            margen_min = col4.number_input(
                "Margen mínimo (%)",
                min_value=0.0, max_value=100.0,
                value=float(cfg.margen_minimo_pct), step=1.0,
                help="Por debajo de este margen, NO postular"
            )
            
            st.info(f"💡 Costo hora total con overhead: **{formato_clp(int(tarifa * (1 + overhead/100)))}**")
            
            if st.button("💾 Guardar economía", type="primary", key="save_econ"):
                actualizar_config({
                    "tarifa_hora_clp": int(tarifa),
                    "overhead_pct": overhead,
                    "margen_objetivo_pct": margen_obj,
                    "margen_minimo_pct": margen_min,
                })
                st.success("✅ Configuración guardada")
                st.rerun()
        
        with cfg_tab2:
            st.markdown("##### Rango de monto referencial óptimo")
            st.caption("Define qué montos están dentro de tu zona ideal de operación")
            
            col1, col2 = st.columns(2)
            ss_min = col1.number_input(
                "Sweet spot mín (CLP)",
                min_value=0, value=int(cfg.sweet_spot_min_clp), step=500_000
            )
            ss_max = col2.number_input(
                "Sweet spot máx (CLP)",
                min_value=0, value=int(cfg.sweet_spot_max_clp), step=500_000
            )
            
            col3, col4 = st.columns(2)
            ra_min = col3.number_input(
                "Aceptable mín (CLP)",
                min_value=0, value=int(cfg.rango_aceptable_min_clp), step=500_000
            )
            ra_max = col4.number_input(
                "Aceptable máx (CLP)",
                min_value=0, value=int(cfg.rango_aceptable_max_clp), step=500_000
            )
            
            st.info(f"📊 Sweet spot: **{formato_clp(ss_min)} - {formato_clp(ss_max)}**")
            
            if st.button("💾 Guardar sweet spot", type="primary", key="save_sweet"):
                actualizar_config({
                    "sweet_spot_min_clp": int(ss_min),
                    "sweet_spot_max_clp": int(ss_max),
                    "rango_aceptable_min_clp": int(ra_min),
                    "rango_aceptable_max_clp": int(ra_max),
                })
                st.success("✅ Sweet spot guardado")
                st.rerun()
        
        with cfg_tab3:
            st.markdown("##### Regiones y categorías objetivo")
            
            todas_regiones = ["Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo",
                              "Valparaíso", "Metropolitana", "O'Higgins", "Maule", "Ñuble", "Biobío",
                              "Araucanía", "Los Ríos", "Los Lagos", "Aysén", "Magallanes"]
            
            regiones = st.multiselect(
                "Regiones donde operas",
                options=todas_regiones,
                default=cfg.regiones_objetivo,
            )
            
            todas_categorias = ["CE-01", "CE-02", "CE-03", "CE-04", "CE-05", "CE-06",
                                "GP-01", "GP-02", "GP-03", "GP-04", "GP-05", "CAP-01"]
            
            categorias = st.multiselect(
                "Categorías AIDU activas",
                options=todas_categorias,
                default=cfg.categorias_objetivo,
            )
            
            st.markdown("##### Mandantes recurrentes")
            mandantes_text = st.text_area(
                "Uno por línea",
                value="\n".join(cfg.mandantes_recurrentes),
                height=120
            )
            mandantes_list = [m.strip() for m in mandantes_text.split("\n") if m.strip()]
            
            if st.button("💾 Guardar filtros", type="primary", key="save_filt"):
                actualizar_config({
                    "regiones_objetivo": regiones,
                    "categorias_objetivo": categorias,
                    "mandantes_recurrentes": mandantes_list,
                })
                st.success("✅ Filtros guardados")
                st.rerun()
        
        with cfg_tab4:
            st.markdown("##### Email y notificaciones")
            
            email_notif = st.text_input(
                "Email para notificaciones",
                value=cfg.email_notificaciones,
                placeholder="ignacio@aidu.cl"
            )
            
            col1, col2 = st.columns(2)
            notif_diario = col1.checkbox(
                "📧 Email diario 7am",
                value=cfg.notif_diario_habilitado,
                help="Resumen de licitaciones que cierran en próximos 5 días"
            )
            notif_semanal = col2.checkbox(
                "📊 Reporte semanal lunes",
                value=cfg.notif_semanal_habilitado,
                help="Top 5 oportunidades de la semana con análisis IA"
            )
            
            if st.button("💾 Guardar notificaciones", type="primary", key="save_notif"):
                actualizar_config({
                    "email_notificaciones": email_notif,
                    "notif_diario_habilitado": notif_diario,
                    "notif_semanal_habilitado": notif_semanal,
                })
                st.success("✅ Notificaciones guardadas")
                st.rerun()
        
        st.divider()
        with st.expander("⚠️ Zona peligrosa"):
            if st.button("🔄 Resetear toda la configuración a defaults", type="secondary"):
                resetear_config()
                st.warning("Configuración reseteada a defaults")
                st.rerun()
    
    except Exception as e:
        st.warning("⚠️ El módulo de configuración requiere migración 002.")
        with st.expander("Detalle técnico"):
            st.code(str(e))


if tab_cartera:
    st.markdown("""
    <div class="macro-flow">
        <div class="macro-step">1. 🔍 BUSCAR</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step" style="border:2px solid #1E40AF; color:#1E40AF; font-weight:700;">2. 📂 CARTERA</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">3. 🔬 ESTUDIAR</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">4. 🚀 OFERTAR</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">5. 📤 SUBIR A MP</div>
    </div>
    """, unsafe_allow_html=True)

    conn = get_connection()
    proyectos = conn.execute("""
        SELECT * FROM aidu_proyectos
        ORDER BY
            CASE estado
                WHEN 'LISTO_OFERTAR' THEN 1
                WHEN 'EN_PREPARACION' THEN 2
                WHEN 'ESTUDIO' THEN 3
                WHEN 'PROSPECTO' THEN 4
                ELSE 5
            END,
            fecha_cierre ASC
    """).fetchall()
    conn.close()

    estados_count = {}
    for p in proyectos:
        estados_count[p["estado"]] = estados_count.get(p["estado"], 0) + 1

    cols = st.columns(6)
    cols[0].metric("Total cartera", len(proyectos))
    cols[1].metric("Prospectos", estados_count.get("PROSPECTO", 0))
    cols[2].metric("En estudio", estados_count.get("ESTUDIO", 0))
    cols[3].metric("Preparación", estados_count.get("EN_PREPARACION", 0))
    cols[4].metric("Listo ofertar", estados_count.get("LISTO_OFERTAR", 0))
    cols[5].metric("Adjudicadas", estados_count.get("ADJUDICADA", 0))

    st.divider()

    if not proyectos:
        st.info("📂 Cartera vacía. Ve a **🎯 Oportunidades** y agrega licitaciones interesantes con el botón '+ Cartera'.")
    else:
        from app.core.match_score import calcular_match_score
        
        # Mapa de próxima acción según estado
        proxima_accion = {
            "PROSPECTO": ("🔬 Estudiar próximo", "ESTUDIO"),
            "ESTUDIO": ("📋 Pasar a Preparación", "EN_PREPARACION"),
            "EN_PREPARACION": ("🚀 Marcar Listo para Ofertar", "LISTO_OFERTAR"),
            "LISTO_OFERTAR": ("📤 Marcar como Ofertada", "OFERTADA"),
            "OFERTADA": ("✅ Marcar Adjudicada", "ADJUDICADA"),
        }
        
        for p in proyectos:
            with st.container(border=True):
                # Calcular match score on-the-fly
                lic_dict = {
                    "cod_servicio_aidu": p["cod_servicio_aidu"],
                    "confianza": 1.0,
                    "region": p["region"],
                    "monto_referencial": p["monto_referencial"],
                    "organismo": p["organismo"],
                    "fecha_publicacion": p.get("fecha_publicacion") if hasattr(p, "get") else (p["fecha_publicacion"] if "fecha_publicacion" in p.keys() else None),
                }
                try:
                    match = calcular_match_score(lic_dict)
                    score = match["score"]
                except Exception:
                    score = None

                # Badges color del score
                if score is not None:
                    if score >= 80:
                        s_color, s_bg = "#15803D", "#DCFCE7"
                    elif score >= 60:
                        s_color, s_bg = "#854F0B", "#FEF3C7"
                    else:
                        s_color, s_bg = "#64748B", "#F1F5F9"
                
                col1, col2, col3 = st.columns([3, 1, 1])

                badge_score = f"<span style='background:{s_bg}; color:{s_color}; font-size:11px; padding:2px 10px; border-radius:12px; font-weight:600; margin-right:6px;'>Match {score}</span>" if score is not None else ""

                col1.markdown(f"""
                {badge_score}<span class="estado-{p['estado']}">{p['estado']}</span>
                <span style='color:#94A3B8; font-family:monospace; font-size:11px; margin-left:8px;'>{p['codigo_externo']}</span>
                <br>
                <span style='font-size:14px; font-weight:600;'>{p['nombre']}</span>
                <br>
                <span style='color:#64748B; font-size:12px;'>
                    🏛️ {p['organismo']} · 📍 {p['region']} · 🎯 {p['cod_servicio_aidu']}
                </span>
                """, unsafe_allow_html=True)

                col2.metric("Monto ref.", formato_clp(p["monto_referencial"]))

                dias = calcular_dias_cierre(p["fecha_cierre"])
                if dias is not None:
                    col3.metric("Días cierre", f"{emoji_dias(dias)} {dias}")

                # Alerta si días al cierre crítico
                if dias is not None and dias <= 3 and p["estado"] not in ("OFERTADA", "ADJUDICADA", "RECHAZADA"):
                    st.warning(f"⚠️ ¡Cierra en {dias} día{'s' if dias != 1 else ''}! Acelera la preparación.")
                
                # 🆕 Indicadores de readiness (checklist + paquete)
                if p["estado"] in ("EN_PREPARACION", "LISTO_OFERTAR"):
                    try:
                        from app.core.precalificacion import progreso_checklist
                        prog_chk = progreso_checklist(p["id"])
                        
                        col_r1, col_r2, col_r3 = st.columns(3)
                        
                        # Checklist
                        if prog_chk["porcentaje"] < 50:
                            col_r1.markdown(f"<div style='padding:6px; background:#FEE2E2; border-radius:6px; font-size:12px; text-align:center;'>🔴 Checklist <strong>{prog_chk['porcentaje']}%</strong></div>", unsafe_allow_html=True)
                        elif prog_chk["porcentaje"] < 80:
                            col_r1.markdown(f"<div style='padding:6px; background:#FEF3C7; border-radius:6px; font-size:12px; text-align:center;'>🟡 Checklist <strong>{prog_chk['porcentaje']}%</strong></div>", unsafe_allow_html=True)
                        else:
                            col_r1.markdown(f"<div style='padding:6px; background:#DCFCE7; border-radius:6px; font-size:12px; text-align:center;'>🟢 Checklist <strong>{prog_chk['porcentaje']}%</strong></div>", unsafe_allow_html=True)
                        
                        # Paquete
                        paquete_ok = p["paquete_generado"] if "paquete_generado" in p.keys() else 0
                        if paquete_ok:
                            col_r2.markdown("<div style='padding:6px; background:#DCFCE7; border-radius:6px; font-size:12px; text-align:center;'>🟢 Paquete <strong>generado</strong></div>", unsafe_allow_html=True)
                        else:
                            col_r2.markdown("<div style='padding:6px; background:#FEE2E2; border-radius:6px; font-size:12px; text-align:center;'>🔴 Paquete <strong>pendiente</strong></div>", unsafe_allow_html=True)
                        
                        # Precio
                        precio_ok = p["precio_ofertado"] if "precio_ofertado" in p.keys() else None
                        if precio_ok:
                            col_r3.markdown(f"<div style='padding:6px; background:#DCFCE7; border-radius:6px; font-size:12px; text-align:center;'>🟢 Precio <strong>{formato_clp(precio_ok)}</strong></div>", unsafe_allow_html=True)
                        else:
                            col_r3.markdown("<div style='padding:6px; background:#FEF3C7; border-radius:6px; font-size:12px; text-align:center;'>🟡 Precio <strong>sin definir</strong></div>", unsafe_allow_html=True)
                    except Exception:
                        pass
                
                # Acciones: botón principal de próxima etapa + Ver detalle
                col_a, col_b, col_c = st.columns(3)
                
                accion = proxima_accion.get(p["estado"])
                if accion:
                    label, nuevo_estado = accion
                    if col_a.button(label, key=f"adv_{p['id']}", use_container_width=True, type="primary"):
                        _cambiar_estado(p["id"], nuevo_estado, paquete=(nuevo_estado == "LISTO_OFERTAR"))
                        st.rerun()
                elif p["estado"] == "ADJUDICADA":
                    col_a.success("🏆 Adjudicada")
                elif p["estado"] == "RECHAZADA":
                    col_a.error("❌ Rechazada")

                if col_c.button("👁️ Ver detalle", key=f"det_{p['id']}", use_container_width=True):
                    st.session_state.view_proyecto_id = p["id"]
                    st.rerun()


# ====================
# TAB 2: BUSCAR
# ====================
# TAB 2: OPORTUNIDADES (rediseñado)
# ====================
if tab_buscar:
    st.subheader("🎯 Oportunidades de mercado")
    st.caption("Licitaciones del histórico MP que calzan con tu perfil AIDU. Convierte las que te interesen a tu cartera.")

    from app.core.match_score import (
        listar_oportunidades, categorias_disponibles, regiones_disponibles,
        convertir_a_proyecto
    )
    
    # Cache de 60s para listas estáticas (categorías y regiones cambian raro)
    @st.cache_data(ttl=60)
    def _cached_categorias():
        return categorias_disponibles()
    
    @st.cache_data(ttl=60)
    def _cached_regiones():
        return regiones_disponibles()

    # ----- Filtros laterales en columnas -----
    col_filtros, col_resultados = st.columns([1, 3])

    with col_filtros:
        st.markdown("##### 🔧 Filtros")
        
        # 🆕 Presets rápidos
        st.caption("⚡ Presets rápidos")
        col_p1, col_p2 = st.columns(2)
        if col_p1.button("📍 Mi región", key="preset_region", use_container_width=True, help="Solo O'Higgins"):
            st.session_state["op_reg"] = next(
                (f"{r[0][:30]} ({r[1]})" for r in _cached_regiones() if "Higgins" in r[0]),
                "Todas"
            )
            st.rerun()
        if col_p2.button("💎 Sweet spot", key="preset_sweet", use_container_width=True, help="$3M - $15M"):
            st.session_state["op_min"] = 3
            st.session_state["op_max"] = 15
            st.rerun()
        
        col_p3, col_p4 = st.columns(2)
        if col_p3.button("🏗️ Estructural", key="preset_estr", use_container_width=True, help="Solo CE-XX"):
            st.session_state["op_busqueda"] = "estructural"
            st.rerun()
        if col_p4.button("🔄 Limpiar", key="preset_clear", use_container_width=True):
            for k in ["op_busqueda", "op_min", "op_max"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
        
        st.divider()

        # 🆕 Búsqueda libre por palabra clave
        busqueda = st.text_input(
            "🔍 Buscar",
            placeholder="ej: estructural, escuela, Machalí...",
            key="op_busqueda",
            help="Busca en nombre, descripción y organismo"
        )

        # Categoría AIDU
        cats = _cached_categorias()
        cat_options = ["Todas"] + [f"{c[0]} ({c[1]})" for c in cats]
        cat_sel_label = st.selectbox("Categoría AIDU", cat_options, key="op_cat")
        cat_sel = "Todas" if cat_sel_label == "Todas" else cat_sel_label.split(" ")[0]

        # Región
        regs = _cached_regiones()
        reg_options = ["Todas"] + [f"{r[0][:30]} ({r[1]})" for r in regs]
        reg_sel_label = st.selectbox("Región", reg_options, key="op_reg")
        reg_sel = "Todas" if reg_sel_label == "Todas" else reg_sel_label.split(" (")[0]

        # Monto - SIN restricción por defecto (tú decides)
        st.caption("Monto referencial (M CLP) · 0 = sin filtro")
        col_min, col_max = st.columns(2)
        monto_min_m = col_min.number_input(
            "Min", min_value=0, max_value=500, value=0, step=1,
            label_visibility="collapsed", key="op_min",
            help="0 = sin mínimo"
        )
        monto_max_m = col_max.number_input(
            "Max", min_value=0, max_value=500, value=0, step=1,
            label_visibility="collapsed", key="op_max",
            help="0 = sin máximo"
        )

        # Match score mínimo
        score_min = st.slider("Match Score mín.", 0, 100, 50, 5, key="op_score")

        # Orden
        orden_label = st.selectbox(
            "Ordenar por",
            ["Match Score (alto→bajo)", "Monto (mayor)", "Fecha (más reciente)"],
            key="op_orden"
        )
        orden_map = {
            "Match Score (alto→bajo)": "score_desc",
            "Monto (mayor)": "monto_desc",
            "Fecha (más reciente)": "fecha_desc",
        }

        # Solo no-en-cartera
        solo_nuevas = st.checkbox(
            "Solo no-en-cartera", value=True, key="op_no_cart",
            help="Excluye licitaciones que ya tienes como proyecto AIDU"
        )

    # ----- Resultados -----
    with col_resultados:
        # Llamada DEFENSIVA: si match_score.py no soporta busqueda_libre,
        # hacemos el filtro en Python después
        kwargs_op = dict(
            filtro_categoria=cat_sel,
            filtro_region=reg_sel,
            monto_min=monto_min_m * 1_000_000 if monto_min_m > 0 else None,
            monto_max=monto_max_m * 1_000_000 if monto_max_m > 0 else None,
            score_min=score_min,
            solo_no_en_cartera=solo_nuevas,
            orden=orden_map[orden_label],
            limit=100
        )
        
        # Intentar pasar busqueda_libre si la función la soporta
        import inspect
        try:
            sig = inspect.signature(listar_oportunidades)
            soporta_busqueda = "busqueda_libre" in sig.parameters
        except Exception:
            soporta_busqueda = False
        
        if soporta_busqueda:
            kwargs_op["busqueda_libre"] = busqueda
            oportunidades = listar_oportunidades(**kwargs_op)
        else:
            # Fallback: filtrar en Python si el backend no soporta búsqueda libre
            oportunidades = listar_oportunidades(**kwargs_op)
            if busqueda and busqueda.strip():
                term = busqueda.strip().lower()
                oportunidades = [
                    op for op in oportunidades
                    if term in (op.get("nombre", "") or "").lower()
                    or term in (op.get("descripcion", "") or "").lower()
                    or term in (op.get("organismo", "") or "").lower()
                ]

        if not oportunidades:
            st.info("📭 Sin oportunidades con estos filtros. Prueba poner Monto Min/Max en 0 (sin filtro) o bajar el Match Score mínimo.")
        else:
            # Contador del universo total
            from app.core.match_score import listar_oportunidades as _lis_all
            try:
                total_universo = len(_lis_all(score_min=0, monto_min=None, monto_max=None, solo_no_en_cartera=solo_nuevas, limit=2000))
            except Exception:
                total_universo = len(oportunidades)
            
            st.markdown(
                f"**{len(oportunidades)} oportunidades** mostradas "
                f"<span style='color:#94A3B8; font-size:12px;'>de {total_universo} disponibles · ordenadas por {orden_label.lower()}</span>",
                unsafe_allow_html=True
            )

            # ========================================
            # ANÁLISIS IA MASIVO
            # ========================================
            with st.container(border=True):
                col_ia_left, col_ia_right = st.columns([3, 1])
                with col_ia_left:
                    st.markdown("##### 🤖 Análisis IA Masivo")
                    n_a_analizar = min(20, len(oportunidades))
                    st.caption(
                        f"Claude analiza las **top {n_a_analizar} oportunidades** y te dice las 5 más prometedoras. "
                        f"Costo estimado: ~$0.05 USD · Tiempo: ~30 segundos"
                    )
                with col_ia_right:
                    st.write("")
                    if st.button(
                        f"🤖 Analizar top {n_a_analizar}",
                        use_container_width=True,
                        type="primary",
                        key="btn_ia_masivo"
                    ):
                        with st.spinner(f"Claude analizando {n_a_analizar} licitaciones..."):
                            from app.core.analisis_masivo import analisis_masivo
                            resultado = analisis_masivo(
                                oportunidades[:n_a_analizar],
                                top_n=5
                            )
                            st.session_state["ia_masivo_resultado"] = resultado

                # Mostrar resultado si existe
                resultado_ia = st.session_state.get("ia_masivo_resultado")
                if resultado_ia:
                    if resultado_ia.get("error"):
                        st.error(f"⚠️ {resultado_ia['error']}")
                        if resultado_ia.get("raw"):
                            with st.expander("Ver respuesta cruda de Claude"):
                                st.code(resultado_ia["raw"])
                    else:
                        st.success(
                            f"✅ Analizadas {resultado_ia['n_analizadas']} licitaciones · "
                            f"Costo: ${resultado_ia['costo_usd']} USD · "
                            f"Tokens: {resultado_ia['tokens_in']}+{resultado_ia['tokens_out']}"
                        )
                        
                        if resultado_ia.get("resumen_ejecutivo"):
                            st.info(f"📝 **Resumen:** {resultado_ia['resumen_ejecutivo']}")
                        
                        st.markdown("###### 🏆 Top recomendaciones de Claude:")
                        
                        for i, item in enumerate(resultado_ia.get("top", []), 1):
                            veredicto = item.get("veredicto", "EVALUAR")
                            riesgo = item.get("riesgo", "MEDIO")
                            margen = item.get("margen_estimado_pct", 0)
                            
                            # Colores según veredicto
                            if veredicto == "POSTULAR":
                                v_color = "#15803D"
                                v_bg = "#DCFCE7"
                            elif veredicto == "DESCARTAR":
                                v_color = "#DC2626"
                                v_bg = "#FEE2E2"
                            else:
                                v_color = "#854F0B"
                                v_bg = "#FEF3C7"
                            
                            # Riesgo
                            r_emoji = "🟢" if riesgo == "BAJO" else "🟡" if riesgo == "MEDIO" else "🔴"
                            
                            st.markdown(f"""
                            <div style='background:#FFFFFF; border:0.5px solid #CBD5E1; border-left:3px solid {v_color}; border-radius:6px; padding:10px 14px; margin-bottom:6px;'>
                                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;'>
                                    <div>
                                        <span style='font-size:13px; font-weight:600;'>#{i} · {item.get('nombre', '')[:80]}</span>
                                        <span style='color:#94A3B8; font-family:monospace; font-size:11px; margin-left:8px;'>{item.get('codigo', '')}</span>
                                    </div>
                                    <div>
                                        <span style='background:{v_bg}; color:{v_color}; font-size:11px; padding:2px 10px; border-radius:12px; font-weight:600;'>{veredicto}</span>
                                        <span style='font-size:11px; margin-left:6px;'>{r_emoji} Riesgo {riesgo.lower()}</span>
                                        <span style='font-size:11px; margin-left:6px; color:#1E40AF; font-weight:600;'>Margen ~{margen}%</span>
                                    </div>
                                </div>
                                <div style='font-size:12px; color:#475569;'>{item.get('razon_principal', '')}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        if st.button("🗑️ Limpiar análisis", key="btn_ia_clear"):
                            del st.session_state["ia_masivo_resultado"]
                            st.rerun()

            st.divider()

            for idx, op in enumerate(oportunidades):
                m = op["match"]
                score = m["score"]
                desg = m["desglose"]

                # Color del score
                if score >= 80:
                    score_color = "#15803D"  # verde
                    score_bg = "#DCFCE7"
                elif score >= 60:
                    score_color = "#854F0B"  # ámbar
                    score_bg = "#FEF3C7"
                else:
                    score_color = "#64748B"  # gris
                    score_bg = "#F1F5F9"

                with st.container(border=True):
                    col_main, col_money, col_action = st.columns([3.5, 1.5, 1])

                    # Bloque principal
                    with col_main:
                        st.markdown(f"""
                        <div style='display:flex; gap:6px; align-items:center; margin-bottom:4px;'>
                            <span style='background:{score_bg}; color:{score_color}; font-size:11px; padding:2px 10px; border-radius:12px; font-weight:600;'>Match {score}</span>
                            <span style='background:#E0F2FE; color:#0C4A6E; font-size:11px; padding:2px 8px; border-radius:12px;'>{op.get('cod_servicio_aidu') or 'Sin cat.'}</span>
                            <span style='color:#94A3B8; font-family:monospace; font-size:11px;'>{op['codigo_externo']}</span>
                        </div>
                        <div style='font-size:14px; font-weight:600; color:#1E293B; margin-bottom:2px;'>{op['nombre'][:120]}</div>
                        <div style='font-size:12px; color:#64748B;'>🏛️ {op.get('organismo') or '-'} · 📍 {op.get('region') or '-'}</div>
                        <div style='font-size:12px; color:#475569; margin-top:6px; line-height:1.4; padding:6px 8px; background:#F8FAFC; border-left:2px solid #CBD5E1; border-radius:3px;'>
                            {(op.get('descripcion') or 'Sin descripción disponible. Revisa las bases en Mercado Público.')[:280]}{'…' if (op.get('descripcion') or '') and len(op.get('descripcion') or '') > 280 else ''}
                        </div>
                        <div style='font-size:11px; color:#94A3B8; margin-top:6px;'>
                            🎯 Categoría: {desg['categoria'][1]} · 📍 Región: {desg['region'][1]} · 💰 Monto: {desg['monto'][1]} · 🏢 Mandante: {desg['mandante'][1]}
                        </div>
                        """, unsafe_allow_html=True)

                    # Bloque monto
                    with col_money:
                        if op.get("monto_referencial"):
                            st.markdown(f"""
                            <div style='text-align:right;'>
                                <div style='font-size:11px; color:#64748B;'>Referencial</div>
                                <div style='font-size:16px; font-weight:600; color:#1E40AF;'>{formato_clp(op['monto_referencial'])}</div>
                            </div>
                            """, unsafe_allow_html=True)
                        if op.get("monto_adjudicado") and op.get("monto_referencial"):
                            desc = ((op["monto_adjudicado"] - op["monto_referencial"]) / op["monto_referencial"]) * 100
                            color_desc = "#DC2626" if desc < -5 else "#15803D"
                            st.markdown(f"""
                            <div style='text-align:right; margin-top:4px;'>
                                <div style='font-size:11px; color:#64748B;'>Adjudicado</div>
                                <div style='font-size:13px; color:{color_desc};'>{formato_clp(op['monto_adjudicado'])} ({desc:+.1f}%)</div>
                            </div>
                            """, unsafe_allow_html=True)

                    # Bloque acción
                    with col_action:
                        st.write("")  # spacer
                        if st.button(
                            "+ Cartera",
                            key=f"add_cart_{idx}_{op['codigo_externo']}",
                            use_container_width=True,
                            help="Convierte esta oportunidad en proyecto AIDU (estado PROSPECTO)"
                        ):
                            try:
                                pid = convertir_a_proyecto(op["codigo_externo"])
                                st.success(f"✅ Agregado a cartera (proyecto #{pid})")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                        
                        # Link directo a Mercado Público (las bases técnicas reales)
                        mp_url = f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={op['codigo_externo']}"
                        st.markdown(
                            f"<a href='{mp_url}' target='_blank' style='display:block; text-align:center; font-size:11px; color:#1E40AF; text-decoration:none; padding:4px 0; margin-top:4px; border:0.5px solid #CBD5E1; border-radius:6px;'>🔗 Ver en MP</a>",
                            unsafe_allow_html=True
                        )


# ====================
# TAB 3: INTELIGENCIA
# ====================
if tab_intel:
    st.subheader("📊 Inteligencia de mercado por categoría AIDU")

    conn = get_connection()
    servicios = conn.execute("""
        SELECT s.cod_servicio, s.nombre, COUNT(c.codigo_externo) as n
        FROM aidu_servicios_keywords s
        LEFT JOIN mp_categorizacion_aidu c ON c.cod_servicio_aidu = s.cod_servicio
        GROUP BY s.cod_servicio
        ORDER BY n DESC
    """).fetchall()
    conn.close()

    cod_sel = st.selectbox(
        "Categoría AIDU",
        options=[s["cod_servicio"] for s in servicios],
        format_func=lambda x: f"{x} · {next(s['nombre'] for s in servicios if s['cod_servicio']==x)} ({next(s['n'] for s in servicios if s['cod_servicio']==x)} licit.)"
    )

    if cod_sel:
        stats = obtener_estadisticas_categoria(cod_sel)
        if stats["n_total"]:
            cols = st.columns(4)
            cols[0].metric("Licitaciones", stats["n_total"])
            cols[1].metric("Descuento P25", f"{stats['descuento_p25']:.1f}%")
            cols[2].metric("Descuento mediana", f"{stats['descuento_mediana']:.1f}%")
            cols[3].metric("Descuento P75", f"{stats['descuento_p75']:.1f}%")

            if stats["competidores_recurrentes"]:
                st.markdown("##### 🥇 Competidores recurrentes")
                for c in stats["competidores_recurrentes"]:
                    st.markdown(f"- **{c['nombre']}** · {c['n_adj']} adjudicaciones")

            comparables = licitaciones_similares(cod_sel, limit=10)
            if comparables:
                st.markdown("##### 📚 Top 10 licitaciones")
                for r in comparables:
                    desc = r["descuento_pct"]
                    desc_str = f" · Δ {desc:+.1f}%" if desc else ""
                    st.markdown(
                        f"<div style='padding:8px 12px;margin-bottom:6px;background:#F8FAFC;border-radius:6px;border-left:3px solid #1E40AF;'>"
                        f"<div style='font-size:13px;font-weight:600;color:#1E40AF;'>{r['nombre']}</div>"
                        f"<div style='font-size:11px;color:#64748B;'>🏛️ {r['organismo'] or '-'} · {formato_clp(r['monto_adjudicado'])} adjudicado{desc_str} · Match: {r['similarity']:.0f}%</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
        else:
            st.info(f"Sin datos para {cod_sel}.")


# ====================
# TAB 4: SISTEMA
# ====================
if tab_sistema:
    st.subheader("⚙️ Estado del sistema")

    estado = estado_actual()
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("##### 📥 Histórico Mercado Público")
        st.metric("Licitaciones indexadas", f"{estado['licitaciones_historicas']:,}")
        st.metric("Categorizadas AIDU", f"{estado['categorizadas_aidu']:,}")
        if estado["backfill_completado"]:
            st.success("✅ Backfill 24m completado")
        else:
            st.warning("⚠️ Backfill 24m pendiente")
        st.caption(f"Última ingesta: {estado['ultima_ingesta'] or 'Nunca'}")

    with col2:
        st.markdown("##### 📂 Cartera AIDU Op")
        st.metric("Proyectos", f"{estado['proyectos_cartera']:,}")
        st.metric("Total ingestas", f"{estado['ingestas_ejecutadas']:,}")
        st.caption(f"Versión: {get_version()}")
        st.caption(f"Datos en: {AIDU_HOME}")

    st.divider()
    st.markdown("##### 📥 Descargar datos REALES de Mercado Público")
    
    # Mensaje según contexto (cloud o local)
    from config.settings import IS_STREAMLIT_CLOUD, get_mp_ticket
    if IS_STREAMLIT_CLOUD:
        st.caption("Requiere ticket configurado en Streamlit Cloud → Settings → Secrets → `MP_TICKET`")
    else:
        st.caption("Requiere ticket configurado en `~/AIDU_Op/config/secrets.env`")

    col_dias, col_btn = st.columns([1, 1])

    with col_dias:
        dias_descarga = st.number_input(
            "Días a descargar",
            min_value=1, max_value=365, value=14, step=7,
            help="MVP recomendado: 14 días (~30 min). Más días = más datos pero más lento."
        )

    with col_btn:
        st.write("")  # spacer
        st.write("")  # spacer
        if st.button("🚀 Descargar ahora", use_container_width=True, type="primary"):
            mp_ticket = get_mp_ticket()
            if not mp_ticket or "tu-ticket" in mp_ticket:
                if IS_STREAMLIT_CLOUD:
                    st.error("⚠️ Configura `MP_TICKET` en Streamlit Cloud → Manage app → Settings → Secrets")
                else:
                    st.error("⚠️ Configura tu MP_TICKET en `~/AIDU_Op/config/secrets.env` primero")
            else:
                with st.spinner(f"Descargando últimos {dias_descarga} días..."):
                    try:
                        from app.core.backfill import ejecutar_backfill_dias
                        result = ejecutar_backfill_dias(dias=dias_descarga)
                        st.success(
                            f"✅ Descargadas {result['total_descargadas']} licitaciones · "
                            f"{result['nuevas']} nuevas · {result['duracion_minutos']} min"
                        )
                    except Exception as e:
                        st.error(f"Error: {e}")

    st.divider()
    st.markdown("##### 🛠️ Acciones rápidas")

    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("🌱 Cargar datos DEMO", use_container_width=True):
            from app.core.seed_demo import seed_demo
            seed_demo(con_cartera=True)
            st.success("✅ Datos demo cargados")
            st.rerun()

    with col_b:
        if st.button("💾 Backup manual", use_container_width=True):
            from app.db.migrator import backup_database
            path = backup_database()
            if path:
                st.success(f"✅ {path.name}")
            else:
                st.info("No hay BD aún")

    with col_c:
        if st.button("🧹 Limpiar demo", use_container_width=True):
            from app.core.seed_demo import clean_demo
            clean_demo()
            st.success("✅ Eliminado")
            st.rerun()

    st.divider()
    st.markdown("##### 📋 Migraciones aplicadas")
    conn = get_connection()
    migs = conn.execute("SELECT * FROM _migrations ORDER BY id").fetchall()
    conn.close()
    for m in migs:
        st.markdown(
            f"✅ **{m['filename']}** · _{m['description']}_  \n"
            f"<span style='color:#94A3B8; font-size:11px;'>Aplicada: {m['applied_at']}</span>",
            unsafe_allow_html=True
        )


# Footer
st.divider()
st.caption(f"AIDU Op v{get_version()} · Datos en {AIDU_HOME} · Construido para Ignacio Vidiella")
