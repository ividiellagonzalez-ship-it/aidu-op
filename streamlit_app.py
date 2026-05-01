"""
AIDU Op - Entrypoint para Streamlit Community Cloud
====================================================
Streamlit Cloud busca este archivo en la raíz del repo.
Solo importa el módulo principal de UI.
"""
import sys
from pathlib import Path

# Agregar el directorio actual al path para que app/ sea importable
sys.path.insert(0, str(Path(__file__).parent))

# Ejecutar la app (el código del UI se ejecuta al importar)
exec(open(Path(__file__).parent / "app" / "ui" / "streamlit_app.py").read())
