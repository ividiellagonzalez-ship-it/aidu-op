# 🚀 Deploy AIDU Op a la web — Guía paso a paso (30 min)

## 📋 Lo que vas a tener al final

- AIDU Op corriendo en una URL pública (ejemplo: `aidu-op-ignacio.streamlit.app`)
- Acceso desde cualquier dispositivo (PC, laptop, celular)
- **Cero instalación local** — nunca más volver a Python en tu Windows
- Cada actualización del código se despliega sola

---

## 🔒 PASO 0 — Seguridad primero (5 min)

### ⚠️ Antes de TODO

1. **Revoca tu API key de Anthropic** comprometida:
   - Ve a https://console.anthropic.com/settings/keys
   - Encuentra la key actual → click "Revoke"
   - Click "Create Key" → guárdala en un sitio seguro (NO me la mandes por chat)

2. **Considera regenerar tu ticket Mercado Público:**
   - Ve a https://www.chileproveedores.cl/
   - Busca tu opción para regenerar token API

---

## 👤 PASO 1 — Crear cuenta GitHub (5 min)

Si ya tienes, salta a Paso 2.

1. Ve a https://github.com/signup
2. Registra cuenta con tu email (puedes usar uno dedicado tipo `aiduop@gmail.com`)
3. Verifica tu email
4. **NO necesitas plan pagado.** El gratuito es suficiente.

---

## 📦 PASO 2 — Subir el código a GitHub (10 min)

### Opción A — Por web (más simple, recomendada para no-devs)

1. **Loguéate en GitHub.**

2. Click en el botón verde **"New"** (o ve a https://github.com/new)

3. Configura:
   - **Repository name:** `aidu-op`
   - **Description:** `Sistema Comercial B2G para Mercado Público Chile`
   - **Privacy:** Privado (selecciona "Private")
   - **NO** marques "Add a README file" (ya viene en mi paquete)
   - Click **"Create repository"**

4. **GitHub te muestra una pantalla con instrucciones.** Ignora la mayoría — busca abajo la parte que dice **"uploading an existing file"** (subir archivo existente).

5. Click en **"uploading an existing file"** (es un link).

6. **Descomprime `aidu_op_cloud.zip`** que te di.

7. **Selecciona TODOS los archivos** dentro de la carpeta descomprimida (Ctrl+A) y arrástralos al área de upload de GitHub.

8. Espera que suban (1-2 min).

9. Abajo en "Commit changes":
   - **Commit message:** `Initial commit`
   - Click **"Commit changes"**

10. ✅ Listo. Tu código está en GitHub en `https://github.com/TU_USUARIO/aidu-op`

---

## ☁️ PASO 3 — Desplegar en Streamlit Cloud (5 min)

1. Ve a https://share.streamlit.io/

2. Click **"Continue with GitHub"** (te pedirá login a GitHub si no lo estás).

3. **Streamlit pedirá permisos para acceder a tu GitHub.** Click "Authorize streamlit".

4. Click el botón **"New app"** o **"Create app"** (arriba a la derecha).

5. Configura:
   - **Repository:** `TU_USUARIO/aidu-op` (selecciona el que acabas de crear)
   - **Branch:** `main`
   - **Main file path:** `streamlit_app.py` *(importante, exactamente así)*
   - **App URL (opcional):** puedes personalizarla a `aidu-op-ignacio` o lo que prefieras

6. **Click "Advanced settings..."**:
   - **Python version:** `3.11`
   - **Secrets:** pega exactamente esto, reemplazando con TUS valores reales:
   
   ```
   MP_TICKET = "TU_TICKET_REAL_DE_MERCADO_PUBLICO"
   ANTHROPIC_API_KEY = "sk-ant-TU_NUEVA_API_KEY"
   ```
   
   ⚠️ **IMPORTANTE:** las comillas son necesarias.

7. Click **"Deploy"**.

8. **Espera ~3 minutos** (verás logs en pantalla mientras instala dependencias).

9. ✅ Cuando termine, tendrás tu **URL pública**: `https://aidu-op-ignacio.streamlit.app/`

---

## 🎯 PASO 4 — Probar la app desplegada (5 min)

1. Abre tu URL en el navegador.

2. Verifica que aparece el badge verde **"⚡ MVP CON IA + WORD/EXCEL"**.

3. Ve a la pestaña **Sistema** → **"Descargar datos REALES"** → cambia a **7 días** → Click **"Descargar ahora"**.

4. Espera ~10 minutos (verás indicador de progreso).

5. Cuando termine, revisa pestaña **Buscar** — debería tener cientos de licitaciones reales.

6. Ve a **Cartera** → click "Ver detalle" en cualquier proyecto → tab **"Acciones"**:
   - Click **"📄 Generar Word + Excel"** → debería ofrecerte descargar archivos
   - Click **"🧠 Analizar con IA"** → Claude analiza el proyecto

---

## 🔄 Cómo funcionan las actualizaciones desde ahora

Cuando yo (Claude) tengo una nueva versión del código:

1. **Yo te paso un nuevo ZIP** o te indico exactamente qué cambió
2. **Tú subes los archivos cambiados a GitHub** (web UI, "Add file" → "Upload files")
3. **Streamlit Cloud detecta el cambio y redespliega solo** (~1 min)
4. **Refrescas la URL** y tienes la versión nueva

Sin instalación. Sin Python. Sin ZIPs virtuales. Sin dolor.

---

## 🆘 Si algo falla en el deploy

### "Build failed" en Streamlit Cloud

En la página de tu app en Streamlit Cloud:
1. Click "Manage app" (abajo a la derecha)
2. Verás los logs en vivo
3. **Cópiame el error y te ayudo en el siguiente mensaje**

### "MP_TICKET no configurado"

Vuelve a Streamlit Cloud → tu app → "⋮" → "Settings" → "Secrets" → verifica que el formato sea:

```
MP_TICKET = "valor-con-comillas"
ANTHROPIC_API_KEY = "valor-con-comillas"
```

### App carga pero muestra error en pantalla

Mándame screenshot del error y resuelvo.

---

## 💡 Ventajas de este modelo vs Windows local

| Aspecto | Antes (Windows local) | Ahora (cloud) |
|---|---|---|
| Instalación | 5 iteraciones fallidas | Cero |
| Python 3.14 issues | Sí | No (uso 3.11) |
| ZIPs virtuales | Sí | N/A |
| Actualizar código | 30-60 min | 2 min |
| Acceso desde móvil | No | Sí |
| Backups | Manual | Automático en GitHub |
| Compartir con tu socia | No | Solo le mandas URL |
| Costo | $0 | $0 |
