"""
AIDU Op - Pagina multi-page Inteligencia de Mercado (S13.2)
=============================================================

Streamlit auto-descubre archivos en pages/ y los expone como entradas
del menu lateral nativo. Esta pagina es DELIBERADAMENTE independiente del
dashboard viejo `app/ui/streamlit_app.py`:

  - NO importa app.core.backfill (que crashea con el SQLite local corrupto)
  - NO importa app.core.descarga_diaria, app.core.enriquecimiento, etc.
  - Solo importa app.ui.inteligencia_mercado, cuyo data layer fue
    refactoreado en S13.2 para leer Turso por HTTP /v2/pipeline directo
    via turso_http_client (bypasa libsql y el SQLite local).

Resultado: aunque el dashboard viejo siga crasheando por la corrupcion
del archivo SQLite del container, ESTA pagina sigue accesible desde la
sidebar nativa de Streamlit Cloud y muestra los 658 items productivos
en Turso.

El emoji va en page_title/page_icon (NO en el nombre del archivo) para
evitar bugs de filesystem entre Windows / Linux / macOS runners.
"""
import sys
from pathlib import Path

# Asegurar imports relativos al repo (los pages corren con CWD = repo root,
# pero el container puede ejecutar desde un path distinto si el setup cambia).
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

st.set_page_config(
    page_title="Inteligencia de Mercado",
    page_icon="🛒",
    layout="wide",
)

# Import diferido para que cualquier crash en el modulo nuevo se vea aca
# y no en el load global de la app. Aislado de la cadena de imports del
# dashboard viejo (app/ui/streamlit_app.py).
try:
    from app.ui.inteligencia_mercado import render_inteligencia_mercado
except Exception as e:
    st.error(
        "No se pudo importar la pantalla de Inteligencia de Mercado.\n\n"
        f"Detalle tecnico: `{type(e).__name__}: {e}`\n\n"
        "Esta pagina depende de `app/ui/inteligencia_mercado.py` y de "
        "`app/db/turso_http_client.py`. Revisar logs de Streamlit Cloud."
    )
    st.stop()

render_inteligencia_mercado()
