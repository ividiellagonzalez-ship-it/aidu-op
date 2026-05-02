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
    --aidu-blue: #1E40AF;
    --aidu-blue-light: #3B82F6;
    --aidu-blue-dark: #1E3A8A;
    --aidu-blue-50: #EFF6FF;
    --aidu-blue-100: #DBEAFE;
    
    --aidu-success: #15803D;
    --aidu-success-bg: #D1FAE5;
    --aidu-warning: #D97706;
    --aidu-warning-bg: #FEF3C7;
    --aidu-danger: #DC2626;
    --aidu-danger-bg: #FEE2E2;
    
    --aidu-gray-50: #F8FAFC;
    --aidu-gray-100: #F1F5F9;
    --aidu-gray-200: #E2E8F0;
    --aidu-gray-300: #CBD5E1;
    --aidu-gray-500: #64748B;
    --aidu-gray-700: #334155;
    --aidu-gray-900: #0F172A;
    
    --shadow-xs: 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-sm: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
    --shadow-md: 0 4px 12px rgba(15, 23, 42, 0.08), 0 2px 4px rgba(15, 23, 42, 0.04);
    --shadow-lg: 0 10px 25px rgba(15, 23, 42, 0.12), 0 4px 8px rgba(15, 23, 42, 0.06);
    --shadow-xl: 0 20px 40px rgba(15, 23, 42, 0.15), 0 10px 20px rgba(15, 23, 42, 0.08);
    --shadow-glow: 0 0 24px rgba(59, 130, 246, 0.25);
    
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
.estado-PROSPECTO { background: #F1F5F9; color: #475569; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-ESTUDIO { background: #CFFAFE; color: #0E7490; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-EN_PREPARACION { background: #DBEAFE; color: #1E40AF; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-LISTO_OFERTAR { background: #FED7AA; color: #9A3412; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
.estado-OFERTADO { background: #E9D5FF; color: #6B21A8; padding: 4px 12px; border-radius: 999px; font-size: 11px; font-weight: 700; letter-spacing: 0.5px; }
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

/* Reducir padding superior global */
.block-container {
    padding-top: 1.5rem !important;
    max-width: 1280px;
}

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
    """
    Vista de detalle completa y profesional de un proyecto.
    Integra: info, IA bases, comparables, predicción descuento, equipo, paquete, bitácora.
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
    
    # Color del estado
    color_estado_map = {
        "PROSPECTO": ("#64748B", "#F1F5F9"),
        "ESTUDIO": ("#0E7490", "#CFFAFE"),
        "EN_PREPARACION": ("#1E40AF", "#DBEAFE"),
        "LISTO_OFERTAR": ("#9A3412", "#FED7AA"),
        "OFERTADO": ("#6B21A8", "#E9D5FF"),
        "ADJUDICADO": ("#14532D", "#BBF7D0"),
        "PERDIDO": ("#7F1D1D", "#FEE2E2"),
        "DESCARTADO": ("#475569", "#F1F5F9"),
    }
    color, bg = color_estado_map.get(p["estado"], ("#64748B", "#F1F5F9"))
    
    # Días para cierre
    dias_cierre = calcular_dias_cierre(p.get("fecha_cierre")) if p.get("fecha_cierre") else None
    color_dias = "#DC2626" if dias_cierre is not None and dias_cierre <= 3 else "#D97706" if dias_cierre is not None and dias_cierre <= 7 else "#15803D"
    
    # ===== HEADER PROFESIONAL =====
    col_back, col_acciones = st.columns([1, 4])
    
    with col_back:
        if st.button("← Volver", use_container_width=True, key="back_detalle"):
            st.session_state.view_proyecto_id = None
            st.rerun()
    
    # URL Mercado Público
    url_mp = f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={p['codigo_externo']}"
    
    with col_acciones:
        st.markdown(f"""
        <div style='display:flex; gap:8px; justify-content:flex-end;'>
            <a href='{url_mp}' target='_blank' style='display:inline-flex; align-items:center; gap:6px; padding:8px 14px; background:#1E40AF; color:white; border-radius:8px; text-decoration:none; font-weight:600; font-size:13px; box-shadow:0 1px 2px rgba(0,0,0,0.05);'>
                🌐 Abrir en Mercado Público
            </a>
        </div>
        """, unsafe_allow_html=True)
    
    # Header con todos los datos clave
    st.markdown(f"""
    <div style='background:linear-gradient(135deg, {bg} 0%, white 80%); padding:24px 28px; border-radius:14px; margin:16px 0 24px; border-left:5px solid {color}; box-shadow:0 4px 12px rgba(15,23,42,0.06);'>
        <div style='display:flex; justify-content:space-between; align-items:start; margin-bottom:8px;'>
            <div style='flex:1;'>
                <div style='display:flex; align-items:center; gap:10px; margin-bottom:8px;'>
                    <span class='estado-{p["estado"]}'>{p["estado"]}</span>
                    <span style='font-family:JetBrains Mono,monospace; font-size:12px; color:#64748B;'>{p["codigo_externo"]}</span>
                </div>
                <div style='font-size:24px; font-weight:700; color:#0F172A; line-height:1.2; margin-bottom:6px;'>{p["nombre"]}</div>
                <div style='font-size:13px; color:#64748B;'>
                    🏛️ {p.get("organismo") or "—"} · 📍 {p.get("region") or "—"} · 🎯 {p.get("cod_servicio_aidu") or "Sin categoría"}
                </div>
            </div>
            <div style='text-align:right; min-width:200px;'>
                <div style='font-size:12px; color:#64748B; font-weight:600; text-transform:uppercase; letter-spacing:0.5px;'>Monto referencial</div>
                <div style='font-size:32px; font-weight:800; color:#1E40AF; letter-spacing:-1px;'>{formato_clp(p.get("monto_referencial", 0))}</div>
                {f'<div style="font-size:13px; font-weight:600; color:{color_dias}; margin-top:4px;">⏰ {dias_cierre} días para cerrar</div>' if dias_cierre is not None else ''}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ===== ACCIONES DE ESTADO (cambio rápido entre fases) =====
    flow_estados = [
        ("PROSPECTO", "📂 Cartera"),
        ("ESTUDIO", "🔬 Estudio"),
        ("EN_PREPARACION", "🛠️ Preparación"),
        ("LISTO_OFERTAR", "📝 Ofertar"),
        ("OFERTADO", "📤 Subido a MP"),
    ]
    
    estado_idx = next((i for i, (e, _) in enumerate(flow_estados) if e == p["estado"]), -1)
    
    if estado_idx >= 0 and estado_idx < len(flow_estados) - 1:
        siguiente_estado, siguiente_label = flow_estados[estado_idx + 1]
        col_avance1, col_avance2, col_avance3 = st.columns([2, 2, 1])
        
        with col_avance1:
            if st.button(f"➡️ Avanzar a {siguiente_label}", type="primary", use_container_width=True, key="avanzar"):
                _cambiar_estado(proyecto_id, siguiente_estado)
                st.success(f"✅ Avanzado a {siguiente_label}")
                st.rerun()
        
        with col_avance2:
            if estado_idx > 0:
                anterior_estado, anterior_label = flow_estados[estado_idx - 1]
                if st.button(f"⬅️ Retroceder a {anterior_label}", use_container_width=True, key="retroceder"):
                    _cambiar_estado(proyecto_id, anterior_estado)
                    st.rerun()
        
        with col_avance3:
            if st.button("❌ Descartar", use_container_width=True, key="descartar"):
                _cambiar_estado(proyecto_id, "DESCARTADO")
                st.rerun()
    
    # ===== TABS DE LA FICHA =====
    t_resumen, t_ia, t_precios, t_comparables, t_check, t_equipo, t_paquete, t_bitacora = st.tabs([
        "📋 Resumen",
        "🤖 Análisis IA",
        "💰 Inteligencia precios",
        "📚 Comparables",
        "✅ Precalificación",
        "👥 Equipo & HH",
        "📦 Paquete",
        "📝 Bitácora",
    ])
    
    # ============ TAB 1: RESUMEN ============
    with t_resumen:
        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.markdown("##### 📌 Información general")
            st.markdown(f"""
            <div style='background:white; padding:16px 20px; border:1px solid #E2E8F0; border-radius:10px;'>
                <table style='width:100%; font-size:13px;'>
                    <tr><td style='color:#64748B; padding:6px 0;'>Código MP</td><td style='font-family:JetBrains Mono,monospace; font-weight:600;'>{p["codigo_externo"]}</td></tr>
                    <tr><td style='color:#64748B; padding:6px 0;'>Mandante</td><td style='font-weight:500;'>{p.get("organismo") or "—"}</td></tr>
                    <tr><td style='color:#64748B; padding:6px 0;'>Región</td><td>{p.get("region") or "—"}</td></tr>
                    <tr><td style='color:#64748B; padding:6px 0;'>Categoría AIDU</td><td>{p.get("cod_servicio_aidu") or "—"}</td></tr>
                    <tr><td style='color:#64748B; padding:6px 0;'>Estado actual</td><td><span class='estado-{p["estado"]}'>{p["estado"]}</span></td></tr>
                    <tr><td style='color:#64748B; padding:6px 0;'>Fecha publicación</td><td>{p.get("fecha_publicacion") or "—"}</td></tr>
                    <tr><td style='color:#64748B; padding:6px 0;'>Fecha cierre</td><td><strong style='color:{color_dias};'>{p.get("fecha_cierre") or "—"} {f"({dias_cierre}d)" if dias_cierre is not None else ""}</strong></td></tr>
                </table>
            </div>
            """, unsafe_allow_html=True)
            
            if p.get("descripcion"):
                st.markdown("##### 📄 Descripción")
                st.markdown(f"<div style='background:#F8FAFC; padding:14px 18px; border-radius:8px; font-size:13px; color:#334155; line-height:1.6;'>{p['descripcion']}</div>", unsafe_allow_html=True)
            
            if p.get("notas"):
                st.markdown("##### 🗒️ Notas")
                st.markdown(f"<div style='background:#FEF3C7; padding:14px 18px; border-radius:8px; font-size:13px; color:#78350F; line-height:1.6; white-space:pre-wrap;'>{p['notas']}</div>", unsafe_allow_html=True)
        
        with col2:
            st.markdown("##### 💰 Resumen económico")
            
            try:
                from app.core.configuracion import obtener_config
                cfg = obtener_config()
                tarifa = cfg.tarifa_hora_clp
                overhead = cfg.overhead_pct
            except Exception:
                tarifa = 78000
                overhead = 18
            
            costo_hora = int(tarifa * (1 + overhead / 100))
            
            monto_ref = p.get("monto_referencial", 0) or 0
            sweet_min = 3_000_000
            sweet_max = 15_000_000
            
            if monto_ref < sweet_min:
                zona = ("⚠️ Por debajo del sweet spot", "#D97706")
            elif monto_ref > sweet_max:
                zona = ("⚠️ Por encima del sweet spot", "#D97706")
            else:
                zona = ("✅ Dentro del sweet spot", "#15803D")
            
            st.markdown(f"""
            <div style='background:white; padding:18px; border:1px solid #E2E8F0; border-radius:10px;'>
                <div style='font-size:11px; color:#64748B; text-transform:uppercase; font-weight:600; letter-spacing:0.5px;'>Monto referencial</div>
                <div style='font-size:26px; font-weight:800; color:#1E40AF; margin:4px 0 8px;'>{formato_clp(monto_ref)}</div>
                <div style='font-size:11px; font-weight:600; color:{zona[1]}; padding:4px 8px; background:{zona[1]}15; border-radius:4px; display:inline-block; margin-bottom:14px;'>{zona[0]}</div>
                
                <div style='border-top:1px solid #F1F5F9; padding-top:12px; margin-top:8px;'>
                    <div style='display:flex; justify-content:space-between; font-size:12px; color:#64748B; padding:4px 0;'>
                        <span>Tarifa hora</span><span style='font-weight:600; color:#0F172A;'>{formato_clp(tarifa)}</span>
                    </div>
                    <div style='display:flex; justify-content:space-between; font-size:12px; color:#64748B; padding:4px 0;'>
                        <span>Costo c/overhead</span><span style='font-weight:600; color:#0F172A;'>{formato_clp(costo_hora)}</span>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # Predicción descuento rápida
            try:
                from app.core.inteligencia_avanzada import predecir_descuento_optimo
                pred = predecir_descuento_optimo(
                    p.get("cod_servicio_aidu") or "",
                    p.get("organismo"),
                    p.get("monto_referencial")
                )
                
                color_p = "#15803D" if pred["confianza"] >= 0.6 else "#D97706"
                
                st.markdown(f"""
                <div style='background:linear-gradient(135deg, {color_p}10 0%, white 80%); padding:16px; border:1px solid #E2E8F0; border-left:3px solid {color_p}; border-radius:10px; margin-top:12px;'>
                    <div style='font-size:11px; color:{color_p}; text-transform:uppercase; font-weight:700; letter-spacing:0.5px;'>🎯 Descuento recomendado</div>
                    <div style='font-size:32px; font-weight:800; color:{color_p}; line-height:1; margin:6px 0;'>{pred['descuento_recomendado_pct']}%</div>
                    <div style='font-size:11px; color:#64748B;'>Banda: {pred['descuento_minimo_pct']}% – {pred['descuento_maximo_pct']}%</div>
                    <div style='font-size:11px; color:#64748B; margin-top:6px;'>Confianza: <strong style='color:{color_p};'>{pred['confianza']*100:.0f}%</strong></div>
                </div>
                """, unsafe_allow_html=True)
            except Exception:
                pass
    
    # ============ TAB 2: ANÁLISIS IA ============
    with t_ia:
        st.markdown("##### 🤖 Análisis IA de bases técnicas")
        st.caption("Sube el PDF de las bases y Claude extraerá requisitos, plazos, riesgos y recomendación")
        
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
                
                st.markdown(f"""
                <div style='padding:20px; background:linear-gradient(135deg, {color_r}15 0%, white 70%); border-left:5px solid {color_r}; border-radius:12px; margin:16px 0;'>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <div style='font-size:22px; font-weight:800; color:{color_r};'>{label_r}</div>
                        <div style='text-align:right;'>
                            <div style='font-size:11px; color:#64748B;'>Confianza Claude</div>
                            <div style='font-size:24px; font-weight:800; color:{color_r};'>{rec.get("confianza", 0)}%</div>
                        </div>
                    </div>
                    <div style='font-size:14px; color:#334155; margin-top:10px; line-height:1.6;'>{resultado.get("resumen_ejecutivo", "")}</div>
                </div>
                """, unsafe_allow_html=True)
                
                # Razones
                razones = rec.get("razones_principales", [])
                if razones:
                    cols_r = st.columns(min(len(razones), 3))
                    for i, razon in enumerate(razones):
                        cols_r[i % 3].markdown(f"""
                        <div style='padding:12px; background:white; border:1px solid #E2E8F0; border-radius:8px; height:100%;'>
                            <div style='font-size:11px; color:#64748B; font-weight:600;'>RAZÓN {i+1}</div>
                            <div style='font-size:13px; color:#0F172A; margin-top:4px;'>{razon}</div>
                        </div>
                        """, unsafe_allow_html=True)
                
                # Resumen requisitos
                requisitos = resultado.get("requisitos_eliminatorios", [])
                if requisitos:
                    n_si = sum(1 for r in requisitos if r.get("puede_cumplir") == "si")
                    n_no = sum(1 for r in requisitos if r.get("puede_cumplir") == "no")
                    n_inc = len(requisitos) - n_si - n_no
                    
                    st.markdown("###### Requisitos eliminatorios")
                    rc1, rc2, rc3 = st.columns(3)
                    rc1.metric("✅ Cumplibles", n_si)
                    rc2.metric("❌ No cumplibles", n_no)
                    rc3.metric("⚠️ Inciertos", n_inc)
                    
                    with st.expander("Ver detalle de requisitos"):
                        for req in requisitos:
                            puede = req.get("puede_cumplir", "incierto")
                            icon = "✅" if puede == "si" else "❌" if puede == "no" else "⚠️"
                            st.markdown(f"**{icon} {req.get('requisito', '—')}** — {req.get('comentario', '')}")
                
                col_r1, col_r2 = st.columns(2)
                with col_r1:
                    if st.button("🔄 Re-analizar (nuevo PDF)", use_container_width=True):
                        st.session_state["ia_reupload"] = True
                with col_r2:
                    if st.button("📊 Ver análisis completo", use_container_width=True):
                        st.session_state["ia_proyecto_pre"] = p["codigo_externo"]
                        st.session_state["nav_principal"] = "🤖 Análisis IA"
                        st.session_state.view_proyecto_id = None
                        st.rerun()
            
            if not ultimo or st.session_state.get("ia_reupload"):
                st.info("Aún no se ha analizado las bases técnicas de este proyecto")
                
                archivo = st.file_uploader(
                    "📄 Sube el PDF de las bases técnicas",
                    type=["pdf"],
                    key=f"upload_ia_{proyecto_id}"
                )
                
                if archivo and st.button("🚀 Analizar con Claude", type="primary", use_container_width=True, key="run_ia"):
                    with st.spinner("🤖 Claude está leyendo las bases..."):
                        pdf_bytes = archivo.read()
                        resultado = analizar_pdf_bases(
                            pdf_bytes,
                            codigo_licitacion=p["codigo_externo"],
                            proyecto_id=proyecto_id,
                            forzar_reanalisis=True
                        )
                    
                    if resultado["ok"]:
                        st.success(f"✅ Análisis completado · ${resultado['meta']['costo_usd']:.4f} USD")
                        st.session_state["ia_reupload"] = False
                        st.rerun()
                    else:
                        st.error(f"❌ {resultado.get('error')}")
        except Exception as e:
            st.warning(f"⚠️ Módulo IA no disponible: {e}")
    
    # ============ TAB 3: INTELIGENCIA PRECIOS ============
    with t_precios:
        st.markdown("##### 💰 Inteligencia de precios y márgenes")
        
        try:
            from app.core.inteligencia_avanzada import predecir_descuento_optimo
            
            pred = predecir_descuento_optimo(
                p.get("cod_servicio_aidu") or "",
                p.get("organismo"),
                p.get("monto_referencial")
            )
            
            col1, col2, col3 = st.columns(3)
            col1.metric("🎯 Descuento óptimo", f"{pred['descuento_recomendado_pct']}%", help=pred["razon"])
            col2.metric("📉 Mínimo seguro", f"{pred['descuento_minimo_pct']}%")
            col3.metric("📈 Máximo arriesgado", f"{pred['descuento_maximo_pct']}%")
            
            st.caption(f"💡 {pred['razon']} · Confianza: {pred['confianza']*100:.0f}%")
            
            # Histórico mandante
            if pred.get("historico_mandante"):
                hm = pred["historico_mandante"]
                st.markdown("###### 🏛️ Histórico con este mandante")
                cm1, cm2, cm3 = st.columns(3)
                cm1.metric("Proyectos previos", hm["n_proyectos"])
                cm2.metric("Descuento promedio", f"{hm['descuento_promedio_pct']}%")
                cm3.metric("Rango histórico", f"{hm['descuento_min_pct']}% – {hm['descuento_max_pct']}%")
            
            # Escenarios calculados
            try:
                escenarios = calcular_escenarios_precio(proyecto_id)
                
                if escenarios.get("ok"):
                    st.markdown("###### 📊 Escenarios de precio")
                    
                    cols = st.columns(3)
                    for i, (key, label, clase) in enumerate([
                        ("agresivo", "Agresivo", "agresivo"),
                        ("competitivo", "Competitivo", "competitivo"),
                        ("premium", "Premium", "premium"),
                    ]):
                        e = escenarios.get(key, {})
                        cols[i].markdown(f"""
                        <div class='escenario-card escenario-{clase}'>
                            <div class='esc-label'>{label}</div>
                            <div class='esc-precio'>{formato_clp(e.get("precio", 0))}</div>
                            <div class='esc-margen'>Margen: {e.get("margen_pct", 0):.1f}%</div>
                            <div class='esc-prob'>Prob: {e.get("probabilidad", 0)}%</div>
                        </div>
                        """, unsafe_allow_html=True)
            except Exception:
                pass
        except Exception as e:
            st.info("La inteligencia de precios requiere proyectos con histórico para predecir bien")
    
    # ============ TAB 4: COMPARABLES ============
    with t_comparables:
        st.markdown("##### 📚 Licitaciones similares en el histórico")
        
        try:
            from app.core.comparables import buscar_comparables
            
            comp = buscar_comparables(
                cod_servicio_aidu=p.get("cod_servicio_aidu"),
                organismo=p.get("organismo"),
                limit=10
            )
            
            if comp.get("comparables"):
                stats = comp.get("stats", {})
                col1, col2, col3 = st.columns(3)
                col1.metric("Comparables", comp["total_encontrados"])
                col2.metric("Descuento mediana", f"{stats.get('descuento_mediana', 0):.1f}%")
                col3.metric("Adjudicaciones", stats.get("n_adjudicadas", 0))
                
                st.markdown("###### 📋 Top 10")
                for c in comp["comparables"][:10]:
                    desc = c.get("descuento_pct")
                    desc_str = f"Δ {desc:+.1f}%" if desc is not None else ""
                    st.markdown(f"""
                    <div class='aidu-card' style='padding:12px 16px;'>
                        <div style='display:flex; justify-content:space-between; align-items:start;'>
                            <div style='flex:1;'>
                                <div class='aidu-card-title'>{c["nombre"]}</div>
                                <div class='aidu-card-meta'>🏛️ {c.get("organismo") or "—"} · {formato_clp(c.get("monto_adjudicado", 0))} · {desc_str}</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("Sin comparables en el histórico para este perfil")
        except Exception:
            st.info("Comparables no disponibles")
    
    # ============ TAB 5: PRECALIFICACIÓN ============
    with t_check:
        st.markdown("##### ✅ Checklist de precalificación")
        st.caption("Verifica todos los requisitos antes de avanzar a Ofertar")
        
        try:
            from app.core.precalificacion import obtener_checklist, actualizar_item_checklist, ITEMS_CHECKLIST_DEFAULT
            
            checklist = obtener_checklist(proyecto_id)
            
            if not checklist:
                st.info("Generando checklist inicial...")
                # Inicializar checklist desde default
                conn = get_connection()
                for item in ITEMS_CHECKLIST_DEFAULT:
                    conn.execute("""
                        INSERT OR IGNORE INTO proy_checklist (proyecto_id, item_id, descripcion, estado, comentario)
                        VALUES (?, ?, ?, 'PENDIENTE', '')
                    """, (proyecto_id, item["id"], item["descripcion"]))
                conn.commit()
                conn.close()
                st.rerun()
            
            n_ok = sum(1 for it in checklist if it["estado"] == "OK")
            n_falta = sum(1 for it in checklist if it["estado"] == "FALTA")
            n_pend = sum(1 for it in checklist if it["estado"] == "PENDIENTE")
            
            cc1, cc2, cc3, cc4 = st.columns(4)
            cc1.metric("✅ OK", n_ok)
            cc2.metric("❌ Falta", n_falta)
            cc3.metric("⏳ Pendiente", n_pend)
            cc4.metric("Total", len(checklist))
            
            # Progreso visual
            progreso_pct = int((n_ok / len(checklist)) * 100) if checklist else 0
            st.progress(progreso_pct / 100, text=f"Progreso: {progreso_pct}%")
            
            for it in checklist[:20]:
                color_icon = "#15803D" if it["estado"] == "OK" else "#DC2626" if it["estado"] == "FALTA" else "#94A3B8"
                icon = "✅" if it["estado"] == "OK" else "❌" if it["estado"] == "FALTA" else "⏳"
                
                col_i, col_act = st.columns([4, 1])
                col_i.markdown(f"""
                <div style='padding:8px 12px; background:white; border:1px solid #E2E8F0; border-radius:6px; margin-bottom:4px;'>
                    <div style='display:flex; justify-content:space-between; align-items:center;'>
                        <span style='font-size:13px;'>{icon} {it["descripcion"]}</span>
                        <span style='font-size:10px; color:{color_icon}; font-weight:700;'>{it["estado"]}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                with col_act:
                    nuevo = st.selectbox(
                        "estado",
                        ["PENDIENTE", "OK", "FALTA", "NA"],
                        index=["PENDIENTE", "OK", "FALTA", "NA"].index(it["estado"]) if it["estado"] in ["PENDIENTE", "OK", "FALTA", "NA"] else 0,
                        key=f"check_{it['item_id']}",
                        label_visibility="collapsed"
                    )
                    if nuevo != it["estado"]:
                        actualizar_item_checklist(proyecto_id, it["item_id"], nuevo)
                        st.rerun()
        except Exception as e:
            st.info(f"Checklist no disponible: {e}")
    
    # ============ TAB 6: EQUIPO & HH ============
    with t_equipo:
        st.markdown("##### 👥 Estimación de equipo y horas hombre")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("###### Estimación")
            hh_ig_est = st.number_input("HH Ignacio (estimadas)", value=p.get("hh_ignacio_estimado") or 40, min_value=0, key="hh_ig_est")
            hh_jo_est = st.number_input("HH Jorella (estimadas)", value=p.get("hh_jorella_estimado") or 20, min_value=0, key="hh_jo_est")
        
        with col2:
            st.markdown("###### Real (a la fecha)")
            hh_ig_real = st.number_input("HH Ignacio (real)", value=p.get("hh_ignacio_real") or 0, min_value=0, key="hh_ig_real")
            hh_jo_real = st.number_input("HH Jorella (real)", value=p.get("hh_jorella_real") or 0, min_value=0, key="hh_jo_real")
        
        if st.button("💾 Guardar HH", type="primary"):
            conn = get_connection()
            conn.execute("""
                UPDATE aidu_proyectos
                SET hh_ignacio_estimado=?, hh_jorella_estimado=?, hh_ignacio_real=?, hh_jorella_real=?
                WHERE id=?
            """, (hh_ig_est, hh_jo_est, hh_ig_real, hh_jo_real, proyecto_id))
            conn.commit()
            conn.close()
            st.success("✅ Guardado")
            st.rerun()
        
        # Cálculo de costos
        try:
            from app.core.configuracion import obtener_config
            cfg = obtener_config()
            costo_total_est = (hh_ig_est + hh_jo_est) * cfg.costo_hora_total
            costo_total_real = (hh_ig_real + hh_jo_real) * cfg.costo_hora_total
            
            st.divider()
            st.markdown("###### 💰 Costo estimado vs real")
            
            ce1, ce2, ce3 = st.columns(3)
            ce1.metric("Costo estimado", formato_clp(costo_total_est))
            ce2.metric("Costo real", formato_clp(costo_total_real))
            
            if hh_ig_est + hh_jo_est > 0:
                pct_completado = ((hh_ig_real + hh_jo_real) / (hh_ig_est + hh_jo_est)) * 100
                ce3.metric("% Completado", f"{pct_completado:.0f}%")
        except Exception:
            pass
    
    # ============ TAB 7: PAQUETE ============
    with t_paquete:
        st.markdown("##### 📦 Paquete de oferta")
        st.caption("Generación automática de Word + Excel + Anexos")
        
        if p.get("paquete_generado"):
            st.success(f"✅ Paquete ya generado · {p.get('paquete_path', '')}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📝 Generar Word (Propuesta técnica)", use_container_width=True, type="primary"):
                try:
                    from app.core.generador_paquete import generar_word_propuesta
                    path = generar_word_propuesta(proyecto_id)
                    if path:
                        st.success(f"✅ Word generado: {path}")
                        with open(path, "rb") as f:
                            st.download_button("⬇️ Descargar Word", f, file_name=f"{p['codigo_externo']}_propuesta.docx")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        with col2:
            if st.button("📊 Generar Excel (Oferta económica)", use_container_width=True, type="primary"):
                try:
                    from app.core.generador_paquete import generar_excel_economico
                    path = generar_excel_economico(proyecto_id)
                    if path:
                        st.success(f"✅ Excel generado: {path}")
                        with open(path, "rb") as f:
                            st.download_button("⬇️ Descargar Excel", f, file_name=f"{p['codigo_externo']}_economico.xlsx")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        st.divider()
        st.markdown("###### 📋 Lo que incluye el paquete")
        st.markdown("""
        - 📄 **Word**: Carta presentación, Propuesta técnica, Equipo, Cronograma, Anexos
        - 📊 **Excel**: Oferta económica con cubicaciones, Cronograma de pago, Resumen
        - 📁 **Anexos**: Declaraciones juradas prellenadas con tus datos (RUT, patente, etc.)
        """)
    
    # ============ TAB 8: BITÁCORA ============
    with t_bitacora:
        st.markdown("##### 📝 Bitácora cronológica")
        
        # Form para nueva nota
        with st.expander("➕ Agregar nota", expanded=False):
            nueva_nota = st.text_area("Nota", key="nueva_nota_proy", height=100)
            if st.button("💾 Guardar nota", type="primary"):
                if nueva_nota.strip():
                    conn = get_connection()
                    conn.execute("""
                        INSERT INTO bitacora (proyecto_id, tipo, mensaje)
                        VALUES (?, 'nota', ?)
                    """, (proyecto_id, nueva_nota.strip()))
                    conn.commit()
                    conn.close()
                    st.success("Nota guardada")
                    st.rerun()
        
        # Listar bitácora
        conn = get_connection()
        eventos = conn.execute("""
            SELECT * FROM bitacora WHERE proyecto_id = ?
            ORDER BY fecha DESC LIMIT 50
        """, (proyecto_id,)).fetchall()
        conn.close()
        
        if not eventos:
            st.caption("Sin eventos registrados aún")
        else:
            for e in eventos:
                tipo = e["tipo"] if "tipo" in e.keys() else "evento"
                icon_map = {
                    "nota": "📝", "estado_cambio": "🔄", "ia": "🤖", 
                    "paquete": "📦", "checklist": "✅", "sistema": "⚙️"
                }
                icon = icon_map.get(tipo, "•")
                
                st.markdown(f"""
                <div style='padding:12px 16px; background:white; border:1px solid #E2E8F0; border-left:3px solid #1E40AF; border-radius:8px; margin-bottom:8px;'>
                    <div style='display:flex; justify-content:space-between; margin-bottom:4px;'>
                        <span style='font-weight:600; font-size:13px; color:#0F172A;'>{icon} {tipo.upper()}</span>
                        <span style='font-size:11px; color:#94A3B8; font-family:JetBrains Mono,monospace;'>{e["fecha"][:16]}</span>
                    </div>
                    <div style='font-size:13px; color:#334155; line-height:1.5;'>{e["mensaje"]}</div>
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
        [
            "🏠 Dashboard",
            "─── EMBUDO ───",
            "🔍 1. Buscar",
            "📂 2. Cartera",
            "🔬 3. Estudio",
            "📝 4. Ofertar",
            "📤 5. Subir a MP",
            "─── INTELIGENCIA ───",
            "📊 Inteligencia",
            "🤖 Análisis IA",
            "─── ADMIN ───",
            "⚙️ Configuración",
            "🛠️ Sistema",
        ],
        label_visibility="collapsed",
        key="nav_principal",
    )
    
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
    
    st.markdown(f"""
    <div style='font-size:10px; color:#94A3B8; padding:0 8px;'>
        <div>Última sync: <strong style='color:#475569;'>{ult_act}</strong></div>
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
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:32px;">🏠 Dashboard</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">Vista ejecutiva del estado actual de AIDU Op · El embudo de ventas en tiempo real</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Stats rápidas del día
    try:
        from app.core.descarga_diaria import stats_vigentes, ejecutar_descarga, listar_vigentes
        st_vig = stats_vigentes()
        
        st.markdown("##### 📡 Hoy en Mercado Público")
        
        col_h1, col_h2, col_h3, col_h4, col_h5 = st.columns(5)
        col_h1.metric("📡 Vigentes total", st_vig["total_vigentes"])
        col_h2.metric("🟢 Publicadas 24h", st_vig["publicadas_24h"])
        col_h3.metric("🔴 Cierran ≤3d", st_vig["cierran_proximos_3_dias"])
        col_h4.metric("🎯 Match AIDU", st_vig["con_match_aidu"])
        
        with col_h5:
            st.caption("&nbsp;")
            if st.button("🔄 Sincronizar MP", use_container_width=True, key="sync_dashboard"):
                with st.spinner("Descargando licitaciones nuevas..."):
                    try:
                        res = ejecutar_descarga(dias_atras=3)
                        st.success(f"✅ {res['nuevas']} nuevas, {res['categorizadas_aidu']} con match AIDU")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error: {e}")
    except Exception as e:
        st.info("Configura el ticket de Mercado Público en Sistema para activar la sincronización automática.")
    
    st.divider()
    
    # ====== EMBUDO VISUAL ======
    st.markdown("##### 🚀 Tu embudo comercial")
    
    conn = get_connection()
    try:
        embudo_counts = {}
        for estado in ["PROSPECTO", "ESTUDIO", "EN_PREPARACION", "LISTO_OFERTAR", "OFERTADO"]:
            row = conn.execute(
                "SELECT COUNT(*) as n, SUM(monto_referencial) as monto FROM aidu_proyectos WHERE estado = ?",
                (estado,)
            ).fetchone()
            embudo_counts[estado] = {"n": row["n"] or 0, "monto": row["monto"] or 0}
        
        # Total
        adj_row = conn.execute(
            "SELECT COUNT(*) as n, SUM(monto_referencial) as monto FROM aidu_proyectos WHERE estado = 'ADJUDICADO'"
        ).fetchone()
        adjudicadas = {"n": adj_row["n"] or 0, "monto": adj_row["monto"] or 0}
    finally:
        conn.close()
    
    embudo_def = [
        ("PROSPECTO", "📂 2. Cartera", "Seleccionadas", "#64748B", "#F1F5F9"),
        ("ESTUDIO", "🔬 3. Estudio", "Análisis profundo", "#0E7490", "#CFFAFE"),
        ("EN_PREPARACION", "🔬 3. Estudio", "Preparación oferta", "#1E40AF", "#DBEAFE"),
        ("LISTO_OFERTAR", "📝 4. Ofertar", "Lista para enviar", "#9A3412", "#FED7AA"),
        ("OFERTADO", "📤 5. Subir a MP", "En MP", "#6B21A8", "#E9D5FF"),
    ]
    
    cols = st.columns(5)
    for i, (estado, label, sub, color, bg) in enumerate(embudo_def):
        data = embudo_counts.get(estado, {"n": 0, "monto": 0})
        cols[i].markdown(f"""
        <div style='padding:18px 16px; background:{bg}; border-radius:12px; text-align:center; border-top:3px solid {color}; height:140px;'>
            <div style='font-size:10px; font-weight:700; color:{color}; letter-spacing:1px; text-transform:uppercase;'>{estado}</div>
            <div style='font-size:36px; font-weight:800; color:{color}; line-height:1; margin:6px 0;'>{data['n']}</div>
            <div style='font-size:11px; color:#64748B; margin-bottom:6px;'>{sub}</div>
            <div style='font-size:13px; font-weight:600; color:#0F172A;'>{formato_clp(data['monto'])}</div>
        </div>
        """, unsafe_allow_html=True)
    
    # Flecha entre columnas (decorativa)
    st.caption("Flujo: Cartera → Estudio → Ofertar → Subir a MP → Adjudicado")
    
    if adjudicadas["n"] > 0:
        st.success(f"🎉 **{adjudicadas['n']} licitaciones adjudicadas** · Monto total: {formato_clp(adjudicadas['monto'])}")
    
    st.divider()
    
    # ====== FORECAST + ATAJOS ======
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.markdown("##### 💰 Proyección 90 días")
        try:
            from app.core.inteligencia_avanzada import forecast_pipeline_90d
            f = forecast_pipeline_90d()
            
            cm1, cm2, cm3 = st.columns(3)
            cm1.metric("Pipeline total", formato_clp(f["valor_pipeline_total_clp"]))
            cm2.metric("Valor esperado", formato_clp(f["valor_esperado_clp"]), help="Ponderado por probabilidad")
            cm3.metric("Ingresos proy.", formato_clp(f["ingresos_esperados_clp"]), help=f"Aplicando margen {f['margen_aplicado_pct']:.0f}%")
        except Exception as e:
            st.info("Forecast disponible cuando tengas proyectos en cartera")
    
    with col_right:
        st.markdown("##### ⚡ Acciones rápidas")
        
        if st.button("🔍 Buscar oportunidades nuevas", use_container_width=True):
            st.session_state["nav_principal"] = "🔍 1. Buscar"
            st.rerun()
        
        if st.button("🤖 Analizar bases con IA", use_container_width=True):
            st.session_state["nav_principal"] = "🤖 Análisis IA"
            st.rerun()
        
        if st.button("📊 Ver dashboard ejecutivo", use_container_width=True):
            st.session_state["nav_principal"] = "📊 Inteligencia"
            st.rerun()
    
    st.divider()
    
    # ====== ÚLTIMAS VIGENTES (las 5 más recientes) ======
    st.markdown("##### 🆕 Últimas oportunidades publicadas")
    
    try:
        ultimas = listar_vigentes(limit=5)
        if not ultimas:
            st.caption("Sin licitaciones nuevas. Click '🔄 Sincronizar MP' arriba para descargar.")
        else:
            for v in ultimas:
                dias_cierre = v.get("dias_para_cierre")
                if dias_cierre is not None and dias_cierre <= 3:
                    border_color = "#DC2626"
                elif dias_cierre is not None and dias_cierre <= 7:
                    border_color = "#D97706"
                else:
                    border_color = "#15803D"
                
                cat_aidu = v.get("cod_servicio_aidu") or "—"
                
                st.markdown(f"""
                <div class='aidu-card' style='border-left:3px solid {border_color};'>
                    <div style='display:flex; justify-content:space-between; align-items:start;'>
                        <div style='flex:1;'>
                            <div class='aidu-card-title'>{v['nombre']}</div>
                            <div class='aidu-card-meta'>
                                🏛️ {v.get('organismo') or '—'} · 📍 {v.get('region') or '—'} · 🎯 {cat_aidu}
                            </div>
                            <div class='aidu-card-code'>{v['codigo_externo']}</div>
                        </div>
                        <div style='text-align:right; min-width:140px;'>
                            <div style='font-weight:700; color:#1E40AF; font-size:16px;'>{formato_clp(v.get('monto_referencial', 0))}</div>
                            <div style='font-size:11px; color:{border_color}; font-weight:600;'>
                                {f"⏰ {dias_cierre}d" if dias_cierre is not None else "—"}
                            </div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
    except Exception:
        pass


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
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:32px;">📂 Cartera (Pre-selección)</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">
            Oportunidades seleccionadas desde Buscar · Pendientes de decisión: ¿pasan a Estudio profundo o las descartas?
        </p>
    </div>
    """, unsafe_allow_html=True)
    
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
    cols[5].metric("Adjudicadas", estados_count.get("ADJUDICADO", 0))

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
            "LISTO_OFERTAR": ("📤 Marcar como Ofertada", "OFERTADO"),
            "OFERTADO": ("✅ Marcar Adjudicada", "ADJUDICADO"),
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
                if dias is not None and dias <= 3 and p["estado"] not in ("OFERTADO", "ADJUDICADO", "PERDIDO"):
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
                elif p["estado"] == "ADJUDICADO":
                    col_a.success("🏆 Adjudicada")
                elif p["estado"] == "PERDIDO":
                    col_a.error("❌ Rechazada")

                if col_c.button("👁️ Ver detalle", key=f"det_{p['id']}", use_container_width=True):
                    st.session_state.view_proyecto_id = p["id"]
                    st.rerun()


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
# ============================================================
# 🔬 ESTUDIO — Análisis profundo + descarga de bases automática
# ============================================================
if tab_estudio:
    st.markdown("""
    <div class="aidu-hero">
        <h1 style="margin:0; font-size:32px;">🔬 Estudio</h1>
        <p style="margin:4px 0 0; font-size:14px; color:#64748B;">
            Análisis profundo de bases técnicas con IA · Descarga automática de documentación · Decisión final de cotizar
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    conn = get_connection()
    proyectos_estudio = conn.execute("""
        SELECT * FROM aidu_proyectos
        WHERE estado IN ('ESTUDIO', 'EN_PREPARACION')
        ORDER BY 
            CASE estado WHEN 'EN_PREPARACION' THEN 1 ELSE 2 END,
            fecha_cierre ASC
    """).fetchall()
    proyectos_estudio = [dict(p) for p in proyectos_estudio]
    conn.close()
    
    col_s1, col_s2, col_s3 = st.columns(3)
    en_estudio = sum(1 for p in proyectos_estudio if p["estado"] == "ESTUDIO")
    en_prep = sum(1 for p in proyectos_estudio if p["estado"] == "EN_PREPARACION")
    monto_total = sum(p.get("monto_referencial") or 0 for p in proyectos_estudio)
    
    col_s1.metric("🔬 En estudio", en_estudio)
    col_s2.metric("🛠️ En preparación", en_prep)
    col_s3.metric("Monto total", formato_clp(monto_total))
    
    if not proyectos_estudio:
        st.info("📭 Sin proyectos en estudio. Mueve proyectos desde Cartera para empezar el análisis profundo.")
        if st.button("📂 Ir a Cartera", type="primary"):
            st.session_state["nav_principal"] = "📂 2. Cartera"
            st.rerun()
    else:
        st.markdown("##### 📋 Proyectos en estudio")
        st.caption("Revisa los antecedentes en profundidad. Si la decisión es positiva, pasa a 'Ofertar' para confección de oferta.")
        
        for p in proyectos_estudio:
            color_estado = "#0E7490" if p["estado"] == "ESTUDIO" else "#1E40AF"
            
            with st.container():
                st.markdown(f"""
                <div class='aidu-card'>
                    <div style='display:flex; justify-content:space-between; align-items:start; margin-bottom:8px;'>
                        <div style='flex:1;'>
                            <div class='aidu-card-title'>{p['nombre']}</div>
                            <div class='aidu-card-meta'>
                                <span class='estado-{p["estado"]}'>{p["estado"]}</span> · 
                                🏛️ {p.get('organismo') or '—'} · 📍 {p.get('region') or '—'} · 
                                🎯 {p.get('cod_servicio_aidu') or 'Sin categoría'}
                            </div>
                        </div>
                        <div style='text-align:right; min-width:160px;'>
                            <div style='font-weight:700; color:{color_estado}; font-size:18px;'>{formato_clp(p.get('monto_referencial', 0))}</div>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                col_a, col_b, col_c, col_d = st.columns(4)
                
                with col_a:
                    if st.button("👁️ Ver detalle completo", key=f"ver_est_{p['id']}", use_container_width=True):
                        st.session_state["view_proyecto_id"] = p["id"]
                        st.rerun()
                
                with col_b:
                    if st.button("🤖 Analizar bases IA", key=f"ia_est_{p['id']}", use_container_width=True):
                        st.session_state["ia_proyecto_pre"] = p["codigo_externo"]
                        st.session_state["nav_principal"] = "🤖 Análisis IA"
                        st.rerun()
                
                with col_c:
                    if p["estado"] == "ESTUDIO":
                        if st.button("➡️ Pasar a Preparación", key=f"prep_{p['id']}", use_container_width=True, type="primary"):
                            conn = get_connection()
                            conn.execute("UPDATE aidu_proyectos SET estado='EN_PREPARACION' WHERE id=?", (p["id"],))
                            conn.commit()
                            conn.close()
                            st.success(f"✅ {p['nombre']} pasó a En Preparación")
                            st.rerun()
                    else:
                        if st.button("➡️ Pasar a Ofertar", key=f"of_{p['id']}", use_container_width=True, type="primary"):
                            conn = get_connection()
                            conn.execute("UPDATE aidu_proyectos SET estado='LISTO_OFERTAR' WHERE id=?", (p["id"],))
                            conn.commit()
                            conn.close()
                            st.success(f"✅ {p['nombre']} listo para ofertar")
                            st.rerun()
                
                with col_d:
                    if st.button("❌ Descartar", key=f"desc_est_{p['id']}", use_container_width=True):
                        conn = get_connection()
                        conn.execute("UPDATE aidu_proyectos SET estado='DESCARTADO' WHERE id=?", (p["id"],))
                        conn.commit()
                        conn.close()
                        st.warning(f"Proyecto descartado")
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
        WHERE estado = 'LISTO_OFERTAR'
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
            st.session_state["nav_principal"] = "🔬 3. Estudio"
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
                    conn.execute("UPDATE aidu_proyectos SET estado='OFERTADO' WHERE id=?", (p["id"],))
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
        WHERE estado = 'OFERTADO'
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
            st.session_state["nav_principal"] = "📝 4. Ofertar"
            st.rerun()
    else:
        st.markdown("##### 📋 Checklist de subida a MP")
        
        for p in proyectos_subir:
            dias = calcular_dias_cierre(p.get("fecha_cierre")) if p.get("fecha_cierre") else None
            border = "#DC2626" if dias is not None and dias <= 1 else "#D97706" if dias is not None and dias <= 3 else "#15803D"
            
            url_mp = f"https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?idlicitacion={p['codigo_externo']}"
            
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
                    conn.execute("UPDATE aidu_proyectos SET estado='OFERTADO', notas = COALESCE(notas, '') || char(10) || 'Subida a MP confirmada el ' || datetime('now', 'localtime') WHERE id=?", (p["id"],))
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
