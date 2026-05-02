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
   AIDU OP · DESIGN SYSTEM v3.0 — World-class
   ============================================================ */

/* Tipografía global - Inter via Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
    /* ========================================================
       AIDU CORPORATE COLOR SYSTEM
       
       Color primario: Azul cobalto profundo (confianza + profesionalismo)
       Color secundario: Violeta corporativo (línea Gestión, diferenciador)
       Color de acento: Cyan eléctrico (highlights, micro-interacciones)
       Neutros: Slate (modernos, legibles, no fríos como blue-gray)
       ======================================================== */
    
    /* === Marca AIDU (azul cobalto, identidad principal) === */
    --aidu-brand:        #1D4ED8;   /* azul corporativo principal */
    --aidu-brand-light:  #3B82F6;   /* hover, links activos */
    --aidu-brand-dark:   #1E3A8A;   /* títulos, énfasis */
    --aidu-brand-50:     #EFF6FF;   /* backgrounds suaves */
    --aidu-brand-100:    #DBEAFE;   /* badges info */
    --aidu-brand-200:    #BFDBFE;   /* dividers azules */
    
    /* === Compatibilidad con código existente (alias) === */
    --aidu-blue:         var(--aidu-brand);
    --aidu-blue-light:   var(--aidu-brand-light);
    --aidu-blue-dark:    var(--aidu-brand-dark);
    --aidu-blue-50:      var(--aidu-brand-50);
    --aidu-blue-100:     var(--aidu-brand-100);
    
    /* === Línea Gestión (violeta corporativo, diferenciador) === */
    --aidu-purple:       #7C3AED;   /* GP-XX, gestión */
    --aidu-purple-light: #A78BFA;
    --aidu-purple-50:    #F5F3FF;
    --aidu-purple-100:   #EDE9FE;
    
    /* === Línea Estructural (azul cobalto, base) === */
    --aidu-structural:        var(--aidu-brand);
    --aidu-structural-50:     var(--aidu-brand-50);
    --aidu-structural-100:    var(--aidu-brand-100);
    
    /* === Acento eléctrico (cyan, para destacar) === */
    --aidu-accent:       #06B6D4;
    --aidu-accent-50:    #ECFEFF;
    --aidu-accent-100:   #CFFAFE;
    
    /* === Estados semánticos === */
    --aidu-success:      #059669;   /* verde más vibrante */
    --aidu-success-50:   #ECFDF5;
    --aidu-success-bg:   #D1FAE5;
    --aidu-warning:      #D97706;
    --aidu-warning-50:   #FFFBEB;
    --aidu-warning-bg:   #FEF3C7;
    --aidu-danger:       #DC2626;
    --aidu-danger-50:    #FEF2F2;
    --aidu-danger-bg:    #FEE2E2;
    
    /* === Neutros Slate (modernos, legibles) === */
    --aidu-gray-50:      #F8FAFC;
    --aidu-gray-100:     #F1F5F9;
    --aidu-gray-200:     #E2E8F0;
    --aidu-gray-300:     #CBD5E1;
    --aidu-gray-400:     #94A3B8;
    --aidu-gray-500:     #64748B;
    --aidu-gray-600:     #475569;
    --aidu-gray-700:     #334155;
    --aidu-gray-800:     #1E293B;
    --aidu-gray-900:     #0F172A;
    
    /* === Sombras refinadas (sutiles, nivel premium) === */
    --shadow-xs:    0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-sm:    0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-md:    0 4px 12px rgba(15, 23, 42, 0.08), 0 2px 4px rgba(15, 23, 42, 0.04);
    --shadow-lg:    0 10px 25px rgba(15, 23, 42, 0.12), 0 4px 8px rgba(15, 23, 42, 0.06);
    --shadow-xl:    0 20px 40px rgba(15, 23, 42, 0.15), 0 10px 20px rgba(15, 23, 42, 0.08);
    --shadow-glow:  0 0 0 3px rgba(29, 78, 216, 0.15);
    --shadow-glow-purple: 0 0 0 3px rgba(124, 58, 237, 0.15);
    
    /* === Radio === */
    --radius-sm: 6px;
    --radius-md: 10px;
    --radius-lg: 14px;
    --radius-xl: 20px;
    
    --transition-fast: 150ms cubic-bezier(0.4, 0, 0.2, 1);
    --transition-base: 250ms cubic-bezier(0.4, 0, 0.2, 1);
    --transition-slow: 400ms cubic-bezier(0.4, 0, 0.2, 1);
}

/* ============ Animaciones globales ============ */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
@keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(59, 130, 246, 0.4); }
    50% { box-shadow: 0 0 0 8px rgba(59, 130, 246, 0); }
}
@keyframes shimmer {
    0% { background-position: -200% 0; }
    100% { background-position: 200% 0; }
}
@keyframes slideInLeft {
    from { opacity: 0; transform: translateX(-12px); }
    to { opacity: 1; transform: translateX(0); }
}

/* ============ Aplicar Inter a toda la app ============ */
html, body, [class*="st-"], [class*="css-"], div, p, span, button, label, input {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}
code, pre, [class*="monospace"] {
    font-family: 'JetBrains Mono', 'Menlo', monospace !important;
}

/* Smooth scroll global */
html { scroll-behavior: smooth; }

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
    animation: pulse 2s ease-in-out infinite;
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

/* ============ Métricas profesionales con animación ============ */
div[data-testid="stMetricValue"] {
    font-weight: 800 !important;
    color: var(--aidu-blue) !important;
    font-size: 28px !important;
    letter-spacing: -0.025em;
    animation: fadeInUp 400ms ease-out;
}
div[data-testid="stMetricLabel"] {
    font-size: 11px !important;
    color: var(--aidu-gray-500) !important;
    font-weight: 700 !important;
    text-transform: uppercase;
    letter-spacing: 0.8px;
}
div[data-testid="stMetricDelta"] {
    font-size: 12px !important;
    font-weight: 600;
}

/* Bloque metric con hover */
div[data-testid="stMetric"] {
    background: white;
    padding: 16px;
    border-radius: var(--radius-md);
    border: 1px solid var(--aidu-gray-200);
    transition: all var(--transition-base);
    box-shadow: var(--shadow-xs);
}
div[data-testid="stMetric"]:hover {
    border-color: var(--aidu-blue-light);
    box-shadow: var(--shadow-md);
    transform: translateY(-1px);
}

/* ============ Botones ============ */
.stButton > button {
    border-radius: var(--radius-md);
    font-weight: 600;
    transition: all var(--transition-fast);
    font-size: 13px;
    border: 1px solid var(--aidu-gray-200);
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: var(--shadow-sm);
    border-color: var(--aidu-blue-light);
}
.stButton > button:active {
    transform: translateY(0);
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--aidu-blue) 0%, var(--aidu-blue-light) 100%);
    border: none;
    color: white !important;
    box-shadow: 0 4px 12px rgba(30, 64, 175, 0.25);
    font-weight: 600;
}
.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(30, 64, 175, 0.35);
}

/* Download button */
.stDownloadButton > button {
    background: linear-gradient(135deg, var(--aidu-success) 0%, #16A34A 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: var(--radius-md) !important;
    font-weight: 600 !important;
}

/* ============ Inputs ============ */
.stTextInput input,
.stNumberInput input,
.stSelectbox > div > div,
.stTextArea textarea {
    border-radius: var(--radius-sm) !important;
    border-color: var(--aidu-gray-200) !important;
    transition: all var(--transition-fast);
}
.stTextInput input:focus,
.stNumberInput input:focus,
.stTextArea textarea:focus {
    border-color: var(--aidu-blue) !important;
    box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1) !important;
}

/* ============ Estados con tags ============ */
.estado-tag, [class^="estado-"] {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.4px;
    text-transform: uppercase;
}
.estado-EN_CARTERA { background: #F1F5F9; color: #475569; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-EN_ESTUDIO { background: #CFFAFE; color: #0E7490; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-EN_ESTUDIO { background: #DBEAFE; color: #1E40AF; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-EN_OFERTA { background: #FED7AA; color: #9A3412; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-LISTO_SUBIR { background: #E9D5FF; color: #6B21A8; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-ADJUDICADO { background: #BBF7D0; color: #14532D; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-PERDIDO { background: #FEE2E2; color: #7F1D1D; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-DESCARTADO { background: #F1F5F9; color: #475569; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }

/* ============ Macro Flow ============ */
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
    animation: fadeIn 400ms ease-out;
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
    transition: all var(--transition-base);
}
.macro-arrow {
    color: var(--aidu-gray-300);
    font-weight: 700;
    font-size: 14px;
    animation: pulse 2s infinite;
}

/* ============ Tarjetas (la estrella del show) ============ */
.aidu-card {
    background: white;
    border: 1px solid var(--aidu-gray-200);
    border-radius: var(--radius-md);
    padding: 16px 20px;
    margin-bottom: 12px;
    box-shadow: var(--shadow-xs);
    transition: all var(--transition-base);
    animation: fadeInUp 400ms ease-out;
    position: relative;
    overflow: hidden;
}
.aidu-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0;
    width: 100%;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(59, 130, 246, 0.3), transparent);
    opacity: 0;
    transition: opacity var(--transition-base);
}
.aidu-card:hover {
    border-color: var(--aidu-blue-light);
    box-shadow: var(--shadow-md);
    transform: translateY(-2px);
}
.aidu-card:hover::before {
    opacity: 1;
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

/* ============ Sidebar premium ============ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FCFCFD 0%, #F5F7FA 100%);
    border-right: 1px solid var(--aidu-gray-200);
}
[data-testid="stSidebar"] > div:first-child {
    padding-top: 8px;
}

/* Items del radio en sidebar */
[data-testid="stSidebar"] [data-baseweb="radio"] {
    margin: 0 !important;
}
[data-testid="stSidebar"] [data-baseweb="radio"] label {
    display: flex;
    align-items: center;
    padding: 9px 14px !important;
    border-radius: var(--radius-md);
    margin: 2px 0 !important;
    font-size: 13.5px !important;
    font-weight: 500 !important;
    color: var(--aidu-gray-700) !important;
    cursor: pointer;
    transition: all var(--transition-fast);
    border: 1px solid transparent;
}
[data-testid="stSidebar"] [data-baseweb="radio"] label:hover {
    background: rgba(30, 64, 175, 0.06);
    color: var(--aidu-blue) !important;
    transform: translateX(2px);
}
[data-testid="stSidebar"] [data-baseweb="radio"] label[aria-checked="true"] {
    background: linear-gradient(90deg, rgba(30, 64, 175, 0.10) 0%, rgba(30, 64, 175, 0.04) 100%) !important;
    border-left: 3px solid var(--aidu-blue) !important;
    color: var(--aidu-blue) !important;
    font-weight: 600 !important;
    box-shadow: var(--shadow-xs);
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
    transition: all var(--transition-fast);
}
.aidu-sidebar-stat:hover {
    border-color: var(--aidu-blue-light);
    box-shadow: var(--shadow-xs);
}
.aidu-sidebar-stat strong {
    color: var(--aidu-blue);
    font-size: 18px;
    font-weight: 700;
}

/* ============ Hero sections ============ */
.aidu-hero {
    padding: 8px 0 16px;
    border-bottom: 1px solid var(--aidu-gray-200);
    margin-bottom: 24px;
    animation: fadeInUp 300ms ease-out;
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
    transition: all var(--transition-base);
}
.escenario-card:hover { 
    transform: translateY(-3px); 
    box-shadow: var(--shadow-lg); 
}
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
    box-shadow: var(--shadow-xs);
}

/* ============ Tabs internos (st.tabs) ============ */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px;
    border-bottom: 1px solid var(--aidu-gray-200);
}
.stTabs [data-baseweb="tab"] {
    padding: 8px 16px;
    border-radius: var(--radius-sm) var(--radius-sm) 0 0;
    font-weight: 500;
    color: var(--aidu-gray-500);
    transition: all var(--transition-fast);
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: var(--aidu-blue) !important;
    font-weight: 600;
}

/* ============ Mejoras varias ============ */
hr {
    margin: 24px 0 !important;
    border-color: var(--aidu-gray-200) !important;
}

/* (block-container styles consolidados al final del archivo) */

/* Spinner */
.stSpinner > div {
    border-top-color: var(--aidu-blue) !important;
}

/* Alertas con estilo profesional */
[data-testid="stAlert"] {
    border-radius: var(--radius-md);
    border-width: 1px;
    box-shadow: var(--shadow-xs);
    animation: slideInLeft 300ms ease-out;
}

/* Expander */
[data-testid="stExpander"] {
    border-radius: var(--radius-md);
    border: 1px solid var(--aidu-gray-200);
    box-shadow: var(--shadow-xs);
    transition: box-shadow var(--transition-fast);
}
[data-testid="stExpander"]:hover {
    box-shadow: var(--shadow-sm);
}

/* Progress bar */
[data-testid="stProgressBar"] > div > div {
    background: linear-gradient(90deg, var(--aidu-blue) 0%, var(--aidu-blue-light) 100%) !important;
    border-radius: 999px;
}

/* Code blocks inline */
code {
    background: var(--aidu-gray-100) !important;
    color: var(--aidu-blue-dark) !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-size: 13px !important;
    font-weight: 500;
}

/* Selectbox dropdown */
[data-baseweb="select"] {
    border-radius: var(--radius-sm) !important;
}

/* File uploader pro */
[data-testid="stFileUploader"] section {
    border: 2px dashed var(--aidu-gray-300) !important;
    border-radius: var(--radius-md) !important;
    background: var(--aidu-gray-50) !important;
    transition: all var(--transition-base);
}
[data-testid="stFileUploader"] section:hover {
    border-color: var(--aidu-blue) !important;
    background: var(--aidu-blue-50) !important;
}

/* Selectbox: items pro */
[role="listbox"] {
    border-radius: var(--radius-md) !important;
    box-shadow: var(--shadow-lg) !important;
    border: 1px solid var(--aidu-gray-200) !important;
}

/* Links con estilo */
a {
    color: var(--aidu-blue) !important;
    text-decoration: none !important;
    transition: color var(--transition-fast);
}
a:hover {
    color: var(--aidu-blue-light) !important;
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
.estado-EN_CARTERA { background: #F1F5F9; color: #475569; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.estado-EN_ESTUDIO { background: #CFFAFE; color: #0E7490; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.estado-EN_ESTUDIO { background: #DBEAFE; color: #1E40AF; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }
.estado-EN_OFERTA { background: #FED7AA; color: #9A3412; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; }
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

/* Separadores en sidebar (filas tipo "─── EMBUDO ───") */
[data-testid="stSidebar"] [data-baseweb="radio"] label:has(div:contains("───")),
[data-testid="stSidebar"] label[data-baseweb="radio"]:has(span:contains("───")) {
    pointer-events: none !important;
    opacity: 0.5 !important;
    font-size: 10px !important;
    color: #94A3B8 !important;
    font-weight: 700 !important;
    letter-spacing: 1.5px !important;
    text-transform: uppercase !important;
    padding: 12px 0 4px !important;
    border-bottom: 1px solid var(--aidu-gray-200) !important;
    margin: 8px 0 4px !important;
    border-radius: 0 !important;
    cursor: default !important;
}

/* Items numerados del embudo */
[data-testid="stSidebar"] [data-baseweb="radio"] label[aria-checked="true"] {
    background: linear-gradient(90deg, rgba(30, 64, 175, 0.10) 0%, rgba(30, 64, 175, 0.04) 100%) !important;
    border-left: 3px solid var(--aidu-blue) !important;
    color: var(--aidu-blue) !important;
    font-weight: 600 !important;
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

/* (block-container styles consolidados al final del archivo) */

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

/* ============================================================
   AIDU OP · v13 — Pulido corporativo final
   ============================================================ */

/* Asegurar que el contenedor principal use todo el ancho disponible
   y tenga padding superior suficiente para que el header NO se corte */
.main .block-container {
    padding-top: 4rem !important;
    padding-bottom: 4rem !important;
    max-width: 1400px !important;
}

/* Toolbar superior de Streamlit con backdrop-blur */
header[data-testid="stHeader"] {
    background: rgba(255, 255, 255, 0.92) !important;
    backdrop-filter: blur(10px);
    -webkit-backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--aidu-gray-200);
    height: 3rem !important;
    z-index: 999991 !important;
}

/* Sidebar: mejor scroll y look */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%);
    border-right: 1px solid var(--aidu-gray-200);
    box-shadow: 1px 0 4px rgba(15, 23, 42, 0.02);
}

[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    padding-top: 1rem;
}

/* Markdown links inline en cards */
.aidu-card a {
    color: var(--aidu-blue) !important;
    font-weight: 500;
    text-decoration: none;
    border-bottom: 1px dashed transparent;
    transition: all 150ms ease;
}
.aidu-card a:hover {
    border-bottom-color: var(--aidu-blue);
}

/* Botones Streamlit: más definidos */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 150ms cubic-bezier(0.4, 0, 0.2, 1) !important;
    border: 1px solid var(--aidu-gray-200) !important;
}
.stButton > button:hover {
    border-color: var(--aidu-blue) !important;
    background: var(--aidu-gray-50) !important;
    transform: translateY(-1px);
    box-shadow: 0 2px 4px rgba(15, 23, 42, 0.06) !important;
}

.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--aidu-blue) 0%, var(--aidu-blue-dark) 100%) !important;
    color: white !important;
    border: none !important;
    box-shadow: 0 1px 3px rgba(30, 64, 175, 0.3) !important;
}
.stButton > button[kind="primary"]:hover {
    box-shadow: 0 4px 12px rgba(30, 64, 175, 0.4) !important;
    transform: translateY(-1px);
}

/* Hero de página: padding ligero pero no comprime */
.aidu-hero {
    padding: 4px 0 12px !important;
    margin-bottom: 16px !important;
}

/* Cards de información clickeables */
.aidu-card-clickable {
    cursor: pointer !important;
    transition: all 200ms ease !important;
}
.aidu-card-clickable:hover {
    border-color: var(--aidu-blue) !important;
    background: linear-gradient(135deg, rgba(30, 64, 175, 0.02) 0%, white 100%) !important;
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08) !important;
}

/* Tabs internos */
.stTabs [data-baseweb="tab-list"] {
    gap: 4px !important;
    border-bottom: 1px solid var(--aidu-gray-200) !important;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 6px 6px 0 0 !important;
    padding: 8px 14px !important;
    font-weight: 500 !important;
    color: var(--aidu-gray-700) !important;
    background: transparent !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: var(--aidu-blue) !important;
    background: var(--aidu-gray-50) !important;
}
.stTabs [aria-selected="true"] {
    color: var(--aidu-blue) !important;
    background: white !important;
    border-bottom: 2px solid var(--aidu-blue) !important;
    font-weight: 600 !important;
}

