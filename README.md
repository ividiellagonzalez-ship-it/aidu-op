# AIDU Op — Sistema Comercial B2G

Aplicación web para gestión de licitaciones en Mercado Público de Chile.

## 🚀 Deploy en Streamlit Community Cloud

### Requisitos
- Cuenta GitHub
- Cuenta Streamlit Cloud (gratis)
- Ticket de Mercado Público
- API Key de Anthropic (Claude)

### Despliegue

1. Sube este repositorio a GitHub
2. Ve a https://share.streamlit.io/
3. Conecta GitHub y selecciona este repo
4. **Main file path:** `streamlit_app.py`
5. **Python version:** 3.11
6. En "Advanced settings" → "Secrets", pega:

```toml
MP_TICKET = "tu-ticket-de-mercado-publico"
ANTHROPIC_API_KEY = "sk-ant-tu-api-key-de-claude"
```

7. Click en "Deploy"
8. Espera ~3 minutos al primer deploy
9. Tendrás URL del tipo `https://aidu-op-XXX.streamlit.app/`

## 📁 Estructura

```
.
├── streamlit_app.py          # Entrypoint (Streamlit lo busca aquí)
├── requirements.txt          # Dependencias
├── .streamlit/
│   ├── config.toml           # Configuración del servicio
│   └── secrets.toml.example  # Template de secretos
├── app/
│   ├── ui/streamlit_app.py   # UI principal
│   ├── core/                 # Motores: backfill, precios, IA, paquete
│   ├── api/                  # Cliente Mercado Público
│   └── db/                   # Migraciones SQLite
├── config/settings.py        # Config (autodetecta cloud vs local)
└── data_semilla/             # BD inicial con datos demo
```

## 🔑 Variables de entorno necesarias

| Variable | Descripción |
|----------|-------------|
| `MP_TICKET` | Ticket de Mercado Público (chileproveedores.cl) |
| `ANTHROPIC_API_KEY` | API key Claude (console.anthropic.com) |

## 💰 Costos esperados

- **Streamlit Cloud:** gratis (apps personales/profesionales)
- **API Mercado Público:** gratis con tu ticket
- **Claude API:** ~$0.005 USD por análisis estratégico
- **Total mensual estimado:** < $5 USD para uso personal

## 🛠️ Desarrollo local

```bash
git clone <tu-repo>
cd <tu-repo>
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Crear ~/AIDU_Op/config/secrets.env con MP_TICKET y ANTHROPIC_API_KEY

streamlit run streamlit_app.py
```

## 📝 Versión

`2.0.0-MVP` — Construido para Ignacio Vidiella González, AIDU Op SpA
