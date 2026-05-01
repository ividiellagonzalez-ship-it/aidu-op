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

from app.db.migrator import get_connection
from app.core.backfill import estado_actual
from app.core.inteligencia_precios import (
    calcular_escenarios_precio,
    obtener_estadisticas_categoria,
    licitaciones_similares,
)
from config.settings import get_version, AIDU_HOME


# ============================================================
# CONFIG STREAMLIT
# ============================================================
st.set_page_config(
    page_title="AIDU Op",
    page_icon="●",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Identidad visual AIDU
st.markdown("""
<style>
.aidu-logo { display: flex; align-items: center; gap: 10px; margin-bottom: 4px;}
.aidu-logo .dot { width: 10px; height: 10px; background: #1E40AF; border-radius: 50%; box-shadow: 0 0 12px #3B82F6; }
.aidu-logo .aidu-text { font-size: 28px; font-weight: 800; color: #1E40AF; letter-spacing: -1px; }
.aidu-logo .op-text { font-size: 16px; color: #475569; padding: 2px 8px; background: #F1F5F9; border-radius: 6px; }
div[data-testid="stMetricValue"] { font-weight: 700; color: #1E40AF; }

/* Estados */
.estado-PROSPECTO { background: #F1F5F9; color: #475569; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; }
.estado-ESTUDIO { background: #CFFAFE; color: #0E7490; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; }
.estado-EN_PREPARACION { background: #DBEAFE; color: #1E40AF; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; }
.estado-LISTO_OFERTAR { background: #FED7AA; color: #9A3412; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; }
.estado-OFERTADA { background: #E9D5FF; color: #6B21A8; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; }
.estado-ADJUDICADA { background: #BBF7D0; color: #14532D; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 700; }

/* Macro Flow */
.macro-flow { background: #F8FAFC; padding: 12px 16px; border-radius: 10px; margin-bottom: 16px; display: flex; gap: 12px; align-items: center; border: 1px solid #E2E8F0; }
.macro-step { flex: 1; padding: 8px 12px; background: white; border-radius: 8px; text-align: center; font-size: 12px; color: #64748B; border: 1px solid #E2E8F0; }
.macro-arrow { color: #94A3B8; font-weight: 700; }

/* Escenarios */
.escenario-card { padding: 16px; border-radius: 10px; text-align: center; margin: 4px; }
.escenario-agresivo { background: linear-gradient(180deg, #FEE2E2 0%, white 50%); border-top: 3px solid #DC2626; }
.escenario-competitivo { background: linear-gradient(180deg, #FED7AA 0%, white 50%); border-top: 3px solid #D97706; }
.escenario-premium { background: linear-gradient(180deg, #BBF7D0 0%, white 50%); border-top: 3px solid #15803D; }
.esc-label { font-size: 10px; font-weight: 700; letter-spacing: 0.8px; text-transform: uppercase; color: #64748B; }
.esc-precio { font-size: 28px; font-weight: 800; margin: 8px 0; }
.esc-margen { font-size: 12px; color: #475569; }
.esc-prob { font-size: 16px; font-weight: 700; margin-top: 8px; }
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

    # Tabs internas del proyecto
    tab_info, tab_precios, tab_comparables, tab_acciones = st.tabs([
        "📋 Información",
        "💰 Inteligencia de Precios",
        "📚 Comparables del Mercado",
        "🎯 Acciones",
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
        st.markdown(f"##### 📚 Top licitaciones similares en categoría {p['cod_servicio_aidu']}")

        comparables = licitaciones_similares(p["cod_servicio_aidu"], limit=15)

        if not comparables:
            st.info("Sin comparables en el histórico actual. Ejecuta el backfill 24m para enriquecer datos.")
        else:
            st.caption(f"Mostrando {len(comparables)} licitaciones más similares ordenadas por confianza de match")

            for c in comparables:
                with st.container(border=True):
                    col1, col2, col3, col4 = st.columns([4, 2, 2, 1])

                    col1.markdown(f"""
                    **{c['nombre']}**
                    <br><span style='color:#64748B; font-size:12px;'>
                    🏛️ {c['organismo'] or '-'} · 📍 {c['region'] or '-'}
                    </span>
                    <br><span style='color:#94A3B8; font-family:monospace; font-size:11px;'>{c['codigo']}</span>
                    """, unsafe_allow_html=True)

                    col2.metric("Referencial", formato_clp(c["monto_referencial"]))
                    col3.metric(
                        "Adjudicado",
                        formato_clp(c["monto_adjudicado"]),
                        f"{c['descuento_pct']:.1f}%" if c["descuento_pct"] else None
                    )
                    col4.metric("Match", f"{c['similarity']:.0f}%")

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


# ============================================================
# HELPERS DE BD
# ============================================================
def _cambiar_estado(proyecto_id: int, nuevo_estado: str, paquete: bool = False):
    conn = get_connection()
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
# HEADER
# ============================================================
col_logo, col_status = st.columns([3, 1])

with col_logo:
    st.markdown(f"""
    <div class="aidu-logo">
        <span class="dot"></span>
        <span class="aidu-text">AIDU</span>
        <span class="op-text">Op</span>
        <span style="color: #94A3B8; font-size: 13px; margin-left: 12px;">Sistema de Gestión Comercial · v{get_version()}</span>
        <span style="background: #15803D; color: white; font-size: 11px; padding: 3px 10px; border-radius: 12px; margin-left: 8px; font-weight: 700;">⚡ MVP CON IA + WORD/EXCEL</span>
    </div>
    """, unsafe_allow_html=True)

with col_status:
    estado = estado_actual()
    if estado["licitaciones_historicas"] > 0:
        st.markdown(
            f"<div style='text-align:right; color:#0E7490; font-size:12px; padding-top:8px;'>"
            f"📊 {estado['licitaciones_historicas']:,} licitaciones · ✅ Sistema OK</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            f"<div style='text-align:right; color:#9A3412; font-size:12px; padding-top:8px;'>"
            f"⚠️ BD vacía · Carga datos demo</div>",
            unsafe_allow_html=True
        )

st.divider()


# ============================================================
# TABS PRINCIPALES
# ============================================================
tab_cartera, tab_buscar, tab_intel, tab_sistema = st.tabs([
    "📂 Cartera", "🔍 Buscar", "📊 Inteligencia", "⚙️ Sistema"
])


# ====================
# TAB 1: CARTERA
# ====================
with tab_cartera:
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
        st.info("📂 Cartera vacía. Carga datos demo desde **⚙️ Sistema**.")
    else:
        for p in proyectos:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])

                col1.markdown(f"""
                **{p['nombre']}**
                <span class="estado-{p['estado']}">{p['estado']}</span>
                <span style='color:#64748B; font-size:12px; margin-left:8px;'>
                    🏛️ {p['organismo']} · 📍 {p['region']} · {p['cod_servicio_aidu']}
                </span>
                <br>
                <span style='color:#94A3B8; font-family:monospace; font-size:11px;'>{p['codigo_externo']}</span>
                """, unsafe_allow_html=True)

                col2.metric("Monto ref.", formato_clp(p["monto_referencial"]))

                dias = calcular_dias_cierre(p["fecha_cierre"])
                if dias is not None:
                    col3.metric("Días cierre", f"{emoji_dias(dias)} {dias}")

                # Acciones
                col_a, col_b, col_c = st.columns(3)
                if p["estado"] == "PROSPECTO":
                    if col_a.button("🔬 Estudiar", key=f"est_{p['id']}", use_container_width=True):
                        _cambiar_estado(p["id"], "ESTUDIO")
                        st.rerun()
                elif p["estado"] == "EN_PREPARACION":
                    if col_a.button("🚀 Ofertar", key=f"of_{p['id']}", use_container_width=True):
                        _cambiar_estado(p["id"], "LISTO_OFERTAR", paquete=True)
                        st.rerun()
                elif p["estado"] == "LISTO_OFERTAR":
                    col_a.success("📦 Paquete listo")

                # ✅ Botón Ver detalle ahora SÍ funciona
                if col_c.button("👁️ Ver detalle", key=f"det_{p['id']}", use_container_width=True):
                    st.session_state.view_proyecto_id = p["id"]
                    st.rerun()


# ====================
# TAB 2: BUSCAR
# ====================
with tab_buscar:
    st.subheader("🔍 Búsqueda en histórico Mercado Público")

    col_q, col_btn = st.columns([3, 1])
    query = col_q.text_input(
        "Buscar",
        placeholder="ej: estructural, dashboard, procesos...",
        label_visibility="collapsed"
    )

    conn = get_connection()
    if query:
        like = f"%{query}%"
        results = conn.execute("""
            SELECT l.*, GROUP_CONCAT(c.cod_servicio_aidu, ', ') as categorias
            FROM mp_licitaciones_adj l
            LEFT JOIN mp_categorizacion_aidu c ON l.codigo_externo = c.codigo_externo
            WHERE l.nombre LIKE ? OR l.organismo LIKE ? OR l.descripcion LIKE ?
            GROUP BY l.codigo_externo
            ORDER BY l.fecha_descarga DESC LIMIT 50
        """, (like, like, like)).fetchall()
    else:
        results = conn.execute("""
            SELECT l.*, GROUP_CONCAT(c.cod_servicio_aidu, ', ') as categorias
            FROM mp_licitaciones_adj l
            LEFT JOIN mp_categorizacion_aidu c ON l.codigo_externo = c.codigo_externo
            GROUP BY l.codigo_externo
            ORDER BY l.fecha_descarga DESC LIMIT 30
        """).fetchall()
    conn.close()

    if not results:
        st.info("📭 Sin resultados.")
    else:
        st.caption(f"Mostrando {len(results)} licitaciones")
        for r in results:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 1, 1])
                col1.markdown(f"""
                **{r['nombre']}**
                <span style='color:#1E40AF; font-weight:600; font-size:11px;'>{r['categorias'] or '(sin categoría)'}</span>
                <br><span style='color:#64748B; font-size:12px;'>🏛️ {r['organismo'] or '-'} · 📍 {r['region'] or '-'}</span>
                <br><span style='color:#94A3B8; font-family:monospace; font-size:11px;'>{r['codigo_externo']}</span>
                """, unsafe_allow_html=True)

                if r["monto_referencial"]:
                    col2.metric("Referencial", formato_clp(r["monto_referencial"]))
                if r["monto_adjudicado"]:
                    desc = ((r["monto_adjudicado"] - (r["monto_referencial"] or r["monto_adjudicado"])) / (r["monto_referencial"] or 1)) * 100
                    col3.metric("Adjudicado", formato_clp(r["monto_adjudicado"]), f"{desc:.1f}%")


# ====================
# TAB 3: INTELIGENCIA
# ====================
with tab_intel:
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
with tab_sistema:
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