/* Métricas: número grande y label limpio */
[data-testid="stMetricValue"] {
    font-size: 26px !important;
    font-weight: 700 !important;
    color: var(--aidu-blue) !important;
    letter-spacing: -0.5px !important;
}
[data-testid="stMetricLabel"] {
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    color: var(--aidu-gray-500) !important;
    font-weight: 600 !important;
}

/* Inputs más definidos */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div {
    border-radius: 8px !important;
    border: 1px solid var(--aidu-gray-200) !important;
    transition: all 150ms ease !important;
}
.stTextInput > div > div > input:focus,
.stNumberInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--aidu-blue) !important;
    box-shadow: 0 0 0 3px rgba(30, 64, 175, 0.1) !important;
}

/* Expanders más limpios */
[data-testid="stExpander"] {
    border: 1px solid var(--aidu-gray-200) !important;
    border-radius: 10px !important;
    background: white !important;
}
[data-testid="stExpander"]:hover {
    border-color: var(--aidu-blue-light) !important;
}

/* Alertas */
[data-testid="stAlert"] {
    border-radius: 10px !important;
    border-left-width: 3px !important;
}

/* Divider */
hr {
    margin: 1.5rem 0 !important;
    border-color: var(--aidu-gray-200) !important;
    opacity: 0.6;
}

/* Tabla de información en ficha */
.aidu-info-table {
    width: 100%;
    font-size: 13px;
    border-collapse: collapse;
}
.aidu-info-table tr {
    border-bottom: 1px solid var(--aidu-gray-100);
}
.aidu-info-table tr:last-child {
    border-bottom: none;
}
.aidu-info-table td {
    padding: 10px 0;
    vertical-align: top;
}
.aidu-info-table td:first-child {
    color: var(--aidu-gray-500);
    width: 40%;
    font-size: 12px;
}
.aidu-info-table td:last-child {
    color: var(--aidu-gray-900);
    font-weight: 500;
}

/* Pills de tipo y complejidad */
.aidu-pill {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 999px;
    font-size: 11px;
    font-weight: 600;
    margin-right: 4px;
}
.aidu-pill-blue { background: rgba(30, 64, 175, 0.1); color: var(--aidu-blue); }
.aidu-pill-cyan { background: rgba(14, 116, 144, 0.1); color: #0E7490; }
.aidu-pill-amber { background: rgba(217, 119, 6, 0.1); color: var(--aidu-warning); }
.aidu-pill-green { background: rgba(21, 128, 61, 0.1); color: var(--aidu-success); }
.aidu-pill-red { background: rgba(220, 38, 38, 0.1); color: var(--aidu-danger); }
.aidu-pill-gray { background: var(--aidu-gray-100); color: var(--aidu-gray-700); }

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


def url_licitacion_mp(codigo: str) -> str:
    """
    URL pública de Mercado Público para llegar a la ficha de una licitación.
    
    Estrategia: usar el buscador público (que NO requiere sesión) con el
    código pre-cargado. MP redirige automáticamente al detalle si encuentra
    una coincidencia exacta. Para licitaciones vigentes funciona casi siempre.
    
    Para licitaciones históricas/cerradas, lleva al buscador donde el usuario
    puede ver el resultado y entrar manualmente.
    """
    if not codigo:
        return "https://www.mercadopublico.cl/"
    # URL del buscador público nuevo: lleva a resultados con el código
    # No requiere sesión, no genera error 403
    return f"https://www.mercadopublico.cl/Portal/Modules/Site/Busquedas/BuscadorAvanzado.aspx?qs={codigo}"


def url_busqueda_mp(codigo: str) -> str:
    """Alias para compatibilidad con código antiguo."""
    return url_licitacion_mp(codigo)


# ============================================================
# VISTA DE DETALLE DEL PROYECTO
# ============================================================
def render_detalle_proyecto(proyecto_id: int):
    """
    Vista de detalle profesional de un proyecto.
    7 tabs ricos con código defensivo (cada tab maneja sus propios errores).
    """
    conn = get_connection()
    p = conn.execute("SELECT * FROM aidu_proyectos WHERE id = ?", (proyecto_id,)).fetchone()
    conn.close()
    
    if not p:
        st.error("Proyecto no encontrado")
        if st.button("← Volver"):
            st.session_state.view_proyecto_id = None
            st.rerun()
        return
    
    p = dict(p)
    
    # Color y label del estado
    color_estado_map = {
        "EN_CARTERA":  ("#64748B", "#F1F5F9", "📂 En Cartera"),
        "EN_ESTUDIO":  ("#0E7490", "#CFFAFE", "🔬 En Estudio"),
        "EN_OFERTA":   ("#9A3412", "#FED7AA", "📝 En Oferta"),
        "LISTO_SUBIR": ("#6B21A8", "#E9D5FF", "📤 Listo Subir"),
        "ADJUDICADO":  ("#14532D", "#BBF7D0", "🏆 Adjudicado"),
        "PERDIDO":     ("#7F1D1D", "#FEE2E2", "❌ Perdido"),
        "DESCARTADO":  ("#475569", "#F1F5F9", "🗑️ Descartado"),
    }
    color, bg, estado_label = color_estado_map.get(p["estado"], ("#64748B", "#F1F5F9", p["estado"]))
    
    dias_cierre = calcular_dias_cierre(p.get("fecha_cierre")) if p.get("fecha_cierre") else None
    color_dias = "#DC2626" if dias_cierre is not None and dias_cierre <= 3 else "#D97706" if dias_cierre is not None and dias_cierre <= 7 else "#15803D"
    
    url_mp = p.get("url_mp") or url_licitacion_mp(p["codigo_externo"])
    
    # ===== HEADER LIMPIO (sin HTML denso que causaba </div> visibles) =====
    col_back, col_spacer, col_mp = st.columns([1, 3, 2])
    
    with col_back:
        if st.button("← Volver", use_container_width=True, key="back_detalle"):
            st.session_state.view_proyecto_id = None
            st.rerun()
    
    with col_mp:
        st.markdown(
            f"<a href='{url_mp}' target='_blank' style='display:block; padding:7px 14px; background:#1E40AF; color:white; "
            f"border-radius:8px; text-decoration:none; font-weight:600; font-size:13px; text-align:center;'>"
            f"🌐 Buscar en Mercado Público</a>",
            unsafe_allow_html=True
        )
    
    # Header en una sola card limpia
    dias_html = f"<span style='color:{color_dias}; font-weight:600;'>⏰ {dias_cierre} días para cerrar</span>" if dias_cierre is not None else ""
    
    st.markdown(
        f"<div style='background:linear-gradient(135deg, {bg} 0%, white 80%); padding:20px 24px; "
        f"border-radius:14px; margin:16px 0 20px; border-left:4px solid {color};'>"
        f"<div style='display:flex; align-items:center; gap:10px; margin-bottom:6px;'>"
        f"<span style='background:{color}; color:white; padding:4px 12px; border-radius:999px; font-size:11px; font-weight:700; letter-spacing:0.4px;'>{estado_label}</span>"
        f"<span style='font-family:JetBrains Mono,monospace; font-size:12px; color:#64748B;'>{p['codigo_externo']}</span>"
        f"</div>"
        f"<div style='font-size:22px; font-weight:700; color:#0F172A; line-height:1.3; margin-bottom:8px;'>{p['nombre']}</div>"
        f"<div style='display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;'>"
        f"<div style='font-size:13px; color:#64748B;'>"
        f"🏛️ {p.get('organismo') or '—'} · 📍 {p.get('region') or '—'} · 🎯 {p.get('cod_servicio_aidu') or 'Sin categoría'}"
        f"</div>"
        f"<div style='text-align:right;'>"
        f"<div style='font-size:11px; color:#64748B; font-weight:600; text-transform:uppercase; letter-spacing:0.5px;'>Monto referencial</div>"
        f"<div style='font-size:28px; font-weight:800; color:#1E40AF; letter-spacing:-0.5px;'>{formato_clp(p.get('monto_referencial', 0))}</div>"
        f"{dias_html}"
        f"</div></div></div>",
        unsafe_allow_html=True
    )
    
    # ===== ACCIONES DE ESTADO =====
    flow_estados = [
        ("EN_CARTERA",  "📂 Cartera"),
        ("EN_ESTUDIO",  "🔬 Estudio"),
        ("EN_OFERTA",   "📝 Ofertar"),
        ("LISTO_SUBIR", "📤 Subir a MP"),
    ]
    
    estado_idx = next((i for i, (e, _) in enumerate(flow_estados) if e == p["estado"]), -1)
    
    if estado_idx >= 0 and estado_idx < len(flow_estados) - 1:
        sig_est, sig_label = flow_estados[estado_idx + 1]
        col_av1, col_av2, col_av3 = st.columns([2, 2, 1])
        with col_av1:
            if st.button(f"➡️ Avanzar a {sig_label}", type="primary", use_container_width=True, key="adv"):
                _cambiar_estado(proyecto_id, sig_est)
                st.rerun()
        with col_av2:
            if estado_idx > 0:
                ant_est, ant_label = flow_estados[estado_idx - 1]
                if st.button(f"⬅️ Retroceder a {ant_label}", use_container_width=True, key="ret"):
                    _cambiar_estado(proyecto_id, ant_est)
                    st.rerun()
        with col_av3:
            if st.button("❌ Descartar", use_container_width=True, key="desc"):
                _cambiar_estado(proyecto_id, "DESCARTADO")
                st.rerun()
    
    # ===== TABS (cada uno con try/except para no romper toda la ficha) =====
    t_resumen, t_analisis, t_ia, t_consultas, t_oferta, t_bitacora = st.tabs([
        "📋 Resumen",
        "📊 Análisis Económico",
        "🤖 Análisis IA",
        "💬 Consultas MP",
        "📝 Oferta (HH + Precio + Paquete)",
        "🗒️ Bitácora",
    ])
    
    # Compatibilidad con código antiguo
    t_comparables = t_analisis
    t_precios = t_analisis
    t_equipo = t_oferta
    t_paquete = t_oferta
    
    # ============ TAB 1: RESUMEN ============
    with t_resumen:
        # Aspectos técnicos extraídos automáticamente
        try:
            from app.core.extractor_aspectos import extraer_aspectos, estimar_hh_referencial
            aspectos = extraer_aspectos(p.get("descripcion") or "", p.get("nombre") or "")
            hh_ref = estimar_hh_referencial(p.get("monto_referencial") or 0)
        except Exception:
            aspectos = {}
            hh_ref = {}
        
        # FILA 1: Aspectos técnicos clave (4 cards)
        st.markdown("##### 🔧 Aspectos técnicos del proyecto")
        st.caption("Extraídos automáticamente desde la descripción de MP. Permiten comparar servicios reales (no solo monto).")
        
        col_a1, col_a2, col_a3, col_a4 = st.columns(4)
        
        m2_val = p.get("metros_cuadrados") or aspectos.get("metros_cuadrados")
        col_a1.metric(
            "📐 Superficie",
            f"{m2_val} m²" if m2_val else "No especifica",
            help="m² mencionados en la descripción de la licitación"
        )
        
        plazo_val = p.get("plazo_dias") or aspectos.get("plazo_dias")
        col_a2.metric(
            "⏱️ Plazo ejecución",
            f"{plazo_val} días" if plazo_val else "No especifica",
            help="Plazo total estimado en días corridos"
        )
        
        n_ent = p.get("n_entregables") or aspectos.get("n_entregables", 0)
        col_a3.metric(
            "📋 Entregables",
            f"{n_ent} tipos",
            help="Cantidad de tipos de entregables identificados (planos, memorias, informes, etc.)"
        )
        
        col_a4.metric(
            "💪 HH estimadas",
            f"{hh_ref.get('hh_total', 0)} HH",
            help=f"~{hh_ref.get('dias_dedicados', 0)} días-persona considerando tarifa AIDU + overhead + margen"
        )
        
        # Pills de tipo y complejidad
        tipo = p.get("tipo_servicio") or aspectos.get("tipo_servicio", "—")
        compl = p.get("complejidad") or aspectos.get("complejidad", "—")
        pill_compl = {"BAJA": "aidu-pill-green", "MEDIA": "aidu-pill-amber", "ALTA": "aidu-pill-red"}.get(compl, "aidu-pill-gray")
        
        st.markdown(
            f"<div style='margin:12px 0 8px;'>"
            f"<span class='aidu-pill aidu-pill-blue'>📑 {tipo}</span>"
            f"<span class='aidu-pill {pill_compl}'>🎯 Complejidad {compl}</span>"
            f"</div>",
            unsafe_allow_html=True
        )
        
        # Lista de entregables identificados
        entregables = aspectos.get("entregables", [])
        if entregables:
            st.markdown(
                f"<div style='font-size:12px; color:#64748B; margin-bottom:16px;'>"
                f"<strong>Entregables detectados:</strong> {' · '.join(entregables)}"
                f"</div>",
                unsafe_allow_html=True
            )
        
        st.divider()
        
        # FILA 2: Información general + Resumen económico
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("##### 📌 Información general")
            
            info_html = (
                "<div style='background:white; padding:16px 22px; border:1px solid #E2E8F0; border-radius:10px;'>"
                "<table class='aidu-info-table'>"
                f"<tr><td>Código MP</td><td style='font-family:JetBrains Mono,monospace;'>{p['codigo_externo']}</td></tr>"
                f"<tr><td>Mandante</td><td>{p.get('organismo') or '—'}</td></tr>"
                f"<tr><td>Región</td><td>{p.get('region') or '—'}</td></tr>"
                f"<tr><td>Categoría AIDU</td><td><span class='aidu-pill aidu-pill-blue'>{p.get('cod_servicio_aidu') or '—'}</span></td></tr>"
                f"<tr><td>Estado</td><td>{estado_label}</td></tr>"
                f"<tr><td>Fecha publicación</td><td>{p.get('fecha_publicacion') or '—'}</td></tr>"
                f"<tr><td>Fecha cierre</td><td><strong style='color:{color_dias};'>{p.get('fecha_cierre') or '—'}</strong></td></tr>"
                "</table></div>"
            )
            st.markdown(info_html, unsafe_allow_html=True)
            
            if p.get("descripcion"):
                with st.expander("📄 Descripción completa de las bases", expanded=True):
                    st.markdown(
                        f"<div style='background:#F8FAFC; padding:14px 18px; border-radius:8px; "
                        f"font-size:13px; color:#334155; line-height:1.65;'>{p['descripcion']}</div>",
                        unsafe_allow_html=True
                    )
            
            # Inteligencia mandante (defensivo)
            try:
                from app.core.inteligencia_avanzada import analizar_mandante
                if p.get("organismo"):
                    mand = analizar_mandante(p["organismo"])
                    if mand and mand.get("encontrado") and mand.get("total_licitaciones", 0) > 0:
                        st.markdown("##### 🏛️ Inteligencia del mandante")
                        st.caption(f"Datos históricos de **{p['organismo']}** en Mercado Público.")
                        
                        col_m1, col_m2, col_m3 = st.columns(3)
                        col_m1.metric("📋 Licitaciones", mand.get("total_licitaciones", 0))
                        col_m2.metric("💰 Ticket promedio", formato_clp(mand.get("monto_promedio_clp", 0)))
                        col_m3.metric("📉 Descuento promedio", f"{mand.get('descuento_promedio_pct', 0):.1f}%")
                        
                        # Categorías frecuentes
                        cats = mand.get("categorias_frecuentes", [])[:3]
                        if cats:
                            cat_html = " · ".join([f"<span class='aidu-pill aidu-pill-cyan'>{c['categoria']} ({c['n']})</span>" for c in cats])
                            st.markdown(
                                f"<div style='margin-top:12px; font-size:12px;'>"
                                f"<strong style='color:#64748B;'>Categorías que más licita:</strong> {cat_html}"
                                f"</div>",
                                unsafe_allow_html=True
                            )
            except Exception:
                st.caption("⚠️ Inteligencia del mandante no disponible")
        
        with col2:
            st.markdown("##### 💰 Resumen económico")
            
            try:
                from app.core.configuracion import obtener_config
                cfg = obtener_config()
                tarifa = cfg.tarifa_hora_clp
                overhead = cfg.overhead_pct
            except Exception:
                tarifa, overhead = 78000, 18
            
            costo_hora = int(tarifa * (1 + overhead / 100))
            monto_ref = p.get("monto_referencial", 0) or 0
            
            if monto_ref < 3_000_000:
                zona, cz = "⚠️ Bajo sweet spot", "#D97706"
            elif monto_ref > 15_000_000:
                zona, cz = "⚠️ Sobre sweet spot", "#D97706"
            else:
                zona, cz = "✅ En sweet spot", "#15803D"
            
            st.markdown(
                f"<div style='background:white; padding:18px; border:1px solid #E2E8F0; border-radius:10px;'>"
                f"<div style='font-size:11px; color:#64748B; text-transform:uppercase; font-weight:600; letter-spacing:0.5px;'>Monto referencial</div>"
                f"<div style='font-size:26px; font-weight:800; color:#1E40AF; margin:6px 0 10px; letter-spacing:-0.5px;'>{formato_clp(monto_ref)}</div>"
                f"<div style='font-size:11px; font-weight:600; color:{cz}; padding:4px 10px; background:{cz}15; "
                f"border-radius:6px; display:inline-block;'>{zona}</div>"
                f"<div style='border-top:1px solid #F1F5F9; padding-top:12px; margin-top:14px;'>"
                f"<div style='display:flex; justify-content:space-between; font-size:12px; color:#64748B; padding:4px 0;'>"
                f"<span>Tarifa hora AIDU</span><span style='font-weight:600; color:#0F172A;'>{formato_clp(tarifa)}</span></div>"
                f"<div style='display:flex; justify-content:space-between; font-size:12px; color:#64748B; padding:4px 0;'>"
                f"<span>Costo c/overhead {overhead}%</span><span style='font-weight:600; color:#0F172A;'>{formato_clp(costo_hora)}</span></div>"
                f"<div style='display:flex; justify-content:space-between; font-size:12px; color:#64748B; padding:4px 0;'>"
                f"<span>HH equivalentes</span><span style='font-weight:600; color:#0F172A;'>{hh_ref.get('hh_total', 0)} HH</span></div>"
                f"</div></div>",
                unsafe_allow_html=True
            )
            
            # Predicción descuento con explicación
            try:
                from app.core.inteligencia_avanzada import predecir_descuento_optimo
                pred = predecir_descuento_optimo(
                    p.get("cod_servicio_aidu") or "",
                    p.get("organismo"),
                    p.get("monto_referencial")
                )
                color_p = "#15803D" if pred["confianza"] >= 0.6 else "#D97706"
                
                st.markdown(
                    f"<div style='background:linear-gradient(135deg, {color_p}10 0%, white 80%); "
                    f"padding:14px 16px; border:1px solid #E2E8F0; border-left:3px solid {color_p}; "
                    f"border-radius:10px; margin-top:14px;'>"
                    f"<div style='font-size:11px; color:{color_p}; text-transform:uppercase; font-weight:700; letter-spacing:0.5px;'>🎯 Descuento óptimo recomendado</div>"
                    f"<div style='font-size:28px; font-weight:800; color:{color_p}; line-height:1; margin:6px 0;'>{pred['descuento_recomendado_pct']}%</div>"
                    f"<div style='font-size:11px; color:#64748B;'>Banda: {pred['descuento_minimo_pct']}% – {pred['descuento_maximo_pct']}%</div>"
                    f"<div style='font-size:11px; color:#64748B; margin-top:4px;'>Confianza: <strong style='color:{color_p};'>{pred['confianza']*100:.0f}%</strong></div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            except Exception:
                pass
    
    # ============================================================
    # TAB FUSIONADO: 📊 ANÁLISIS ECONÓMICO
    # Fusiona Comparables + Inteligencia de Precios + filosofía AIDU
    # ============================================================
    with t_analisis:
        # === EXPLICACIÓN DEL ENFOQUE AIDU ===
        with st.expander("💡 ¿Cómo se calcula tu rango de oferta? (lee esto primero)", expanded=False):
            st.markdown("""
**Filosofía AIDU**: Tu HH es tu principal activo. **No tienes pérdida**, sólo más o menos margen sobre tu HH.

**3 conceptos clave**:

1. **Costo HH AIDU** = tarifa hora × (1 + overhead %). Es tu costo *real* por hora trabajada.
2. **Precio piso** = HH estimadas × Costo HH. Bajo este precio, no cubres tus costos operacionales.
3. **Precio ofertable** = Precio piso × (1 + margen objetivo %). Tu margen objetivo (default 22%) viene de tu configuración.

**¿Qué es un "descuento"?** Cuando MP publica un monto referencial, los competidores ofertan **menos** que ese referencial. El "descuento promedio histórico" es cuánto bajan los ganadores. **No significa pérdida** — significa "qué rango de precio gana adjudicaciones en este tipo de proyecto".

**Cómo usarlo**: 
- Ver mediana de precios homologados → ese es el precio de mercado.
- Tu precio piso te dice **cuánto NO bajar**.
- Si la mediana > tu piso → **competitivo**, oferta cerca de la mediana.
- Si la mediana < tu piso → **revisa tus HH estimadas**. Probablemente puedes hacer el trabajo en menos tiempo o el proyecto no te conviene.
""")
        
        # === SELECTORES DE COMPARACIÓN ===
        st.markdown("##### 🎛️ Filtros de comparación")
        st.caption("Ajusta los criterios para ver contra qué se está comparando este proyecto.")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        
        with col_f1:
            cat_actual = p.get("cod_servicio_aidu") or ""
            usar_categoria = st.checkbox("Categoría AIDU", value=True, key="filt_cat", help=f"Filtra por: {cat_actual}")
        
        with col_f2:
            region_actual = p.get("region")
            usar_region = st.checkbox("Misma región", value=False, key="filt_reg", help=f"Filtra por: {region_actual or '—'}")
        
        with col_f3:
            usar_complejidad = st.checkbox("Misma complejidad", value=False, key="filt_compl", help="Filtra por nivel de complejidad técnica similar")
        
        st.divider()
        
        # === COMPARABLES HOMOLOGADOS ===
        try:
            from app.core.comparables_homologados import buscar_comparables_homologados
            
            comp = buscar_comparables_homologados(
                cod_servicio_aidu=p.get("cod_servicio_aidu") or "" if usar_categoria else None,
                region=p.get("region") if usar_region else None,
                monto_referencial=p.get("monto_referencial"),
                limit=15
            )
            
            n = comp["n_comparables"]
            
            if n == 0:
                st.info(f"📭 Sin comparables adjudicados para este perfil. Prueba relajando los filtros.")
            else:
                # ===== BLOQUE 1: PRECIO DE MERCADO HOMOLOGADO =====
                st.markdown("##### 💵 Precio de mercado (homologado)")
                st.caption(f"Basado en **{n} licitaciones similares adjudicadas**. Cada una ajustada por inflación + región vs hoy.")
                
                stats = comp["estadisticas_homologadas"]
                
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                col_s1.metric(
                    "📊 Mediana",
                    formato_clp(stats["monto_adj_mediana"]),
                    help="50% de los proyectos similares se adjudicaron por menos de este monto, 50% por más. Es la referencia de mercado más estable."
                )
                col_s2.metric(
                    "📈 Promedio",
                    formato_clp(stats["monto_adj_promedio"]),
                    help="Promedio aritmético. Más sensible a outliers que la mediana."
                )
                col_s3.metric(
                    "⬇️ Mínimo",
                    formato_clp(stats["monto_adj_min"]),
                    help="El proyecto más barato adjudicado en este perfil. Sirve para entender el piso de competencia agresiva."
                )
                col_s4.metric(
                    "⬆️ Máximo",
                    formato_clp(stats["monto_adj_max"]),
                    help="El proyecto más caro adjudicado. Si tu propuesta tiene valor diferenciado puedes apuntar aquí."
                )
                
                # ===== BLOQUE 2: TU PRECIO PISO (HH × Costo) =====
                st.markdown("##### 🏗️ Tu precio piso (basado en HH)")
                st.caption("Este es el precio mínimo que NO debes bajar. Por debajo, no cubres tus costos AIDU.")
                
                try:
                    from app.core.configuracion import obtener_config
                    cfg = obtener_config()
                    tarifa = cfg.tarifa_hora_clp
                    overhead = cfg.overhead_pct
                    margen_obj = cfg.margen_objetivo_pct
                except Exception:
                    tarifa, overhead, margen_obj = 78000, 18, 22
                
                costo_hora = int(tarifa * (1 + overhead / 100))
                
                # HH estimadas: usar las del proyecto si existen, si no estimar
                hh_total_est = (p.get("hh_ignacio_estimado") or 0) + (p.get("hh_jorella_estimado") or 0)
                if hh_total_est == 0:
                    # Estimar desde monto referencial
                    monto_ref_aux = p.get("monto_referencial") or 0
                    if monto_ref_aux > 0:
                        hh_total_est = max(20, int(monto_ref_aux / (costo_hora * 1.22)))
                    else:
                        hh_total_est = 40  # default
                    hh_origen = "estimado"
                else:
                    hh_origen = "configurado"
                
                precio_piso = hh_total_est * costo_hora
                precio_objetivo = int(precio_piso * (1 + margen_obj / 100))
                
                col_p1, col_p2, col_p3 = st.columns(3)
                col_p1.metric(
                    "⏱️ HH estimadas",
                    f"{hh_total_est} HH",
                    help=f"Total de horas-hombre del equipo AIDU. {hh_origen.capitalize()} (ajusta en tab Oferta)."
                )
                col_p2.metric(
                    "🏗️ Precio piso",
                    formato_clp(precio_piso),
                    help=f"= {hh_total_est} HH × {formato_clp(costo_hora)} (costo c/overhead {overhead}%). NO bajar de aquí."
                )
                col_p3.metric(
                    "🎯 Precio objetivo",
                    formato_clp(precio_objetivo),
                    help=f"= Piso × (1 + {margen_obj}% margen objetivo). Es tu precio ideal con margen sano."
                )
                
                # ===== BLOQUE 3: TU OFERTA RECOMENDADA =====
                st.markdown("##### 💡 Recomendación de oferta")
                
                mediana = stats["monto_adj_mediana"]
                
                # Comparar mediana vs precio piso
                if mediana >= precio_objetivo:
                    color_rec, label_rec = "#15803D", "✅ ZONA CÓMODA"
                    texto_rec = (
                        f"La mediana de mercado ({formato_clp(mediana)}) supera tu precio objetivo ({formato_clp(precio_objetivo)}). "
                        f"Puedes ofertar entre {formato_clp(precio_objetivo)} y {formato_clp(mediana)} con buen margen. "
                        f"**Recomendación: ofertar cerca de {formato_clp(int((precio_objetivo + mediana) / 2))}** para ganar competitividad."
                    )
                elif mediana >= precio_piso:
                    color_rec, label_rec = "#D97706", "⚠️ ZONA AJUSTADA"
                    margen_real_pct = ((mediana - precio_piso) / precio_piso) * 100
                    texto_rec = (
                        f"La mediana ({formato_clp(mediana)}) está entre tu piso y tu objetivo. "
                        f"Si ofertas en mediana, tu margen real será **{margen_real_pct:.1f}%** (vs {margen_obj}% objetivo). "
                        f"**Decisión: ofertar es viable** pero ajustado. Considera reducir HH si es posible."
                    )
                else:
                    color_rec, label_rec = "#DC2626", "🔴 NO CONVIENE"
                    texto_rec = (
                        f"La mediana de mercado ({formato_clp(mediana)}) está POR DEBAJO de tu precio piso ({formato_clp(precio_piso)}). "
                        f"En este perfil, los proyectos se adjudican demasiado bajo para tu costo AIDU. "
                        f"**Recomendación**: revisa si puedes hacer el trabajo en menos HH, o **descarta este proyecto**."
                    )
                
                st.markdown(
                    f"<div style='background:{color_rec}10; padding:18px 22px; border-radius:12px; "
                    f"border-left:5px solid {color_rec}; margin-top:8px;'>"
                    f"<div style='font-size:12px; color:{color_rec}; font-weight:700; text-transform:uppercase; letter-spacing:0.5px;'>{label_rec}</div>"
                    f"<div style='font-size:14px; color:#0F172A; margin-top:8px; line-height:1.65;'>{texto_rec}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
                
                # ===== BLOQUE 4: DÓNDE CAE TU REFERENCIAL =====
                monto_ref = p.get("monto_referencial", 0) or 0
                if mediana > 0 and monto_ref > 0:
                    delta_pct = ((monto_ref - mediana) / mediana) * 100
                    color_delta = "#15803D" if delta_pct > 5 else "#D97706" if delta_pct > -5 else "#DC2626"
                    label = "✅ holgado" if delta_pct > 5 else "⚠️ ajustado" if delta_pct > -5 else "🔴 bajo competencia"
                    st.markdown(
                        f"<div style='background:white; padding:14px 18px; border:1px solid #E2E8F0; "
                        f"border-left:3px solid {color_delta}; border-radius:8px; margin-top:14px;'>"
                        f"<div style='font-size:12px; color:#64748B;'>Tu monto referencial ({formato_clp(monto_ref)}) vs mediana de mercado:</div>"
                        f"<div style='font-size:15px; font-weight:600; color:{color_delta}; margin-top:4px;'>"
                        f"{label} · {delta_pct:+.1f}% ({formato_clp(int(monto_ref - mediana))} de diferencia)"
                        f"</div></div>",
                        unsafe_allow_html=True
                    )
                
                # ===== BLOQUE 5: HOMOLOGACIÓN VISIBLE =====
                with st.expander("🔍 ¿Cómo se calculan los precios homologados?"):
                    crit = comp["criterios_homologacion"]
                    st.markdown(f"""
**Categoría buscada**: `{crit.get('categoria_buscada')}`  
**Región**: `{crit.get('region_buscada')}`

{crit.get('explicacion', '')}
                    """)
                
                st.divider()
                
                # ===== BLOQUE 6: TOP COMPARABLES =====
                st.markdown(f"##### 📋 Top {n} comparables (ordenados por similitud)")
                st.caption("Click en cada uno para ver detalle completo en MP. Los pills muestran aspectos técnicos.")
                
                for c in comp["comparables"]:
                    sim = c["similitud"]
                    color_sim = "#15803D" if sim >= 70 else "#D97706" if sim >= 50 else "#DC2626"
                    
                    monto_orig = c.get("monto_adjudicado", 0)
                    monto_homol = c["monto_adjudicado_homologado"]
                    factor = c["factor_total"]
                    
                    delta_homol = ""
                    if factor != 1.0:
                        diff = monto_homol - monto_orig
                        pct = (diff / monto_orig * 100) if monto_orig else 0
                        delta_homol = f" <span style='color:#64748B; font-size:11px;'>(× {factor} = {pct:+.1f}%)</span>"
                    
                    desc_str = f"{c['descuento_pct']:+.1f}% descuento" if c.get("descuento_pct") is not None else "Sin dato descuento"
                    fecha = c.get("fecha_adjudicacion") or "—"
                    if fecha and fecha != "—":
                        fecha = fecha[:10]
                    
                    # Cargar aspectos técnicos del comparable
                    asp_c = {}
                    try:
                        conn_c = get_connection()
                        asp_row = conn_c.execute(
                            "SELECT metros_cuadrados, plazo_dias, n_entregables, tipo_servicio, complejidad "
                            "FROM mp_licitaciones_adj WHERE codigo_externo = ?",
                            (c["codigo_externo"],)
                        ).fetchone()
                        conn_c.close()
                        if asp_row:
                            asp_c = dict(asp_row)
                    except Exception:
                        asp_c = {}
                    
                    # Pills técnicas
                    tech_pills = []
                    if asp_c.get("metros_cuadrados"):
                        tech_pills.append(f"<span class='aidu-pill aidu-pill-cyan'>📐 {asp_c['metros_cuadrados']} m²</span>")
                    if asp_c.get("plazo_dias"):
                        tech_pills.append(f"<span class='aidu-pill aidu-pill-blue'>⏱️ {asp_c['plazo_dias']}d</span>")
                    if asp_c.get("n_entregables"):
                        tech_pills.append(f"<span class='aidu-pill aidu-pill-gray'>📋 {asp_c['n_entregables']} entreg.</span>")
                    if asp_c.get("complejidad"):
                        c_pill = {"BAJA": "aidu-pill-green", "MEDIA": "aidu-pill-amber", "ALTA": "aidu-pill-red"}.get(asp_c["complejidad"], "aidu-pill-gray")
                        tech_pills.append(f"<span class='aidu-pill {c_pill}'>🎯 {asp_c['complejidad']}</span>")
                    
                    pills_html = " ".join(tech_pills) if tech_pills else ""
                    url_comp = url_licitacion_mp(c["codigo_externo"])
                    
                    st.markdown(
                        f"<div class='aidu-card' style='border-left:3px solid {color_sim};'>"
                        f"<div style='display:flex; justify-content:space-between; align-items:start; gap:16px;'>"
                        f"<div style='flex:1; min-width:0;'>"
                        f"<div style='display:flex; align-items:center; gap:8px; margin-bottom:6px;'>"
                        f"<span style='background:{color_sim}; color:white; padding:3px 10px; border-radius:6px; font-size:10px; font-weight:700; letter-spacing:0.4px;'>SIM {sim}/100</span>"
                        f"<a href='{url_comp}' target='_blank' style='font-family:JetBrains Mono,monospace; font-size:11px; color:#1E40AF; text-decoration:none;'>🔗 {c['codigo_externo']}</a>"
                        f"</div>"
                        f"<div style='font-size:13px; font-weight:600; color:#0F172A; margin-bottom:6px;'>{c['nombre']}</div>"
                        f"<div style='font-size:12px; color:#64748B; margin-bottom:6px;'>"
                        f"🏛️ {c.get('organismo') or '—'} · 📅 {fecha} · 👥 {c.get('n_oferentes') or '?'} oferentes"
                        f"</div>"
                        f"<div style='margin-top:6px;'>{pills_html}</div>"
                        f"</div>"
                        f"<div style='text-align:right; min-width:200px;'>"
                        f"<div style='font-size:11px; color:#64748B;'>Adjudicado: {formato_clp(monto_orig)}</div>"
                        f"<div style='font-size:20px; font-weight:700; color:#1E40AF; line-height:1.2;'>{formato_clp(monto_homol)}</div>"
                        f"<div style='font-size:11px; color:#64748B;'>Homologado{delta_homol}</div>"
                        f"<div style='font-size:11px; color:#15803D; font-weight:600; margin-top:4px;'>{desc_str}</div>"
                        f"</div></div></div>",
                        unsafe_allow_html=True
                    )
        except Exception as e:
            st.error(f"Error cargando análisis económico: {e}")
            import traceback
            with st.expander("Detalle del error"):
                st.code(traceback.format_exc())
    
    # ============ TAB 4: ANÁLISIS IA ============
    with t_ia:
        st.markdown("##### 🤖 Análisis IA de bases técnicas")
        st.caption("Sube el PDF de las bases y Claude extraerá requisitos, plazos, riesgos y recomendación.")
        
        try:
            from app.core.analisis_bases import obtener_ultimo_analisis, analizar_pdf_bases
            
            ultimo = obtener_ultimo_analisis(p["codigo_externo"])
            
            if ultimo:
                st.success(f"📦 Análisis previo del {ultimo['fecha_analisis']} · Costo: ${ultimo['costo_usd']:.4f} USD")
                resultado = ultimo["resultado"]
                rec = resultado.get("recomendacion", {})
                postular = rec.get("postular", "incierto")
                color_r = "#15803D" if postular == "si" else "#DC2626" if postular == "no" else "#D97706"
                label_r = "✅ POSTULAR" if postular == "si" else "❌ NO POSTULAR" if postular == "no" else "⚠️ CON RESERVAS"
                
                st.markdown(
                    f"<div style='padding:16px 20px; background:linear-gradient(135deg, {color_r}15 0%, white 70%); "
                    f"border-left:4px solid {color_r}; border-radius:10px; margin:12px 0;'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:center;'>"
                    f"<div style='font-size:18px; font-weight:800; color:{color_r};'>{label_r}</div>"
                    f"<div style='font-size:22px; font-weight:800; color:{color_r};'>{rec.get('confianza', 0)}%</div>"
                    f"</div>"
                    f"<div style='font-size:13px; color:#334155; margin-top:8px;'>{resultado.get('resumen_ejecutivo', '')}</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
            else:
                st.info("Aún no se ha analizado las bases técnicas de este proyecto.")
            
            archivo = st.file_uploader(
                "📄 Sube el PDF de las bases técnicas",
                type=["pdf"],
                key=f"upload_ia_{proyecto_id}"
            )
            if archivo and st.button("🚀 Analizar con Claude", type="primary", key="run_ia"):
                with st.spinner("🤖 Claude está leyendo las bases..."):
                    resultado = analizar_pdf_bases(
                        archivo.read(),
                        codigo_licitacion=p["codigo_externo"],
                        proyecto_id=proyecto_id,
                        forzar_reanalisis=True
                    )
                if resultado["ok"]:
                    st.success(f"✅ Análisis completado · ${resultado['meta']['costo_usd']:.4f} USD")
                    st.rerun()
                else:
                    st.error(f"❌ {resultado.get('error')}")
        except Exception as e:
            st.warning(f"⚠️ Módulo IA no disponible: {e}")
    
    # ============ TAB 5: CONSULTAS MP ============
    with t_consultas:
        st.markdown("##### 💬 Ronda de consultas y respuestas")
        st.caption(
            "MP tiene un período formal donde los oferentes pueden hacer consultas escritas al mandante. "
            "Aquí registras las consultas que hiciste, las que hicieron otros, y las respuestas que dio el mandante. "
            "Esta info es CRÍTICA para entender ambigüedades en las bases."
        )
        
        # Fechas del período de consultas
        col_fc1, col_fc2 = st.columns(2)
        with col_fc1:
            fecha_inicio = st.date_input(
                "📅 Inicio período de consultas",
                value=None,
                key=f"f_ini_consultas_{proyecto_id}",
                format="DD/MM/YYYY",
                help="Fecha en que MP abrió el período para enviar consultas"
            )
        with col_fc2:
            fecha_fin = st.date_input(
                "📅 Fin período de consultas",
                value=None,
                key=f"f_fin_consultas_{proyecto_id}",
                format="DD/MM/YYYY",
                help="Fecha en que MP cierra el período (después de esto no se aceptan más consultas)"
            )
        
        if st.button("💾 Guardar fechas del período", key="save_fechas_consultas"):
            conn_c = get_connection()
            conn_c.execute(
                "UPDATE aidu_proyectos SET fecha_inicio_consultas=?, fecha_fin_consultas=? WHERE id=?",
                (fecha_inicio.isoformat() if fecha_inicio else None,
                 fecha_fin.isoformat() if fecha_fin else None,
                 proyecto_id)
            )
            conn_c.commit()
            conn_c.close()
            st.success("✅ Fechas guardadas")
            st.rerun()
        
        # Alerta si estamos en período activo
        if fecha_inicio and fecha_fin:
            from datetime import date as _date
            hoy = _date.today()
            if fecha_inicio <= hoy <= fecha_fin:
                dias_quedan = (fecha_fin - hoy).days
                st.success(f"🟢 **Período de consultas ACTIVO** — quedan {dias_quedan} día(s) para enviar consultas formales en MP.")
            elif hoy > fecha_fin:
                st.info(f"🔵 Período cerrado el {fecha_fin}. No se pueden hacer más consultas formales.")
            else:
                dias_para_inicio = (fecha_inicio - hoy).days
                st.warning(f"🟡 Período abre el {fecha_inicio} (en {dias_para_inicio} día(s)).")
        
        st.divider()
        
        # Listar consultas existentes
        conn_c = get_connection()
        consultas = conn_c.execute(
            "SELECT * FROM proy_consultas WHERE proyecto_id = ? ORDER BY fecha_pregunta DESC",
            (proyecto_id,)
        ).fetchall()
        conn_c.close()
        consultas = [dict(c) for c in consultas]
        
        st.markdown(f"##### 📋 Consultas registradas ({len(consultas)})")
        
        # Form para nueva consulta
        with st.expander("➕ Registrar nueva consulta", expanded=len(consultas) == 0):
            nueva_pregunta = st.text_area(
                "Pregunta",
                key=f"nueva_pregunta_{proyecto_id}",
                placeholder="Ej: ¿La memoria de cálculo debe incluir análisis dinámico modal espectral o basta con análisis estático equivalente?",
                height=100
            )
            col_nc1, col_nc2 = st.columns(2)
            with col_nc1:
                autor_consulta = st.text_input("Autor (opcional)", key=f"autor_q_{proyecto_id}", placeholder="Ej: AIDU Op")
            with col_nc2:
                publicada = st.checkbox("Ya publicada en MP", key=f"pub_q_{proyecto_id}")
            
            if st.button("💾 Guardar consulta", type="primary", key="save_consulta"):
                if nueva_pregunta.strip():
                    conn_c = get_connection()
                    conn_c.execute(
                        "INSERT INTO proy_consultas (proyecto_id, pregunta, autor, publicada_en_mp) VALUES (?, ?, ?, ?)",
                        (proyecto_id, nueva_pregunta.strip(), autor_consulta or "AIDU Op", 1 if publicada else 0)
                    )
                    conn_c.commit()
                    conn_c.close()
                    st.success("✅ Consulta registrada")
                    st.rerun()
                else:
                    st.warning("Escribe la pregunta antes de guardar")
        
        # Render de consultas existentes
        if not consultas:
            st.info("📭 Aún no hay consultas registradas. Cuando hagas o veas consultas en MP, regístralas aquí para llevar trazabilidad.")
        else:
            for c in consultas:
                tiene_respuesta = bool(c.get("respuesta"))
                color_pill = "#15803D" if tiene_respuesta else "#D97706"
                bg_pill = "#DCFCE7" if tiene_respuesta else "#FEF3C7"
                label_pill = "✅ Con respuesta" if tiene_respuesta else "⏳ Esperando respuesta"
                
                pub_pill = "📡 Publicada en MP" if c.get("publicada_en_mp") else "📝 Borrador interno"
                pub_color = "#1E40AF" if c.get("publicada_en_mp") else "#64748B"
                
                fecha_q = (c.get("fecha_pregunta") or "")[:10]
                
                st.markdown(
                    f"<div class='aidu-card'>"
                    f"<div style='display:flex; gap:8px; margin-bottom:8px; flex-wrap:wrap;'>"
                    f"<span style='background:{bg_pill}; color:{color_pill}; padding:3px 10px; border-radius:6px; font-size:11px; font-weight:600;'>{label_pill}</span>"
                    f"<span style='background:{pub_color}15; color:{pub_color}; padding:3px 10px; border-radius:6px; font-size:11px; font-weight:600;'>{pub_pill}</span>"
                    f"<span style='font-size:11px; color:#94A3B8; margin-left:auto;'>{c.get('autor') or '—'} · {fecha_q}</span>"
                    f"</div>"
                    f"<div style='font-size:13px; color:#0F172A; margin-bottom:8px; line-height:1.5;'>"
                    f"<strong>P:</strong> {c['pregunta']}"
                    f"</div>"
                    + (f"<div style='font-size:13px; color:#15803D; padding:10px 14px; background:#F0FDF4; border-left:3px solid #15803D; border-radius:6px; line-height:1.5;'>"
                       f"<strong>R:</strong> {c['respuesta']}</div>"
                       if tiene_respuesta else
                       "<div style='font-size:12px; color:#94A3B8; font-style:italic;'>Sin respuesta del mandante todavía</div>")
                    + f"</div>",
                    unsafe_allow_html=True
                )
                
                # Form para responder
                if not tiene_respuesta:
                    with st.expander(f"✍️ Registrar respuesta del mandante", expanded=False):
                        respuesta_txt = st.text_area(
                            "Respuesta",
                            key=f"resp_{c['id']}",
                            height=80
                        )
                        if st.button("💾 Guardar respuesta", key=f"save_resp_{c['id']}"):
                            if respuesta_txt.strip():
                                conn_c = get_connection()
                                conn_c.execute(
                                    "UPDATE proy_consultas SET respuesta=?, fecha_respuesta=datetime('now', 'localtime') WHERE id=?",
                                    (respuesta_txt.strip(), c["id"])
                                )
                                conn_c.commit()
                                conn_c.close()
                                st.success("✅ Respuesta registrada")
                                st.rerun()
    
    # ============ TAB 6: EQUIPO & HH ============
    with t_equipo:
        st.markdown("##### 👥 Estimación de equipo y horas hombre")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("###### Estimado")
            hh_ig_est = st.number_input("HH Ignacio (estimadas)", value=p.get("hh_ignacio_estimado") or 40, min_value=0, key="hh_ig_est")
            hh_jo_est = st.number_input("HH Jorella (estimadas)", value=p.get("hh_jorella_estimado") or 20, min_value=0, key="hh_jo_est")
        with col2:
            st.markdown("###### Real")
            hh_ig_real = st.number_input("HH Ignacio (real)", value=p.get("hh_ignacio_real") or 0, min_value=0, key="hh_ig_real")
            hh_jo_real = st.number_input("HH Jorella (real)", value=p.get("hh_jorella_real") or 0, min_value=0, key="hh_jo_real")
        
        if st.button("💾 Guardar HH", type="primary"):
            conn = get_connection()
            conn.execute(
                "UPDATE aidu_proyectos SET hh_ignacio_estimado=?, hh_jorella_estimado=?, "
                "hh_ignacio_real=?, hh_jorella_real=? WHERE id=?",
                (hh_ig_est, hh_jo_est, hh_ig_real, hh_jo_real, proyecto_id)
            )
            conn.commit()
            conn.close()
            st.success("✅ Guardado")
            st.rerun()
        
        try:
            from app.core.configuracion import obtener_config
            cfg = obtener_config()
            costo_total_est = (hh_ig_est + hh_jo_est) * cfg.costo_hora_total
            costo_total_real = (hh_ig_real + hh_jo_real) * cfg.costo_hora_total
            
            st.divider()
            ce1, ce2, ce3 = st.columns(3)
            ce1.metric("Costo estimado", formato_clp(costo_total_est))
            ce2.metric("Costo real", formato_clp(costo_total_real))
            if hh_ig_est + hh_jo_est > 0:
                pct = ((hh_ig_real + hh_jo_real) / (hh_ig_est + hh_jo_est)) * 100
                ce3.metric("% Completado", f"{pct:.0f}%")
        except Exception:
            pass
    
    # ============ TAB 6: PAQUETE ============
    with t_paquete:
        st.markdown("##### 📦 Paquete de oferta")
        st.info("🚧 Generador de paquete Word/Excel disponible próximamente. Por ahora puedes preparar la oferta manualmente con los insumos de los demás tabs.")
        
        st.markdown("###### Insumos disponibles para tu oferta")
        st.markdown("""
- 📊 **Comparables homologados** → rango de precios objetivo (tab Comparables)
- 💰 **Descuento óptimo** → cuánto descontar del referencial (tab Inteligencia precios)
- 🤖 **Análisis IA** → requisitos eliminatorios, riesgos, plazos (tab Análisis IA)
- 👥 **HH estimadas** → costo proyecto (tab Equipo & HH)
""")
    
    # ============ TAB 7: BITÁCORA ============
    with t_bitacora:
        st.markdown("##### 📝 Bitácora del proyecto")
        
        # Campo simple de notas (sin tabla bitacora separada que no existe en BD)
        notas_actuales = p.get("notas") or ""
        
        nuevas_notas = st.text_area(
            "Notas y comentarios del proyecto",
            value=notas_actuales,
            height=200,
            key=f"notas_{proyecto_id}"
        )
        
        if st.button("💾 Guardar notas", type="primary"):
            conn = get_connection()
            conn.execute("UPDATE aidu_proyectos SET notas=? WHERE id=?", (nuevas_notas, proyecto_id))
            conn.commit()
            conn.close()
            st.success("✅ Notas guardadas")
            st.rerun()
        
        st.divider()
        st.caption(f"📅 Última modificación: {p.get('fecha_modificacion') or p.get('fecha_creacion') or '—'}")


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
    
    # Navegación basada en query params (permite acciones rápidas funcionales)
    NAV_OPCIONES = [
        ("🏠 Dashboard",       "dashboard"),
        ("─── EMBUDO ───",     None),
        ("🔍 1. Buscar",       "buscar"),
        ("📂 2. Cartera",      "cartera"),
        ("🔬 3. Estudio",      "estudio"),
        ("📝 4. Ofertar",      "ofertar"),
        ("📤 5. Subir a MP",   "subir"),
        ("─── INTELIGENCIA ───", None),
        ("📊 Inteligencia",    "intel"),
        ("🤖 Análisis IA",     "ia"),
        ("─── ADMIN ───",      None),
        ("⚙️ Configuración",   "config"),
        ("🛠️ Sistema",         "sistema"),
    ]
    
    # Leer query param actual (fuente de verdad)
    nav_actual = st.query_params.get("nav", "dashboard")
    
    # Encontrar el label que coincide con el query param
    label_actual = next(
        (label for label, key in NAV_OPCIONES if key == nav_actual),
        "🏠 Dashboard"
    )
    
    # Calcular índice
    labels_solo = [label for label, _ in NAV_OPCIONES]
    try:
        idx_inicial = labels_solo.index(label_actual)
    except ValueError:
        idx_inicial = 0
    
    seccion = st.radio(
        "Navegación",
        labels_solo,
        index=idx_inicial,
        label_visibility="collapsed",
        key=f"nav_radio_{nav_actual}",  # Key dinámico = se reinicia con query_params
    )
    
    # Si el usuario cambió la selección con el radio, actualizar query param
    nuevo_key = next((k for label, k in NAV_OPCIONES if label == seccion and k), None)
    if nuevo_key and nuevo_key != nav_actual:
        st.query_params["nav"] = nuevo_key
        st.rerun()
    
    # Saltar separadores
    if seccion.startswith("───"):
        seccion = "🏠 Dashboard"
    
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
    
    # Info BD: contar licitaciones en BD para mostrar persistencia
    try:
        _conn_bd = get_connection()
        _bd_total = _conn_bd.execute(
            "SELECT COUNT(*) FROM mp_licitaciones_vigentes"
        ).fetchone()[0] if _tabla_existe(_conn_bd, "mp_licitaciones_vigentes") else 0
        _bd_hist = _conn_bd.execute(
            "SELECT COUNT(*) FROM mp_licitaciones_adj"
        ).fetchone()[0] if _tabla_existe(_conn_bd, "mp_licitaciones_adj") else 0
        _conn_bd.close()
    except Exception:
        _bd_total, _bd_hist = 0, 0
    
    st.markdown(f"""
    <div style='font-size:10px; color:#94A3B8; padding:0 8px;'>
        <div style='margin-bottom:8px;'>
            <div style='font-weight:600; color:#475569; margin-bottom:4px;'>💾 Base de datos local</div>
            <div>Vigentes: <strong style='color:#1D4ED8;'>{_bd_total:,}</strong></div>
            <div>Histórico: <strong style='color:#1D4ED8;'>{_bd_hist:,}</strong></div>
        </div>
        <div>Última sync: <strong style='color:#475569;'>{ult_act}</strong></div>
        <div style='margin-top:6px; font-size:9px; color:#CBD5E1;'>BD persistente · sync diario 7am</div>
        <div style='margin-top:6px;'><a href='https://github.com/ividiellagonzalez-ship-it/aidu-op' target='_blank' style='color:#3B82F6; text-decoration:none;'>📦 Ver código →</a></div>
    </div>
    """, unsafe_allow_html=True)


# ============================================================
# CONTENIDO PRINCIPAL — según sección elegida
# ============================================================

# Booleanos del nuevo embudo (1→2→3→4→5)
tab_dashboard = (seccion == "🏠 Dashboard")
tab_buscar = (seccion == "🔍 1. Buscar")
tab_cartera = (seccion == "📂 2. Cartera")
tab_estudio = (seccion == "🔬 3. Estudio")
tab_ofertar = (seccion == "📝 4. Ofertar")
tab_subir = (seccion == "📤 5. Subir a MP")

# Inteligencia
tab_intel = (seccion == "📊 Inteligencia")
tab_ia = (seccion == "🤖 Análisis IA")

# Admin
tab_config = (seccion == "⚙️ Configuración")
tab_sistema = (seccion == "🛠️ Sistema")

# Compatibilidad: tab_hoy ya no existe, va integrado en Dashboard
tab_hoy = False


# ====================
# TAB 1: CARTERA
# ====================
# ============================================================
# TAB: 🔥 HOY (v7 — licitaciones publicadas en últimas 24h)
# ============================================================
# ============================================================
# 🏠 DASHBOARD — Vista de inicio con embudo visible
# ============================================================
if tab_dashboard:
    # ================== HEADER CON CONTEXTO ==================
    from datetime import datetime as _dt
    hora_actual = _dt.now().strftime("%H:%M")
    fecha_hoy = _dt.now().strftime("%A %d de %B")
    
    st.markdown(f"""
    <div style="margin-bottom:24px;">
        <h1 style="margin:0; font-size:28px; color:#0F172A;">👋 Buen día, Ignacio</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">{fecha_hoy} · {hora_actual} · ¿Qué licitaciones merecen tu atención hoy?</p>
    </div>
    """, unsafe_allow_html=True)
    
    # ================== SECCIÓN 1: ¿QUÉ DECIDIR HOY? ==================
    conn = get_connection()
    try:
        n_buscar = conn.execute(
            "SELECT COUNT(*) FROM mp_licitaciones_vigentes WHERE estado IN ('Publicada','Recepcion de Ofertas','Recepción de Ofertas')"
        ).fetchone()[0] if _tabla_existe(conn, "mp_licitaciones_vigentes") else 0
        
        n_cartera = conn.execute("SELECT COUNT(*) FROM aidu_proyectos WHERE estado = 'EN_CARTERA'").fetchone()[0]
        n_estudio = conn.execute("SELECT COUNT(*) FROM aidu_proyectos WHERE estado = 'EN_ESTUDIO'").fetchone()[0]
        n_oferta  = conn.execute("SELECT COUNT(*) FROM aidu_proyectos WHERE estado = 'EN_OFERTA'").fetchone()[0]
        n_subir   = conn.execute("SELECT COUNT(*) FROM aidu_proyectos WHERE estado = 'LISTO_SUBIR'").fetchone()[0]
        
        # Cierran ≤3 días en TODOS los estados activos
        from datetime import date as _date, timedelta as _td
        limite = (_date.today() + _td(days=3)).isoformat()
        n_urgentes = conn.execute(
            "SELECT COUNT(*) FROM aidu_proyectos WHERE estado IN ('EN_CARTERA','EN_ESTUDIO','EN_OFERTA','LISTO_SUBIR') AND fecha_cierre <= ? AND fecha_cierre IS NOT NULL",
            (limite,)
        ).fetchone()[0]
    finally:
        conn.close()
    
    st.markdown("##### 🎯 Decisiones que requieren tu atención")
    
    col_d1, col_d2, col_d3, col_d4 = st.columns(4)
    
    with col_d1:
        st.markdown(f"""
        <div style='background:linear-gradient(135deg, #DBEAFE 0%, white 100%); padding:18px 16px; border-radius:14px; border-top:3px solid #1E40AF;'>
            <div style='font-size:11px; color:#1E40AF; text-transform:uppercase; letter-spacing:0.5px; font-weight:700;'>🔍 Para revisar</div>
            <div style='font-size:36px; font-weight:800; color:#1E40AF; line-height:1; margin:6px 0;'>{n_buscar}</div>
            <div style='font-size:12px; color:#64748B;'>Licitaciones vigentes en MP</div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("→ Ir a Buscar", key="ir_buscar", use_container_width=True):
            st.query_params["nav"] = "buscar"
            st.rerun()
    
    with col_d2:
        urgent_color = "#DC2626" if n_urgentes > 0 else "#15803D"
        urgent_bg = "#FEE2E2" if n_urgentes > 0 else "#DCFCE7"
        st.markdown(f"""
        <div style='background:linear-gradient(135deg, {urgent_bg} 0%, white 100%); padding:18px 16px; border-radius:14px; border-top:3px solid {urgent_color};'>
            <div style='font-size:11px; color:{urgent_color}; text-transform:uppercase; letter-spacing:0.5px; font-weight:700;'>⏰ Cierran ≤3 días</div>
            <div style='font-size:36px; font-weight:800; color:{urgent_color}; line-height:1; margin:6px 0;'>{n_urgentes}</div>
            <div style='font-size:12px; color:#64748B;'>Proyectos activos urgentes</div>
        </div>
        """, unsafe_allow_html=True)
        if n_urgentes > 0:
            if st.button("→ Ver urgentes", key="ir_urgentes", use_container_width=True):
                st.query_params["nav"] = "estudio" if n_estudio > 0 else "cartera"
                st.rerun()
    
    with col_d3:
        st.markdown(f"""
        <div style='background:linear-gradient(135deg, #FED7AA 0%, white 100%); padding:18px 16px; border-radius:14px; border-top:3px solid #9A3412;'>
            <div style='font-size:11px; color:#9A3412; text-transform:uppercase; letter-spacing:0.5px; font-weight:700;'>📝 En oferta</div>
            <div style='font-size:36px; font-weight:800; color:#9A3412; line-height:1; margin:6px 0;'>{n_oferta}</div>
            <div style='font-size:12px; color:#64748B;'>Preparando propuesta</div>
        </div>
        """, unsafe_allow_html=True)
        if n_oferta > 0:
            if st.button("→ Ir a Ofertar", key="ir_oferta", use_container_width=True):
                st.query_params["nav"] = "ofertar"
                st.rerun()
    
    with col_d4:
        st.markdown(f"""
        <div style='background:linear-gradient(135deg, #E9D5FF 0%, white 100%); padding:18px 16px; border-radius:14px; border-top:3px solid #6B21A8;'>
            <div style='font-size:11px; color:#6B21A8; text-transform:uppercase; letter-spacing:0.5px; font-weight:700;'>📤 Listo subir</div>
            <div style='font-size:36px; font-weight:800; color:#6B21A8; line-height:1; margin:6px 0;'>{n_subir}</div>
            <div style='font-size:12px; color:#64748B;'>Para cargar en MP</div>
        </div>
        """, unsafe_allow_html=True)
        if n_subir > 0:
            if st.button("→ Ir a Subir", key="ir_subir", use_container_width=True):
                st.query_params["nav"] = "subir"
                st.rerun()
    
    st.divider()
    
    # ================== SECCIÓN 2: EMBUDO RESUMIDO ==================
    st.markdown("##### 🚀 Embudo Comercial — vista compacta")
    st.caption("Cantidad de proyectos activos por etapa. Click en una etapa para verla en detalle.")
    
    conn = get_connection()
    try:
        embudo_counts = {}
        for estado in ["EN_CARTERA", "EN_ESTUDIO", "EN_OFERTA", "LISTO_SUBIR"]:
            row = conn.execute(
                "SELECT COUNT(*) as n, SUM(monto_referencial) as monto FROM aidu_proyectos WHERE estado = ?",
                (estado,)
            ).fetchone()
            embudo_counts[estado] = {"n": row["n"] or 0, "monto": row["monto"] or 0}
        
        adj_row = conn.execute(
            "SELECT COUNT(*) as n, SUM(monto_referencial) as monto FROM aidu_proyectos WHERE estado = 'ADJUDICADO'"
        ).fetchone()
        adjudicadas = {"n": adj_row["n"] or 0, "monto": adj_row["monto"] or 0}
    finally:
        conn.close()
    
    embudo_def = [
        ("EN_CARTERA",  "📂 Cartera",    "cartera",  "#1E40AF", "#DBEAFE"),
        ("EN_ESTUDIO",  "🔬 Estudio",    "estudio",  "#0E7490", "#CFFAFE"),
        ("EN_OFERTA",   "📝 Ofertar",    "ofertar",  "#9A3412", "#FED7AA"),
        ("LISTO_SUBIR", "📤 Subir a MP", "subir",    "#6B21A8", "#E9D5FF"),
    ]
    
    cols = st.columns(4)
    for i, (estado, label, nav_key, color, bg) in enumerate(embudo_def):
        data = embudo_counts.get(estado, {"n": 0, "monto": 0})
        cols[i].markdown(
            f"<div style='padding:14px 12px; background:linear-gradient(135deg, {bg} 0%, white 100%); border-radius:10px; text-align:center; border-top:2px solid {color};'>"
            f"<div style='font-size:12px; font-weight:600; color:{color};'>{label}</div>"
            f"<div style='font-size:32px; font-weight:800; color:{color}; line-height:1; margin:6px 0;'>{data['n']}</div>"
            f"<div style='font-size:11px; color:#64748B;'>{formato_clp(data['monto'])}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    
    if adjudicadas["n"] > 0:
        st.success(f"🏆 **{adjudicadas['n']} licitaciones adjudicadas históricas** · Total {formato_clp(adjudicadas['monto'])}")
    
    st.divider()
    
    # ================== SECCIÓN 3: SINCRONIZACIÓN MP CON OPCIONES ==================
    st.markdown("##### 📡 Sincronizar con Mercado Público")
    st.caption("Trae las últimas licitaciones publicadas. **Más días = más datos pero más tiempo.**")
    
    col_sync1, col_sync2 = st.columns([3, 1])
    
    with col_sync1:
        sync_dias = st.select_slider(
            "Rango de descarga",
            options=[1, 2, 3, 7, 14, 30],
            value=3,
            format_func=lambda d: f"{d} día{'s' if d > 1 else ''}",
            help="Cuántos días hacia atrás traer licitaciones nuevas. 1d = ~10s, 7d = ~30s, 30d = ~2min."
        )
        
        # Estimaciones de tiempo
        tiempo_est = {1: "~10 seg", 2: "~15 seg", 3: "~20 seg", 7: "~30 seg", 14: "~60 seg", 30: "~120 seg"}
        precision = "Precisión: solo HOY" if sync_dias == 1 else f"Precisión: últimos {sync_dias} días"
        
        st.caption(f"⏱️ Tiempo estimado: **{tiempo_est.get(sync_dias, '~?')}** · {precision}")
    
    with col_sync2:
        st.write("")
        st.write("")
        if st.button("🔄 Sincronizar", use_container_width=True, type="primary", key="sync_dashboard_v14"):
            try:
                from app.core.descarga_diaria import ejecutar_descarga
                with st.spinner(f"Descargando licitaciones de los últimos {sync_dias} días..."):
                    res = ejecutar_descarga(dias_atras=sync_dias)
                    st.success(f"✅ {res['nuevas']} nuevas · {res['categorizadas_aidu']} con match AIDU")
                    st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
    
    # Estado en vivo
    try:
        from app.core.descarga_diaria import stats_vigentes
        st_vig = stats_vigentes()
        
        col_h1, col_h2, col_h3, col_h4 = st.columns(4)
        col_h1.metric("📡 Vigentes total", f"{st_vig['total_vigentes']:,}", help="Licitaciones publicadas que aún no cierran. Se actualizan al sincronizar.")
        col_h2.metric("🟢 Publicadas 24h", st_vig["publicadas_24h"], help="Licitaciones publicadas en las últimas 24 horas.")
        col_h3.metric("🔴 Cierran ≤3d", st_vig["cierran_proximos_3_dias"], help="Licitaciones que cierran en los próximos 3 días. Si te interesan, debes ofertar pronto.")
        
        # Match AIDU: explicar qué es y por qué puede ser 0
        col_h4.metric(
            "🎯 Match AIDU",
            st_vig["con_match_aidu"],
            help=(
                "Licitaciones cuya descripción matchea con tus servicios AIDU (CE-01 a CE-06, GP-04, etc.). "
                "Si es 0: o no se ha corrido categorización masiva, o no hay vigentes que matcheen tu perfil. "
                "Tip: ve a Buscar — usa el filtro por categoría manualmente para ver más opciones."
            )
        )
        
        if st_vig["con_match_aidu"] == 0 and st_vig["total_vigentes"] > 0:
            st.info(
                "💡 **¿Por qué Match AIDU = 0?** La categorización automática (que detecta si una licitación matchea tus servicios) "
                "aún no se ha corrido sobre las licitaciones nuevas. Ve a la sección **Buscar** y usa los filtros manualmente — "
                "ahí verás todas las oportunidades disponibles."
            )
    except Exception:
        st.info("Configura el ticket de Mercado Público en Sistema para activar la sincronización automática.")
    
    st.divider()
    
    # ================== SECCIÓN 4: PIPELINE FINANCIERO CON EXPLICACIÓN ==================
    st.markdown("##### 💰 Pipeline financiero")
    
    with st.expander("💡 ¿Cómo se calcula el pipeline?", expanded=False):
        st.markdown("""
**Pipeline total**: Suma del monto referencial de TODOS tus proyectos activos (Cartera + Estudio + Ofertar + Subir).

**Valor esperado**: Pipeline ponderado por probabilidad de cierre según etapa:
- 📂 Cartera: 10% probabilidad
- 🔬 Estudio: 25% probabilidad
- 📝 Ofertar: 50% probabilidad
- 📤 Subir: 75% probabilidad

**Ingresos proyectados**: Valor esperado × margen objetivo configurado (default 22%).

⚠️ Estos números son **proyecciones estadísticas**, no certezas. Mientras más histórico real tengas en AIDU, más se calibran.
""")
    
    try:
        from app.core.inteligencia_avanzada import forecast_pipeline_90d
        f = forecast_pipeline_90d()
        
        cm1, cm2, cm3 = st.columns(3)
        cm1.metric(
            "Pipeline total",
            formato_clp(f["valor_pipeline_total_clp"]),
            help="Suma de monto referencial de proyectos activos en tu embudo (Cartera + Estudio + Ofertar + Subir)."
        )
        cm2.metric(
            "Valor esperado",
            formato_clp(f["valor_esperado_clp"]),
            help="Pipeline ponderado por probabilidad de cierre según etapa (10/25/50/75%)."
        )
        cm3.metric(
            "Ingresos proyectados",
            formato_clp(f["ingresos_esperados_clp"]),
            help=f"Valor esperado × margen objetivo {f['margen_aplicado_pct']:.0f}%."
        )
    except Exception:
        st.caption("📭 Pipeline disponible cuando tengas proyectos activos.")
    
    st.divider()
    
    # ================== SECCIÓN 5: ÚLTIMAS OPORTUNIDADES (MEJORADO) ==================
    col_ult_t, col_ult_b = st.columns([3, 1])
    col_ult_t.markdown("##### 🆕 Últimas oportunidades publicadas en MP")
    col_ult_t.caption("Las 5 más recientes ordenadas por fecha. Click 'Ver en MP' o 'Ver ficha' para detalles.")
    
    try:
        from app.core.descarga_diaria import listar_vigentes
        ultimas = listar_vigentes(limit=5)
        
        with col_ult_b:
            if st.button("Ver todas →", use_container_width=True, key="ver_todas_ops_dashboard"):
                st.query_params["nav"] = "buscar"
                st.rerun()
        
        if not ultimas:
            st.caption("📭 Sin licitaciones nuevas en BD. Click '🔄 Sincronizar' arriba.")
        else:
            for v in ultimas:
                dias_cierre = v.get("dias_para_cierre")
                if dias_cierre is not None and dias_cierre <= 3:
                    border_color = "#DC2626"
                    urgencia = f"🔴 Cierra en {dias_cierre}d"
                elif dias_cierre is not None and dias_cierre <= 7:
                    border_color = "#D97706"
                    urgencia = f"🟡 Cierra en {dias_cierre}d"
                elif dias_cierre is not None:
                    border_color = "#15803D"
                    urgencia = f"🟢 Cierra en {dias_cierre}d"
                else:
                    border_color = "#94A3B8"
                    urgencia = "Sin fecha cierre"
                
                cat_aidu = v.get("cod_servicio_aidu") or "—"
                organismo_v = v.get("organismo") or "—"
                region_v = v.get("region") or "—"
                monto_v = v.get("monto_referencial") or 0
                url_mp_v = url_licitacion_mp(v['codigo_externo'])
                
                # Card mejorado con MUCHO más contexto
                st.markdown(
                    f"<div class='aidu-card' style='border-left:4px solid {border_color};'>"
                    f"<div style='display:flex; justify-content:space-between; align-items:start; gap:16px;'>"
                    f"<div style='flex:1; min-width:0;'>"
                    f"<div style='display:flex; gap:8px; flex-wrap:wrap; margin-bottom:6px;'>"
                    f"<span class='aidu-pill aidu-pill-blue'>{cat_aidu}</span>"
                    f"<span style='font-family:JetBrains Mono,monospace; font-size:11px; color:#94A3B8; padding:2px 0;'>{v['codigo_externo']}</span>"
                    f"</div>"
                    f"<div style='font-size:14px; font-weight:600; color:#0F172A; margin-bottom:6px; line-height:1.4;'>{v['nombre']}</div>"
                    f"<div style='font-size:12px; color:#64748B;'>"
                    f"🏛️ {organismo_v} · 📍 {region_v}"
                    f"</div>"
                    f"</div>"
                    f"<div style='text-align:right; min-width:170px;'>"
                    f"<div style='font-size:10px; color:#64748B; text-transform:uppercase; letter-spacing:0.5px;'>Monto referencial</div>"
                    f"<div style='font-size:18px; font-weight:700; color:#1E40AF;'>{formato_clp(monto_v) if monto_v else '—'}</div>"
                    f"<div style='font-size:11px; color:{border_color}; font-weight:600; margin:4px 0;'>{urgencia}</div>"
                    f"<a href='{url_mp_v}' target='_blank' style='display:inline-block; padding:5px 12px; background:#1E40AF; color:white; border-radius:6px; text-decoration:none; font-size:11px; font-weight:600;'>🔗 Ver en MP</a>"
                    f"</div>"
                    f"</div>"
                    f"</div>",
                    unsafe_allow_html=True
                )
    except Exception:
        pass


def _tabla_existe(conn, nombre):
    """Helper local: verifica si una tabla existe."""
    try:
        r = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (nombre,)
        ).fetchone()
        return r is not None
    except Exception:
        return False


# ============================================================
# TAB: 🔥 HOY (LEGACY - ya no usado, se redirige a Dashboard)
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
# ============================================================
# TAB: 🤖 ANÁLISIS IA (v8 — análisis de bases técnicas con Claude)
# ============================================================
if tab_ia:
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:28px;">🤖 Análisis IA de Bases Técnicas</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">Sube un PDF de bases y Claude extrae requisitos, plazos, riesgos y te da una recomendación</p>
    </div>
    """, unsafe_allow_html=True)
    
    try:
        from app.core.analisis_bases import analizar_pdf_bases, obtener_ultimo_analisis
        
        col_up1, col_up2 = st.columns([3, 1])
        
        with col_up1:
            codigo_lic = st.text_input(
                "Código de licitación",
                placeholder="Ej: 2641-156-L125",
                help="Identificador de Mercado Público para guardar el análisis"
            )
            
            archivo = st.file_uploader(
                "📄 Sube el PDF de las bases técnicas",
                type=["pdf"],
                help="PDF con texto (no escaneado). Máx 80k caracteres"
            )
        
        with col_up2:
            st.markdown("##### 💰 Costo estimado")
            st.markdown("""
            <div style='padding:12px; background:#F8FAFC; border-radius:8px; border:1px solid #E2E8F0;'>
                <div style='font-size:11px; color:#64748B;'>Por análisis típico</div>
                <div style='font-size:22px; font-weight:700; color:#1E40AF;'>~$0.05 USD</div>
                <div style='font-size:11px; color:#64748B;'>~30 segundos</div>
            </div>
            """, unsafe_allow_html=True)
        
        if archivo and codigo_lic:
            # Verificar si ya hay análisis previo
            previo = obtener_ultimo_analisis(codigo_lic)
            
            if previo:
                st.info(f"📦 Hay un análisis previo del {previo['fecha_analisis']}. Costo previo: ${previo['costo_usd']:.4f} USD")
                col_b1, col_b2 = st.columns(2)
                ver_previo = col_b1.button("👁️ Ver análisis previo", use_container_width=True)
                reanalizar = col_b2.button("🔄 Re-analizar (gastar tokens)", use_container_width=True, type="primary")
            else:
                ver_previo = False
                reanalizar = st.button("🚀 Analizar con Claude", use_container_width=True, type="primary")
            
            if ver_previo and previo:
                st.session_state["ia_resultado_actual"] = previo["resultado"]
                st.session_state["ia_meta"] = {"from_cache": True, "fecha": previo["fecha_analisis"]}
            
            if reanalizar:
                with st.spinner("🤖 Claude está leyendo las bases técnicas..."):
                    pdf_bytes = archivo.read()
                    resultado = analizar_pdf_bases(
                        pdf_bytes,
                        codigo_licitacion=codigo_lic,
                        forzar_reanalisis=(previo is not None)
                    )
                
                if resultado["ok"]:
                    st.session_state["ia_resultado_actual"] = resultado["resultado"]
                    st.session_state["ia_meta"] = resultado["meta"]
                    st.success(f"✅ Análisis completado · Costo: ${resultado['meta'].get('costo_usd', 0):.4f} USD · {resultado['meta'].get('tokens_input', 0):,} tokens in / {resultado['meta'].get('tokens_output', 0):,} out")
                else:
                    st.error(f"❌ Error: {resultado.get('error', 'Desconocido')}")
        
        # Mostrar resultado si existe
        if "ia_resultado_actual" in st.session_state:
            r = st.session_state["ia_resultado_actual"]
            
            st.divider()
            
            # === RECOMENDACIÓN PRINCIPAL ===
            rec = r.get("recomendacion", {})
            postular = rec.get("postular", "incierto")
            confianza = rec.get("confianza", 0)
            
            color_rec = "#15803D" if postular == "si" else "#DC2626" if postular == "no" else "#D97706"
            label_rec = "✅ POSTULAR" if postular == "si" else "❌ NO POSTULAR" if postular == "no" else "⚠️ CON RESERVAS"
            
            st.markdown(f"""
            <div style='padding:24px; background:linear-gradient(135deg, {color_rec}15 0%, white 60%); border-left:5px solid {color_rec}; border-radius:12px; margin-bottom:24px;'>
                <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;'>
                    <div style='font-size:24px; font-weight:800; color:{color_rec};'>{label_rec}</div>
                    <div style='text-align:right;'>
                        <div style='font-size:11px; color:#64748B;'>Confianza Claude</div>
                        <div style='font-size:28px; font-weight:800; color:{color_rec};'>{confianza}%</div>
                    </div>
                </div>
                <div style='font-size:14px; color:#334155; line-height:1.6;'>{r.get('resumen_ejecutivo', '')}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # === RAZONES ===
            razones = rec.get("razones_principales", [])
            if razones:
                st.markdown("##### 🎯 Razones principales")
                for i, razon in enumerate(razones, 1):
                    st.markdown(f"""
                    <div style='padding:10px 14px; background:#F8FAFC; border-left:3px solid {color_rec}; border-radius:6px; margin-bottom:6px;'>
                        <strong>{i}.</strong> {razon}
                    </div>
                    """, unsafe_allow_html=True)
            
            # === DATOS CLAVE ===
            col_d1, col_d2, col_d3 = st.columns(3)
            
            monto_ref = r.get("monto_referencial_clp")
            if monto_ref:
                col_d1.metric("Monto referencial", formato_clp(monto_ref))
            
            plazo = r.get("plazo_ejecucion_dias")
            if plazo:
                col_d2.metric("Plazo ejecución", f"{plazo} días")
            
            comp = r.get("estimacion_competencia", {})
            nivel = comp.get("nivel_esperado", "—")
            col_d3.metric("Competencia esperada", nivel.upper())
            
            # === REQUISITOS ELIMINATORIOS ===
            requisitos = r.get("requisitos_eliminatorios", [])
            if requisitos:
                st.markdown("##### 📋 Requisitos eliminatorios")
                for req in requisitos:
                    puede = req.get("puede_cumplir", "incierto")
                    icon = "✅" if puede == "si" else "❌" if puede == "no" else "⚠️"
                    color_req = "#15803D" if puede == "si" else "#DC2626" if puede == "no" else "#D97706"
                    st.markdown(f"""
                    <div style='padding:10px 14px; background:white; border:1px solid #E2E8F0; border-left:3px solid {color_req}; border-radius:6px; margin-bottom:6px;'>
                        <div style='display:flex; justify-content:space-between;'>
                            <span><strong>{icon} {req.get('requisito', '—')}</strong></span>
                            <span style='font-size:11px; color:{color_req}; font-weight:600;'>{puede.upper()}</span>
                        </div>
                        <div style='font-size:12px; color:#64748B; margin-top:4px;'>{req.get('comentario', '')}</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # === PLAZOS CRÍTICOS ===
            plazos = r.get("plazos_criticos", [])
            if plazos:
                st.markdown("##### ⏰ Plazos críticos")
                for p in plazos:
                    crit = p.get("criticidad", "media")
                    color_p = "#DC2626" if crit == "alta" else "#D97706" if crit == "media" else "#15803D"
                    st.markdown(f"""
                    <div style='padding:8px 14px; background:#F8FAFC; border-left:3px solid {color_p}; border-radius:6px; margin-bottom:4px;'>
                        <strong>{p.get('hito', '—')}</strong> · {p.get('fecha_o_dias', '—')} · <span style='color:{color_p}; font-weight:600;'>{crit.upper()}</span>
                    </div>
                    """, unsafe_allow_html=True)
            
            # === GARANTÍAS ===
            garantias = r.get("garantias_exigidas", [])
            if garantias:
                st.markdown("##### 💰 Garantías exigidas")
                cols_g = st.columns(min(len(garantias), 3))
                for i, g in enumerate(garantias):
                    cols_g[i % 3].markdown(f"""
                    <div style='padding:14px; background:white; border:1px solid #E2E8F0; border-radius:8px; text-align:center;'>
                        <div style='font-size:11px; color:#64748B; text-transform:uppercase;'>{g.get('tipo', '—')}</div>
                        <div style='font-size:18px; font-weight:700; color:#1E40AF;'>{g.get('monto_uf_o_pct', '—')}</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # === CRITERIOS EVALUACIÓN ===
            criterios = r.get("criterios_evaluacion", [])
            if criterios:
                st.markdown("##### 📊 Criterios de evaluación")
                for c in criterios:
                    pond = c.get("ponderacion_pct", 0)
                    st.markdown(f"""
                    <div style='padding:10px 14px; background:white; border:1px solid #E2E8F0; border-radius:6px; margin-bottom:4px;'>
                        <div style='display:flex; justify-content:space-between;'>
                            <span><strong>{c.get('criterio', '—')}</strong></span>
                            <span style='font-weight:700; color:#1E40AF;'>{pond}%</span>
                        </div>
                        <div style='height:4px; background:#F1F5F9; border-radius:2px; margin-top:6px; overflow:hidden;'>
                            <div style='height:100%; width:{pond}%; background:#1E40AF; border-radius:2px;'></div>
                        </div>
                        <div style='font-size:11px; color:#64748B; margin-top:4px;'>{c.get('comentario', '')}</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # === CLÁUSULAS PROBLEMÁTICAS ===
            clausulas = r.get("clausulas_problematicas", [])
            if clausulas:
                st.markdown("##### 🚨 Cláusulas problemáticas detectadas")
                for cl in clausulas:
                    riesgo = cl.get("riesgo", "medio")
                    color_r = "#DC2626" if riesgo == "alto" else "#D97706" if riesgo == "medio" else "#94A3B8"
                    st.markdown(f"""
                    <div style='padding:12px 14px; background:#FEF2F2; border-left:3px solid {color_r}; border-radius:6px; margin-bottom:6px;'>
                        <div style='font-size:13px; font-weight:600; color:#0F172A;'>⚠️ {cl.get('clausula', '—')}</div>
                        <div style='font-size:12px; color:#64748B; margin-top:4px;'>{cl.get('razon', '')}</div>
                        <div style='font-size:10px; color:{color_r}; font-weight:600; margin-top:4px;'>RIESGO: {riesgo.upper()}</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # === ALERTAS LEGALES ===
            alertas = r.get("alertas_legales", [])
            if alertas:
                st.markdown("##### ⚖️ Alertas legales")
                for a in alertas:
                    st.warning(a)
            
            # === ACCIONES PREVIAS ===
            acciones = rec.get("acciones_previas_necesarias", [])
            if acciones:
                st.markdown("##### 📝 Acciones previas necesarias")
                for a in acciones:
                    st.info(f"☐ {a}")
            
            # JSON descargable
            with st.expander("🔍 Ver JSON completo del análisis"):
                st.json(r)
    
    except Exception as e:
        st.error(f"Error en módulo de análisis IA: {e}")
        with st.expander("Detalle"):
            import traceback
            st.code(traceback.format_exc())


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
    <div style="margin-bottom:20px;">
        <h1 style="margin:0; font-size:28px; color:#0F172A;">📂 Cartera · ¿Vamos o no vamos?</h1>
        <p style="margin:6px 0 0; font-size:14px; color:#64748B;">
            Tu sala de decisiones. Cada tarjeta es una licitación esperando que decidas si <strong>avanza a Estudio</strong> o se <strong>descarta</strong>.
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Macro flow indicator
    st.markdown("""
    <div class="macro-flow">
        <div class="macro-step">1. 🔍 BUSCAR</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step" style="border:2px solid #1E40AF; color:#1E40AF; font-weight:700; background: rgba(30, 64, 175, 0.05);">2. 📂 CARTERA</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">3. 🔬 ESTUDIO</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">4. 📝 OFERTAR</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">5. 📤 SUBIR A MP</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Filtros rápidos
    col_f1, col_f2, col_f3 = st.columns([2, 2, 2])
    with col_f1:
        filtro_estado = st.selectbox(
            "Mostrar",
            ["Todas las activas", "Solo Cartera (sin decidir)", "En Estudio", "En Oferta", "Listo para subir", "Cerradas (Adj/Perd)"],
            key="cart_filtro_estado"
        )
    with col_f2:
        filtro_orden = st.selectbox(
            "Ordenar por",
            ["Más urgente primero (por cierre)", "Mejor match primero", "Mayor monto primero", "Más reciente primero"],
            key="cart_filtro_orden"
        )
    with col_f3:
        filtro_solo_urgente = st.checkbox("⏰ Solo urgentes (cierran ≤7d)", key="cart_solo_urgente")
    
    # Construir query
    estado_map = {
        "Todas las activas": ["EN_CARTERA", "EN_ESTUDIO", "EN_OFERTA", "LISTO_SUBIR"],
        "Solo Cartera (sin decidir)": ["EN_CARTERA"],
        "En Estudio": ["EN_ESTUDIO"],
        "En Oferta": ["EN_OFERTA"],
        "Listo para subir": ["LISTO_SUBIR"],
        "Cerradas (Adj/Perd)": ["ADJUDICADO", "PERDIDO"],
    }
    estados_filt = estado_map.get(filtro_estado, ["EN_CARTERA", "EN_ESTUDIO", "EN_OFERTA", "LISTO_SUBIR"])
    placeholders = ",".join(["?"] * len(estados_filt))
    
    orden_map = {
        "Más urgente primero (por cierre)": "fecha_cierre ASC NULLS LAST",
        "Mejor match primero": "monto_referencial DESC",
        "Mayor monto primero": "monto_referencial DESC",
        "Más reciente primero": "id DESC",
    }
    orden_sql = orden_map.get(filtro_orden, "fecha_cierre ASC NULLS LAST")
    
    conn = get_connection()
    proyectos = conn.execute(
        f"SELECT * FROM aidu_proyectos WHERE estado IN ({placeholders}) ORDER BY {orden_sql}",
        estados_filt
    ).fetchall()
    conn.close()
    
    proyectos = [dict(p) for p in proyectos]
    
    # Filtrar urgentes
    if filtro_solo_urgente:
        from datetime import date as _date, timedelta as _td
        limite = (_date.today() + _td(days=7)).isoformat()
        proyectos = [p for p in proyectos if p.get("fecha_cierre") and p["fecha_cierre"] <= limite]
    
    # Conteos por estado para el header
    from collections import Counter
    counts = Counter(p["estado"] for p in proyectos)
    
    # Métricas resumen
    n_cartera = counts.get("EN_CARTERA", 0)
    n_estudio = counts.get("EN_ESTUDIO", 0)
    n_oferta = counts.get("EN_OFERTA", 0)
    n_subir = counts.get("LISTO_SUBIR", 0)
    n_adj = counts.get("ADJUDICADO", 0)
    n_perd = counts.get("PERDIDO", 0)
    
    st.markdown("##### 📊 Resumen del embudo activo")
    cm1, cm2, cm3, cm4, cm5, cm6 = st.columns(6)
    cm1.metric("📂 Cartera", n_cartera, help="Sin decidir si avanzar")
    cm2.metric("🔬 Estudio", n_estudio, help="En análisis profundo")
    cm3.metric("📝 Ofertar", n_oferta, help="Confeccionando propuesta")
    cm4.metric("📤 Subir", n_subir, help="Listo para cargar en MP")
    cm5.metric("🏆 Adjudicadas", n_adj, help="Ganadas")
    cm6.metric("❌ Perdidas", n_perd, help="No ganadas")
    
    st.divider()
    
    if not proyectos:
        st.info(f"📭 Sin proyectos en estado: **{filtro_estado}**. Ve a **🔍 Buscar** para agregar oportunidades.")
    else:
        st.markdown(f"##### 🎴 {len(proyectos)} licitación{'es' if len(proyectos) != 1 else ''} para revisar")
        
        # Mapa de próxima acción según estado
        proxima_accion = {
            "EN_CARTERA":  ("🔬 Pasar a Estudio",   "EN_ESTUDIO"),
            "EN_ESTUDIO":  ("📝 Pasar a Ofertar",   "EN_OFERTA"),
            "EN_OFERTA":   ("📤 Pasar a Subir MP",  "LISTO_SUBIR"),
            "LISTO_SUBIR": ("🏆 Marcar Adjudicada", "ADJUDICADO"),
        }
        
        # Mapa de colores por estado
        estado_colors = {
            "EN_CARTERA":  ("#1E40AF", "#DBEAFE", "📂", "Cartera"),
            "EN_ESTUDIO":  ("#0E7490", "#CFFAFE", "🔬", "Estudio"),
            "EN_OFERTA":   ("#9A3412", "#FED7AA", "📝", "Ofertar"),
            "LISTO_SUBIR": ("#6B21A8", "#E9D5FF", "📤", "Subir MP"),
            "ADJUDICADO":  ("#15803D", "#DCFCE7", "🏆", "Adjudicada"),
            "PERDIDO":     ("#DC2626", "#FEE2E2", "❌", "Perdida"),
        }
        
        try:
            from app.core.match_score import calcular_match_score
        except Exception:
            calcular_match_score = None
        
        for p in proyectos:
            color_e, bg_e, ico_e, label_e = estado_colors.get(p["estado"], ("#64748B", "#F1F5F9", "•", p["estado"]))
            
            # Calcular match score on-the-fly
            score = None
            if calcular_match_score:
                try:
                    lic_dict = {
                        "cod_servicio_aidu": p["cod_servicio_aidu"],
                        "confianza": 1.0,
                        "region": p["region"],
                        "monto_referencial": p["monto_referencial"],
                        "organismo": p["organismo"],
                        "fecha_publicacion": p.get("fecha_publicacion"),
                    }
                    match = calcular_match_score(lic_dict)
                    score = match["score"]
                except Exception:
                    pass
            
            # Días al cierre
            dias = calcular_dias_cierre(p.get("fecha_cierre")) if p.get("fecha_cierre") else None
            
            # Scoring "vamos/no vamos"
            decision_score = 0
            decision_factores = []
            
            # Match score (40%)
            if score is not None:
                if score >= 80:
                    decision_score += 40
                    decision_factores.append("✅ Match alto")
                elif score >= 60:
                    decision_score += 25
                    decision_factores.append("🟡 Match medio")
                else:
                    decision_score += 10
                    decision_factores.append("🔴 Match bajo")
            
            # Sweet spot del monto (30%)
            monto = p.get("monto_referencial") or 0
            if 3_000_000 <= monto <= 15_000_000:
                decision_score += 30
                decision_factores.append("✅ Sweet spot")
            elif 1_500_000 <= monto <= 30_000_000:
                decision_score += 18
                decision_factores.append("🟡 Rango aceptable")
            else:
                decision_score += 5
                decision_factores.append("🔴 Fuera de rango")
            
            # Plazo suficiente (30%)
            if dias is not None:
                if dias >= 7:
                    decision_score += 30
                    decision_factores.append(f"✅ {dias}d para preparar")
                elif dias >= 3:
                    decision_score += 18
                    decision_factores.append(f"🟡 Solo {dias}d")
                else:
                    decision_score += 5
                    decision_factores.append(f"🔴 Cierra en {dias}d")
            
            # Recomendación basada en scoring
            if decision_score >= 75:
                rec_color, rec_bg, rec_label, rec_icon = "#15803D", "#DCFCE7", "VAMOS", "🟢"
            elif decision_score >= 50:
                rec_color, rec_bg, rec_label, rec_icon = "#D97706", "#FEF3C7", "EVALUAR", "🟡"
            else:
                rec_color, rec_bg, rec_label, rec_icon = "#DC2626", "#FEE2E2", "DESCARTAR", "🔴"
            
            # Pills técnicas
            tech_pills = []
            if p.get("metros_cuadrados"):
                tech_pills.append(f"<span class='aidu-pill aidu-pill-cyan'>📐 {p['metros_cuadrados']} m²</span>")
            if p.get("plazo_dias"):
                tech_pills.append(f"<span class='aidu-pill aidu-pill-blue'>⏱️ {p['plazo_dias']}d</span>")
            if p.get("complejidad"):
                c_pill = {"BAJA": "aidu-pill-green", "MEDIA": "aidu-pill-amber", "ALTA": "aidu-pill-red"}.get(p["complejidad"], "aidu-pill-gray")
                tech_pills.append(f"<span class='aidu-pill {c_pill}'>🎯 {p['complejidad']}</span>")
            pills_html = " ".join(tech_pills) if tech_pills else ""
            
            url_mp = url_licitacion_mp(p["codigo_externo"])
            
            # Card kanban-style
            with st.container(border=True):
                # Header de la card: estado + recomendación + score
                col_head1, col_head2 = st.columns([3, 2])
                
                with col_head1:
                    badge_match = f"<span class='aidu-pill aidu-pill-blue' title='Match Score AIDU: cuán bien matchea tu perfil con esta licitación. Pesos: categoría 35% + región 20% + monto 20% + mandante 10% + recencia 15%'>Match {score}/100</span>" if score is not None else ""
                    st.markdown(
                        f"<div style='display:flex; gap:8px; flex-wrap:wrap; margin-bottom:8px;'>"
                        f"<span style='background:{bg_e}; color:{color_e}; padding:4px 12px; border-radius:8px; font-size:11px; font-weight:700; letter-spacing:0.4px;'>{ico_e} {label_e}</span>"
                        f"{badge_match}"
                        f"<span style='font-family:JetBrains Mono,monospace; font-size:11px; color:#94A3B8; padding:4px 0;'>{p['codigo_externo']}</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                
                with col_head2:
                    # Bloque de DECISIÓN visible (foco visual de la card)
                    st.markdown(
                        f"<div style='text-align:right;'>"
                        f"<span style='background:{rec_bg}; color:{rec_color}; padding:6px 14px; border-radius:10px; font-size:13px; font-weight:800; letter-spacing:0.5px; border:1px solid {rec_color}40;'>"
                        f"{rec_icon} {rec_label} · {decision_score}/100"
                        f"</span>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                
                # Cuerpo
                col_body1, col_body2 = st.columns([3, 1])
                
                with col_body1:
                    st.markdown(
                        f"<div style='font-size:16px; font-weight:600; color:#0F172A; line-height:1.4; margin-bottom:6px;'>{p['nombre']}</div>"
                        f"<div style='font-size:12px; color:#64748B; margin-bottom:8px;'>"
                        f"🏛️ {p.get('organismo') or '—'} · 📍 {p.get('region') or '—'} · 🎯 {p.get('cod_servicio_aidu') or '—'}"
                        f"</div>"
                        f"<div style='margin-bottom:8px;'>{pills_html}</div>",
                        unsafe_allow_html=True
                    )
                    
                    # Factores de decisión
                    factores_html = " · ".join(decision_factores)
                    st.markdown(
                        f"<div style='font-size:11px; color:#64748B; padding:8px 12px; background:#F8FAFC; border-radius:6px; border-left:2px solid #CBD5E1;'>"
                        f"<strong style='color:#475569;'>¿Por qué {rec_label.lower()}?</strong> {factores_html}"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                
                with col_body2:
                    color_dias = "#DC2626" if dias is not None and dias <= 3 else "#D97706" if dias is not None and dias <= 7 else "#15803D" if dias is not None else "#94A3B8"
                    dias_txt = f"{dias}d" if dias is not None else "—"
                    st.markdown(
                        f"<div style='text-align:right;'>"
                        f"<div style='font-size:10px; color:#64748B; text-transform:uppercase; letter-spacing:0.5px;'>Monto referencial</div>"
                        f"<div style='font-size:22px; font-weight:800; color:#1E40AF; line-height:1.1; margin:4px 0;'>{formato_clp(p.get('monto_referencial', 0) or 0)}</div>"
                        f"<div style='font-size:11px; color:{color_dias}; font-weight:600;'>⏰ Cierra en {dias_txt}</div>"
                        f"</div>",
                        unsafe_allow_html=True
                    )
                
                # Botones de acción
                st.write("")
                col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 2])
                
                # Botón principal: avanzar etapa
                accion = proxima_accion.get(p["estado"])
                if accion:
                    label, nuevo_estado = accion
                    if col_a.button(label, key=f"adv_{p['id']}", use_container_width=True, type="primary"):
                        _cambiar_estado(p["id"], nuevo_estado, paquete=(nuevo_estado == "EN_OFERTA"))
                        st.success(f"✅ Movida a {nuevo_estado}")
                        st.rerun()
                elif p["estado"] == "ADJUDICADO":
                    col_a.success("🏆 Adjudicada")
                elif p["estado"] == "PERDIDO":
                    col_a.error("❌ Perdida")
                
                # Botón ver detalle
                if col_b.button("👁️ Ver ficha", key=f"det_{p['id']}", use_container_width=True):
                    st.session_state["view_proyecto_id"] = p["id"]
                    st.rerun()
                
                # Botón descartar (solo si no está ya cerrada)
                if p["estado"] not in ("ADJUDICADO", "PERDIDO"):
                    if col_c.button("🗑️ Descartar", key=f"desc_{p['id']}", use_container_width=True, help="Mover a 'Perdida' (no ofertaremos)"):
                        _cambiar_estado(p["id"], "PERDIDO", paquete=False)
                        st.warning("Proyecto descartado")
                        st.rerun()
                
                # Botón ver en MP
                col_d.markdown(
                    f"<a href='{url_mp}' target='_blank' style='display:block; text-align:center; padding:8px 12px; background:#1E40AF; color:white; border-radius:8px; text-decoration:none; font-size:13px; font-weight:600;'>🔗 Ver en MP</a>",
                    unsafe_allow_html=True
                )



# ====================
# TAB 1 EMBUDO: 🔍 BUSCAR
# ====================
if tab_buscar:
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:32px;">🔍 Buscar oportunidades</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">
            Match Score con perfil AIDU · Histórico Mercado Público + licitaciones vigentes · Análisis IA Masivo
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="macro-flow">
        <div class="macro-step" style="border:2px solid #1E40AF; color:#1E40AF; font-weight:700; background: rgba(30, 64, 175, 0.05);">1. 🔍 BUSCAR</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">2. 📂 CARTERA</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">3. 🔬 ESTUDIO</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">4. 📝 OFERTAR</div>
        <span class="macro-arrow">→</span>
        <div class="macro-step">5. 📤 SUBIR A MP</div>
    </div>
    """, unsafe_allow_html=True)
    
    st.info("💡 **Cómo usar este paso:** Filtra y revisa las oportunidades con mejor Match Score. Las que te interesen, click '+ Cartera' para que pasen al paso 2 (decisión).")

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
        if col_p1.button("📍 Mi región", key="preset_region", use_container_width=True, help="Filtra por O'Higgins"):
            st.session_state["op_regs_multi"] = ["VI"]
            st.rerun()
        if col_p2.button("🏗️ Estructural", key="preset_estr", use_container_width=True, help="Solo CE-XX (cálculo, peritaje, ITO)"):
            from app.core.catalogo_aidu import codigos_por_linea
            st.session_state["op_cats_multi"] = codigos_por_linea("Estructural")
            st.rerun()
        
        col_p3, col_p4 = st.columns(2)
        if col_p3.button("📊 Gestión", key="preset_gest", use_container_width=True, help="Solo GP-XX (PMO, BPM, optimización)"):
            from app.core.catalogo_aidu import codigos_por_linea
            st.session_state["op_cats_multi"] = codigos_por_linea("Gestión")
            st.rerun()
        if col_p4.button("🌎 Zonas AIDU", key="preset_zonas", use_container_width=True, help="V + RM + O'Higgins + Los Lagos"):
            st.session_state["op_regs_multi"] = ["V", "RM", "VI", "X"]
            st.rerun()
        
        col_p5, col_p6 = st.columns(2)
        if col_p5.button("💎 Sweet spot", key="preset_sweet", use_container_width=True, help="Monto $3M - $15M"):
            st.session_state["op_min"] = 3
            st.session_state["op_max"] = 15
            st.rerun()
        if col_p6.button("🔄 Limpiar todo", key="preset_clear", use_container_width=True):
            for k in ["op_busqueda", "op_min", "op_max", "op_cats_multi", "op_regs_multi", "op_org"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
        
        st.divider()

        # Búsqueda libre por palabra clave
        busqueda = st.text_input(
            "🔍 Buscar palabra clave",
            placeholder="ej: estructural, escuela, Machalí...",
            key="op_busqueda",
            help="Busca en nombre, descripción y organismo"
        )

        # ============ Categoría AIDU MULTI con descripciones ============
        from app.core.catalogo_aidu import CATALOGO_AIDU, label_servicio
        
        cats_disponibles = list(CATALOGO_AIDU.keys())
        cat_format = lambda cod: label_servicio(cod, "completo")
        
        cats_seleccionadas = st.multiselect(
            "🎯 Categorías AIDU",
            options=cats_disponibles,
            format_func=cat_format,
            key="op_cats_multi",
            help="Selecciona uno o más servicios. Vacío = todas las categorías."
        )

        # ============ Regiones MULTI ============
        from app.core.catalogo_aidu import REGIONES_INTERES_AIDU, MP_REGION_TO_CODE
        
        regs_disponibles = list(REGIONES_INTERES_AIDU.keys())
        reg_format = lambda code: f"{code} — {REGIONES_INTERES_AIDU[code]}"
        
        regs_seleccionadas = st.multiselect(
            "📍 Regiones de operación",
            options=regs_disponibles,
            format_func=reg_format,
            key="op_regs_multi",
            help="Zonas con facilidades logísticas AIDU. Vacío = todas las regiones."
        )

        # ============ Organismo (filtro nuevo) ============
        # Cargar organismos disponibles desde BD
        @st.cache_data(ttl=120)
        def _cached_organismos():
            try:
                conn_org = get_connection()
                rows = conn_org.execute(
                    "SELECT DISTINCT organismo FROM mp_licitaciones_vigentes "
                    "WHERE organismo IS NOT NULL AND organismo != '' "
                    "ORDER BY organismo"
                ).fetchall()
                conn_org.close()
                return [r[0] for r in rows]
            except Exception:
                return []
        
        organismos_lista = _cached_organismos()
        org_seleccionados = st.multiselect(
            "🏛️ Organismos (mandantes)",
            options=organismos_lista,
            key="op_org",
            help=f"Filtrar por uno o más mandantes. {len(organismos_lista)} organismos disponibles. Vacío = todos."
        )

        # Monto - SIN restricción por defecto
        st.caption("💰 Monto referencial (M CLP) · 0 = sin filtro")
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
        score_min = st.slider("⭐ Match Score mín.", 0, 100, 50, 5, key="op_score")

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
        # Para compatibilidad con la firma actual de listar_oportunidades,
        # tomamos la PRIMERA categoría/región seleccionada como filtro principal
        # y aplicamos el resto (multi) en post-filtrado en Python.
        cat_sel_legacy = cats_seleccionadas[0] if cats_seleccionadas and len(cats_seleccionadas) == 1 else "Todas"
        
        # Para región, mapear código corto a nombre completo de MP
        reg_sel_legacy = "Todas"
        if regs_seleccionadas and len(regs_seleccionadas) == 1:
            code = regs_seleccionadas[0]
            # Buscar el nombre canónico en MP
            inv_map = {v: k for k, v in MP_REGION_TO_CODE.items() if v not in MP_REGION_TO_CODE.values() or k == REGIONES_INTERES_AIDU.get(v, v)}
            reg_sel_legacy = REGIONES_INTERES_AIDU.get(code, "Todas")
        
        kwargs_op = dict(
            filtro_categoria=cat_sel_legacy,
            filtro_region=reg_sel_legacy,
            monto_min=monto_min_m * 1_000_000 if monto_min_m > 0 else None,
            monto_max=monto_max_m * 1_000_000 if monto_max_m > 0 else None,
            score_min=score_min,
            solo_no_en_cartera=solo_nuevas,
            orden=orden_map[orden_label],
            limit=200,  # más amplio porque filtraremos en Python
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
        
        # ============ Post-filtrado MULTI ============
        # Multi-categoría AIDU
        if cats_seleccionadas and len(cats_seleccionadas) >= 1:
            cats_set = set(cats_seleccionadas)
            oportunidades = [
                op for op in oportunidades
                if (op.get("cod_servicio_aidu") or "") in cats_set
            ]
        
        # Multi-región
        if regs_seleccionadas:
            regs_set = set(regs_seleccionadas)
            oportunidades = [
                op for op in oportunidades
                if MP_REGION_TO_CODE.get((op.get("region") or "").strip(), "") in regs_set
            ]
        
        # Filtro por organismo (multi)
        if org_seleccionados:
            orgs_set = set(org_seleccionados)
            oportunidades = [
                op for op in oportunidades
                if (op.get("organismo") or "") in orgs_set
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
                    
                    # Construir tooltip rico para Match Score
                    match_tooltip = (
                        f"Match Score: {score}/100&#10;&#10;"
                        f"Cómo se calcula:&#10;"
                        f"• Categoría AIDU: {desg['categoria'][1]} (peso 35%)&#10;"
                        f"• Región: {desg['region'][1]} (peso 20%)&#10;"
                        f"• Monto vs sweet spot: {desg['monto'][1]} (peso 20%)&#10;"
                        f"• Mandante: {desg['mandante'][1]} (peso 10%)&#10;"
                        f"• Recencia: {desg.get('recencia', ('', '?'))[1]} (peso 15%)"
                    )
                    
                    # Tooltip para categoría AIDU
                    cat_aidu = op.get('cod_servicio_aidu') or 'Sin cat.'
                    cat_descripciones = {
                        "CE-01": "Peritaje y diagnóstico estructural · evaluación de daños",
                        "CE-02": "Cálculo y diseño estructural · planos y memoria",
                        "CE-03": "Revisión de proyectos estructurales",
                        "CE-04": "Asesoría en obras estructurales",
                        "CE-05": "Inspección técnica de obras estructurales",
                        "CE-06": "Apoyo SECPLAN · revisión bases técnicas",
                        "GP-01": "Gestión de proyectos · PMO",
                        "GP-02": "Optimización de procesos operacionales",
                        "GP-03": "Diagnóstico organizacional",
                        "GP-04": "Levantamiento y rediseño de procesos · BPM",
                    }
                    cat_tooltip = cat_descripciones.get(cat_aidu, "Categoría AIDU del catálogo de servicios")

                    # Bloque principal
                    with col_main:
                        st.markdown(f"""
                        <div style='display:flex; gap:6px; align-items:center; margin-bottom:4px;'>
                            <span title="{match_tooltip}" style='background:{score_bg}; color:{score_color}; font-size:11px; padding:2px 10px; border-radius:12px; font-weight:600; cursor:help;'>Match {score}</span>
                            <span title="{cat_aidu}: {cat_tooltip}" style='background:#E0F2FE; color:#0C4A6E; font-size:11px; padding:2px 8px; border-radius:12px; cursor:help;'>{cat_aidu}</span>
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
                            type="primary",
                            help="Convierte esta oportunidad en proyecto AIDU (estado EN_CARTERA)"
                        ):
                            try:
                                pid = convertir_a_proyecto(op["codigo_externo"])
                                st.session_state["view_proyecto_id"] = pid
                                st.success(f"✅ Agregado a cartera")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                        
                        # Botón Ver detalle/ficha
                        if st.button(
                            "👁️ Ver ficha",
                            key=f"ver_ficha_{idx}_{op['codigo_externo']}",
                            use_container_width=True,
                            help="Abre la ficha de detalle (sin agregar a cartera)"
                        ):
                            # Buscar si ya existe como proyecto, si no crearlo temporalmente
                            try:
                                conn = get_connection()
                                existe = conn.execute(
                                    "SELECT id FROM aidu_proyectos WHERE codigo_externo = ?",
                                    (op["codigo_externo"],)
                                ).fetchone()
                                conn.close()
                                
                                if existe:
                                    st.session_state["view_proyecto_id"] = existe["id"]
                                else:
                                    # Crear como prospecto temporal
                                    pid = convertir_a_proyecto(op["codigo_externo"])
                                    st.session_state["view_proyecto_id"] = pid
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error: {e}")
                        
                        # Link directo a Mercado Público
                        mp_url = url_licitacion_mp(op['codigo_externo'])
                        st.markdown(
                            f"<a href='{mp_url}' target='_blank' style='display:block; text-align:center; font-size:11px; color:#1E40AF; text-decoration:none; padding:5px 0; margin-top:6px; border:1px solid #CBD5E1; border-radius:6px;'>🔗 Ver en MP</a>",
                            unsafe_allow_html=True
                        )


# ====================
# TAB 3: INTELIGENCIA
# ====================
# ============================================================
# 🔬 ESTUDIO — Análisis profundo + descarga de bases automática
# ============================================================
if tab_estudio:
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:32px;">🔬 Estudio</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">
            Análisis profundo de bases técnicas · Decisión final de cotizar antes de pasar a Ofertar
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    conn = get_connection()
    proyectos_estudio = conn.execute("""
        SELECT * FROM aidu_proyectos
        WHERE estado = 'EN_ESTUDIO'
        ORDER BY fecha_cierre ASC
    """).fetchall()
    proyectos_estudio = [dict(p) for p in proyectos_estudio]
    conn.close()
    
    col_s1, col_s2, col_s3 = st.columns(3)
    monto_total = sum(p.get("monto_referencial") or 0 for p in proyectos_estudio)
    cierran_pronto = sum(1 for p in proyectos_estudio if p.get("fecha_cierre") and (calcular_dias_cierre(p["fecha_cierre"]) or 99) <= 7)
    
    col_s1.metric("🔬 Proyectos en estudio", len(proyectos_estudio))
    col_s2.metric("💰 Monto total", formato_clp(monto_total))
    col_s3.metric("⏰ Cierran ≤7d", cierran_pronto)
    
    if not proyectos_estudio:
        st.info("📭 Sin proyectos en estudio. Mueve proyectos desde Cartera para empezar el análisis profundo.")
        if st.button("📂 Ir a Cartera", type="primary"):
            st.query_params["nav"] = "cartera"
            st.rerun()
    else:
        st.caption("💡 Cada proyecto en estudio debe tener sus bases técnicas analizadas (en la ficha → tab IA) antes de avanzar a Ofertar.")
        
        for p in proyectos_estudio:
            dias = calcular_dias_cierre(p.get("fecha_cierre")) if p.get("fecha_cierre") else None
            border = "#DC2626" if dias is not None and dias <= 3 else "#D97706" if dias is not None and dias <= 7 else "#0E7490"
            url_mp = p.get("url_mp") or url_licitacion_mp(p['codigo_externo'])
            
            st.markdown(f"""
            <div class='aidu-card' style='border-left:4px solid {border};'>
                <div style='display:flex; justify-content:space-between; align-items:start;'>
                    <div style='flex:1;'>
                        <div class='aidu-card-title'>{p['nombre']}</div>
                        <div class='aidu-card-meta'>
                            <span class='aidu-card-code'>{p['codigo_externo']}</span> · 
                            🏛️ {p.get('organismo') or '—'} · 
                            📍 {p.get('region') or '—'} · 
                            🎯 {p.get('cod_servicio_aidu') or '—'}
                        </div>
                    </div>
                    <div style='text-align:right; min-width:160px;'>
                        <div style='font-weight:700; color:#1E40AF; font-size:18px;'>{formato_clp(p.get('monto_referencial', 0))}</div>
                        <div style='font-size:11px; font-weight:600; color:{border};'>
                            {f"⏰ {dias}d para cerrar" if dias is not None else "—"}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            col_a, col_b, col_c, col_d = st.columns([2, 2, 2, 1])
            
            with col_a:
                if st.button("📋 Abrir ficha completa", key=f"ver_est_{p['id']}", use_container_width=True, type="primary"):
                    st.session_state["view_proyecto_id"] = p["id"]
                    st.rerun()
            
            with col_b:
                st.markdown(f"""
                <a href='{url_mp}' target='_blank' style='display:block; padding:9px 14px; background:white; color:#1E40AF; text-align:center; border-radius:8px; text-decoration:none; font-weight:600; font-size:13px; border:1px solid #1E40AF;'>
                    🌐 Ver en MP
                </a>
                """, unsafe_allow_html=True)
            
            with col_c:
                if st.button("➡️ Pasar a Ofertar", key=f"of_{p['id']}", use_container_width=True):
                    conn = get_connection()
                    conn.execute("UPDATE aidu_proyectos SET estado='EN_OFERTA' WHERE id=?", (p["id"],))
                    conn.commit()
                    conn.close()
                    st.rerun()
            
            with col_d:
                if st.button("❌", key=f"desc_est_{p['id']}", use_container_width=True, help="Descartar"):
                    conn = get_connection()
                    conn.execute("UPDATE aidu_proyectos SET estado='DESCARTADO' WHERE id=?", (p["id"],))
                    conn.commit()
                    conn.close()
                    st.rerun()


# ============================================================
# 📝 OFERTAR — Confección de oferta asistida por IA
# ============================================================
if tab_ofertar:
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:32px;">📝 Ofertar</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">
            Confección de oferta técnica y económica asistida por IA · Predicción de descuento óptimo · Generación de paquetes Word/Excel
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    conn = get_connection()
    proyectos_ofertar = conn.execute("""
        SELECT * FROM aidu_proyectos
        WHERE estado = 'EN_OFERTA'
        ORDER BY fecha_cierre ASC
    """).fetchall()
    proyectos_ofertar = [dict(p) for p in proyectos_ofertar]
    conn.close()
    
    col_o1, col_o2, col_o3 = st.columns(3)
    col_o1.metric("📝 Listos para ofertar", len(proyectos_ofertar))
    col_o2.metric("Monto total", formato_clp(sum(p.get("monto_referencial") or 0 for p in proyectos_ofertar)))
    
    cierran_pronto = sum(1 for p in proyectos_ofertar if p.get("fecha_cierre") and (calcular_dias_cierre(p["fecha_cierre"]) or 99) <= 3)
    col_o3.metric("🔴 Cierran ≤3d", cierran_pronto)
    
    if not proyectos_ofertar:
        st.info("📭 Sin proyectos listos para ofertar. Avanza desde Estudio cuando hayas tomado la decisión de cotizar.")
        if st.button("🔬 Ir a Estudio", type="primary"):
            st.query_params["nav"] = "estudio"
            st.rerun()
    else:
        st.markdown("##### 🎯 Confecciona la oferta")
        
        for p in proyectos_ofertar:
            dias = calcular_dias_cierre(p.get("fecha_cierre")) if p.get("fecha_cierre") else None
            border = "#DC2626" if dias is not None and dias <= 3 else "#D97706" if dias is not None and dias <= 7 else "#1E40AF"
            
            st.markdown(f"""
            <div class='aidu-card' style='border-left:4px solid {border};'>
                <div style='display:flex; justify-content:space-between; align-items:start;'>
                    <div style='flex:1;'>
                        <div class='aidu-card-title'>{p['nombre']}</div>
                        <div class='aidu-card-meta'>
                            🏛️ {p.get('organismo') or '—'} · 🎯 {p.get('cod_servicio_aidu') or '—'} · 
                            <span style='color:{border}; font-weight:600;'>⏰ {f"{dias}d para cerrar" if dias is not None else "Sin fecha"}</span>
                        </div>
                    </div>
                    <div style='text-align:right;'>
                        <div style='font-weight:700; color:#1E40AF; font-size:18px;'>{formato_clp(p.get('monto_referencial', 0))}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                if st.button("👁️ Detalle + IA precios", key=f"ver_of_{p['id']}", use_container_width=True, type="primary"):
                    st.session_state["view_proyecto_id"] = p["id"]
                    st.rerun()
            
            with col2:
                if st.button("📊 Predecir descuento", key=f"pred_{p['id']}", use_container_width=True):
                    try:
                        from app.core.inteligencia_avanzada import predecir_descuento_optimo
                        pred = predecir_descuento_optimo(
                            p.get("cod_servicio_aidu") or "",
                            p.get("organismo"),
                            p.get("monto_referencial")
                        )
                        st.info(f"💡 **Recomendado: {pred['descuento_recomendado_pct']}% descuento** · Confianza: {pred['confianza']*100:.0f}%")
                        st.caption(pred["razon"])
                        st.caption(f"Banda segura: {pred['descuento_minimo_pct']}% — {pred['descuento_maximo_pct']}%")
                    except Exception as e:
                        st.error(f"Error: {e}")
            
            with col3:
                if st.button("📦 Generar paquete", key=f"pkg_{p['id']}", use_container_width=True):
                    st.session_state["view_proyecto_id"] = p["id"]
                    st.rerun()
            
            with col4:
                if st.button("✅ Marcar Ofertado", key=f"of_done_{p['id']}", use_container_width=True):
                    conn = get_connection()
                    conn.execute("UPDATE aidu_proyectos SET estado='LISTO_SUBIR' WHERE id=?", (p["id"],))
                    conn.commit()
                    conn.close()
                    st.success("Marcada como ofertada → ahora en 'Subir a MP'")
                    st.rerun()


# ============================================================
# 📤 SUBIR A MP — Lista para carga manual en Mercado Público
# ============================================================
if tab_subir:
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:32px;">📤 Subir a Mercado Público</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">
            Ofertas listas con paquete generado · Cierra el ciclo subiéndolas manualmente al portal de MP
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    st.warning("⚠️ Por seguridad legal, AIDU Op NO sube ofertas automáticamente al portal de Mercado Público. La carga es manual y la haces tú directamente en mercadopublico.cl")
    
    conn = get_connection()
    proyectos_subir = conn.execute("""
        SELECT * FROM aidu_proyectos
        WHERE estado = 'LISTO_SUBIR'
        ORDER BY fecha_cierre ASC
    """).fetchall()
    proyectos_subir = [dict(p) for p in proyectos_subir]
    conn.close()
    
    col_sb1, col_sb2 = st.columns(2)
    col_sb1.metric("📤 Por subir a MP", len(proyectos_subir))
    col_sb2.metric("Monto comprometido", formato_clp(sum(p.get("monto_referencial") or 0 for p in proyectos_subir)))
    
    if not proyectos_subir:
        st.info("📭 Sin ofertas listas para subir. Avanza ofertas desde 'Ofertar' cuando estén completas.")
        if st.button("📝 Ir a Ofertar", type="primary"):
            st.query_params["nav"] = "ofertar"
            st.rerun()
    else:
        st.markdown("##### 📋 Checklist de subida a MP")
        
        for p in proyectos_subir:
            dias = calcular_dias_cierre(p.get("fecha_cierre")) if p.get("fecha_cierre") else None
            border = "#DC2626" if dias is not None and dias <= 1 else "#D97706" if dias is not None and dias <= 3 else "#15803D"
            
            url_mp = url_licitacion_mp(p['codigo_externo'])
            
            st.markdown(f"""
            <div class='aidu-card' style='border-left:4px solid {border};'>
                <div style='display:flex; justify-content:space-between; align-items:start;'>
                    <div style='flex:1;'>
                        <div class='aidu-card-title'>{p['nombre']}</div>
                        <div class='aidu-card-meta'>
                            <span class='aidu-card-code'>{p['codigo_externo']}</span> · 
                            🏛️ {p.get('organismo') or '—'} · 
                            <span style='color:{border}; font-weight:600;'>⏰ {f"{dias}d para cerrar" if dias is not None else "Sin fecha"}</span>
                        </div>
                    </div>
                    <div style='text-align:right;'>
                        <div style='font-weight:700; color:#1E40AF; font-size:18px;'>{formato_clp(p.get('monto_referencial', 0))}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f"""
                <a href='{url_mp}' target='_blank' style='display:inline-block; width:100%; padding:9px 14px; background:#1E40AF; color:white; text-align:center; border-radius:8px; text-decoration:none; font-weight:600; font-size:13px;'>
                    🌐 Abrir en MP →
                </a>
                """, unsafe_allow_html=True)
            
            with col2:
                if st.button("📦 Ver paquete", key=f"pkg_sub_{p['id']}", use_container_width=True):
                    st.session_state["view_proyecto_id"] = p["id"]
                    st.rerun()
            
            with col3:
                if st.button("✅ Confirmar subida", key=f"sub_done_{p['id']}", use_container_width=True, type="primary"):
                    conn = get_connection()
                    conn.execute("UPDATE aidu_proyectos SET estado='LISTO_SUBIR', notas = COALESCE(notas, '') || char(10) || 'Subida a MP confirmada el ' || datetime('now', 'localtime') WHERE id=?", (p["id"],))
                    conn.commit()
                    conn.close()
                    st.success("✅ Subida confirmada. Esperando resultado de adjudicación.")
                    st.rerun()
            
            with col4:
                resultado = st.selectbox(
                    "Resultado",
                    ["Pendiente", "✅ Adjudicada", "❌ Perdida"],
                    key=f"res_{p['id']}",
                    label_visibility="collapsed"
                )
                if resultado != "Pendiente":
                    nuevo_estado = "ADJUDICADO" if "Adjudicada" in resultado else "PERDIDO"
                    if st.button("Guardar resultado", key=f"save_res_{p['id']}", use_container_width=True):
                        conn = get_connection()
                        conn.execute("UPDATE aidu_proyectos SET estado=? WHERE id=?", (nuevo_estado, p["id"]))
                        conn.commit()
                        conn.close()
                        st.success(f"Estado actualizado: {nuevo_estado}")
                        st.rerun()


if tab_intel:
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:28px;">📊 Inteligencia de Mercado</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">Dashboard ejecutivo · análisis por categoría · estudio de mandantes · competencia recurrente</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Sub-pestañas internas
    intel_t1, intel_t2, intel_t3, intel_t4 = st.tabs([
        "📈 Dashboard ejecutivo",
        "🎯 Por categoría",
        "🏛️ Análisis de mandante",
        "🥇 Competencia"
    ])
    
    # ============ SUB-TAB 1: DASHBOARD EJECUTIVO ============
    with intel_t1:
        try:
            from app.core.inteligencia_avanzada import forecast_pipeline_90d, tasa_exito_por_dimension
            
            forecast = forecast_pipeline_90d()
            win_rate = tasa_exito_por_dimension()
            
            st.markdown("##### 💰 Pipeline 90 días")
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric(
                "Pipeline total",
                formato_clp(forecast["valor_pipeline_total_clp"]),
                help="Suma de montos de todos los proyectos activos"
            )
            col2.metric(
                "Valor esperado",
                formato_clp(forecast["valor_esperado_clp"]),
                help="Valor ponderado por probabilidad de adjudicación"
            )
            col3.metric(
                "Ingresos proyectados",
                formato_clp(forecast["ingresos_esperados_clp"]),
                help=f"Aplicando margen objetivo {forecast['margen_aplicado_pct']:.0f}%"
            )
            col4.metric(
                "Proyectos activos",
                forecast["n_proyectos_activos"]
            )
            
            st.markdown("##### 📊 Pipeline por etapa")
            
            if forecast["por_etapa"]:
                for etapa in forecast["por_etapa"]:
                    barra_pct = etapa["probabilidad_pct"]
                    color = "#15803D" if barra_pct >= 50 else "#D97706" if barra_pct >= 25 else "#DC2626"
                    
                    st.markdown(f"""
                    <div style='padding:14px 18px; background:white; border:1px solid #E2E8F0; border-radius:10px; margin-bottom:8px; box-shadow:0 1px 2px rgba(0,0,0,0.04);'>
                        <div style='display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;'>
                            <div>
                                <span class='estado-{etapa["etapa"]}'>{etapa["etapa"]}</span>
                                <span style='margin-left:12px; color:#64748B; font-size:13px;'>{etapa["n_proyectos"]} proyectos · {formato_clp(etapa["valor_total_clp"])}</span>
                            </div>
                            <div style='font-weight:700; color:{color}; font-size:15px;'>
                                {formato_clp(etapa["valor_esperado_clp"])} esperado
                            </div>
                        </div>
                        <div style='height:6px; background:#F1F5F9; border-radius:3px; overflow:hidden;'>
                            <div style='height:100%; width:{barra_pct}%; background:{color}; border-radius:3px;'></div>
                        </div>
                        <div style='font-size:11px; color:#94A3B8; margin-top:4px;'>Probabilidad estimada de adjudicación: {barra_pct:.0f}%</div>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("##### 🏆 Win Rate")
            
            col_w1, col_w2, col_w3 = st.columns(3)
            col_w1.metric(
                "Win rate global",
                f"{win_rate['win_rate_global_pct']:.1f}%",
                f"{win_rate['total_adjudicadas']}/{win_rate['total_postuladas']} postulaciones"
            )
            col_w2.metric("Adjudicadas", win_rate["total_adjudicadas"])
            col_w3.metric("Total postuladas", win_rate["total_postuladas"])
            
            if win_rate["por_categoria"]:
                st.markdown("###### 📁 Por categoría AIDU")
                for cat in win_rate["por_categoria"][:5]:
                    color = "#15803D" if cat["win_rate_pct"] >= 30 else "#D97706" if cat["win_rate_pct"] >= 15 else "#DC2626"
                    st.markdown(f"""
                    <div style='display:flex; justify-content:space-between; padding:8px 14px; background:#F8FAFC; border-radius:6px; margin-bottom:4px;'>
                        <span><strong>{cat['categoria']}</strong> · {cat['ganadas']}/{cat['postuladas']}</span>
                        <strong style='color:{color};'>{cat['win_rate_pct']:.1f}%</strong>
                    </div>
                    """, unsafe_allow_html=True)
            
            if win_rate["por_mandante"]:
                st.markdown("###### 🏛️ Top 5 mandantes")
                for m in win_rate["por_mandante"][:5]:
                    color = "#15803D" if m["win_rate_pct"] >= 30 else "#D97706" if m["win_rate_pct"] >= 15 else "#DC2626"
                    st.markdown(f"""
                    <div style='display:flex; justify-content:space-between; padding:8px 14px; background:#F8FAFC; border-radius:6px; margin-bottom:4px;'>
                        <span><strong>{m['mandante']}</strong> · {m['ganadas']}/{m['postuladas']}</span>
                        <strong style='color:{color};'>{m['win_rate_pct']:.1f}%</strong>
                    </div>
                    """, unsafe_allow_html=True)
            
            st.markdown("---")
            st.markdown("##### 🌟 Top 5 oportunidades por valor esperado")
            
            for op in forecast["top_oportunidades"][:5]:
                st.markdown(f"""
                <div class='aidu-card'>
                    <div style='display:flex; justify-content:space-between; align-items:start;'>
                        <div style='flex:1;'>
                            <div class='aidu-card-title'>{op['nombre']}</div>
                            <div class='aidu-card-meta'>
                                🏛️ {op.get('organismo', '—')} · 
                                <span class='estado-{op['estado']}'>{op['estado']}</span>
                            </div>
                        </div>
                        <div style='text-align:right;'>
                            <div style='font-size:11px; color:#94A3B8;'>Valor esperado</div>
                            <div style='font-size:18px; font-weight:700; color:#1E40AF;'>{formato_clp(op['valor_esperado'])}</div>
                            <div style='font-size:11px; color:#64748B;'>Prob: {op['prob']*100:.0f}%</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
        except Exception as e:
            st.warning("⚠️ Dashboard requiere datos en cartera. Carga datos demo en Sistema o agrega proyectos.")
            with st.expander("Detalle"):
                st.code(str(e))
    
    # ============ SUB-TAB 2: POR CATEGORÍA ============
    with intel_t2:
        st.markdown("##### 🎯 Análisis estadístico por categoría AIDU")
        
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
                
                comparables = licitaciones_similares(cod_sel, limit=10)
                if comparables:
                    st.markdown("##### 📚 Top 10 licitaciones")
                    for r in comparables:
                        desc = r.get("descuento_pct")
                        desc_str = f" · Δ {desc:+.1f}%" if desc else ""
                        st.markdown(
                            f"<div class='aidu-card' style='padding:12px 16px; margin-bottom:6px; border-left:3px solid #1E40AF;'>"
                            f"<div class='aidu-card-title'>{r['nombre']}</div>"
                            f"<div class='aidu-card-meta'>🏛️ {r.get('organismo') or '—'} · {formato_clp(r['monto_adjudicado'])} adjudicado{desc_str} · Match: {r['similarity']:.0f}%</div>"
                            f"</div>",
                            unsafe_allow_html=True
                        )
            else:
                st.info(f"Sin datos para {cod_sel}.")
    
    # ============ SUB-TAB 3: ANÁLISIS DE MANDANTE ============
    with intel_t3:
        st.markdown("##### 🏛️ Análisis 360 de un mandante")
        st.caption("Conoce a fondo cómo licita un organismo específico antes de postular")
        
        try:
            from app.core.inteligencia_avanzada import analizar_mandante
            
            conn = get_connection()
            mandantes = conn.execute("""
                SELECT organismo, COUNT(*) as n
                FROM mp_licitaciones_adj
                WHERE organismo IS NOT NULL
                GROUP BY organismo
                ORDER BY n DESC LIMIT 100
            """).fetchall()
            conn.close()
            
            if mandantes:
                organismo_sel = st.selectbox(
                    "Mandante a analizar",
                    options=[m["organismo"] for m in mandantes],
                    format_func=lambda x: f"{x} ({next(m['n'] for m in mandantes if m['organismo']==x)} licit.)"
                )
                
                if organismo_sel:
                    analisis = analizar_mandante(organismo_sel)
                    
                    if analisis["encontrado"]:
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Total licitaciones", analisis["total_licitaciones"])
                        c2.metric("Monto promedio", formato_clp(analisis["monto_promedio_clp"]))
                        c3.metric("Monto máximo", formato_clp(analisis["monto_max_clp"]))
                        c4.metric("Descuento promedio", f"{analisis['descuento_promedio_pct']:.1f}%")
                        
                        col_a, col_b = st.columns(2)
                        
                        with col_a:
                            st.markdown("###### 📁 Categorías frecuentes")
                            for cat in analisis["categorias_frecuentes"]:
                                st.markdown(f"""
                                <div style='padding:8px 14px; background:#F8FAFC; border-radius:6px; margin-bottom:4px; display:flex; justify-content:space-between;'>
                                    <strong>{cat['categoria']}</strong>
                                    <span style='color:#64748B;'>{cat['n']} proyectos</span>
                                </div>
                                """, unsafe_allow_html=True)
                        
                        with col_b:
                            st.markdown("###### 🥇 Proveedores recurrentes")
                            for prov in analisis["proveedores_recurrentes"]:
                                st.markdown(f"""
                                <div style='padding:8px 14px; background:#F8FAFC; border-radius:6px; margin-bottom:4px;'>
                                    <div style='font-size:13px; font-weight:600;'>{prov['nombre']}</div>
                                    <div style='font-size:11px; color:#64748B;'>{prov['n']} adj. · {formato_clp(prov['total_clp'])} total</div>
                                </div>
                                """, unsafe_allow_html=True)
        except Exception as e:
            st.warning("⚠️ Análisis de mandante no disponible.")
            with st.expander("Detalle"):
                st.code(str(e))
    
    # ============ SUB-TAB 4: COMPETENCIA ============
    with intel_t4:
        st.markdown("##### 🥇 Detección de competencia recurrente")
        st.caption("Identifica quiénes ganan más en tu nicho competitivo")
        
        try:
            from app.core.inteligencia_avanzada import detectar_competencia_recurrente
            
            col_f1, col_f2 = st.columns(2)
            
            cat_filtro = col_f1.selectbox(
                "Filtrar por categoría",
                ["Todas"] + [s["cod_servicio"] for s in servicios],
                key="comp_cat"
            )
            
            region_filtro = col_f2.selectbox(
                "Filtrar por región",
                ["Todas", "O'Higgins", "Metropolitana", "Maule", "Valparaíso"],
                key="comp_reg"
            )
            
            comp = detectar_competencia_recurrente(
                cod_servicio_aidu=cat_filtro if cat_filtro != "Todas" else None,
                region=region_filtro if region_filtro != "Todas" else None,
                top_n=15
            )
            
            if comp["competidores"]:
                col_m1, col_m2, col_m3 = st.columns(3)
                col_m1.metric("Competidores únicos", len(comp["competidores"]))
                col_m2.metric(
                    "Concentración top 3",
                    f"{comp['concentracion_top3_pct']:.1f}%",
                    "Mercado fragmentado" if comp["competencia_fragmentada"] else "Mercado concentrado"
                )
                col_m3.metric("Total proyectos", comp["total_proyectos_analizados"])
                
                st.markdown("###### 📋 Top 15 competidores")
                
                for i, c in enumerate(comp["competidores"], 1):
                    st.markdown(f"""
                    <div class='aidu-card'>
                        <div style='display:flex; justify-content:space-between; align-items:center;'>
                            <div style='flex:1;'>
                                <div class='aidu-card-title'>#{i} {c['nombre']}</div>
                                <div class='aidu-card-meta'>{c['n_adjudicaciones']} adjudicaciones · descuento promedio {c['descuento_promedio_pct']:.1f}%</div>
                            </div>
                            <div style='text-align:right;'>
                                <div style='font-size:11px; color:#94A3B8;'>Win rate</div>
                                <div style='font-size:18px; font-weight:700; color:#1E40AF;'>{c['win_rate_pct']:.1f}%</div>
                                <div style='font-size:11px; color:#64748B;'>{formato_clp(c['monto_total_clp'])}</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Sin competidores con estos filtros")
        except Exception as e:
            st.warning("⚠️ Análisis de competencia no disponible.")
            with st.expander("Detalle"):
                st.code(str(e))


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
