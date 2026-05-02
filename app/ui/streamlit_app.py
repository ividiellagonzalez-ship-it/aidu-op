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
    "📂 Cartera", "🎯 Oportunidades", "📊 Inteligencia", "⚙️ Sistema"
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
with tab_buscar:
    st.subheader("🎯 Oportunidades de mercado")
    st.caption("Licitaciones del histórico MP que calzan con tu perfil AIDU. Convierte las que te interesen a tu cartera.")

    from app.core.match_score import (
        listar_oportunidades, categorias_disponibles, regiones_disponibles,
        convertir_a_proyecto
    )

    # ----- Filtros laterales en columnas -----
    col_filtros, col_resultados = st.columns([1, 3])

    with col_filtros:
        st.markdown("##### 🔧 Filtros")

        # Categoría AIDU
        cats = categorias_disponibles()
        cat_options = ["Todas"] + [f"{c[0]} ({c[1]})" for c in cats]
        cat_sel_label = st.selectbox("Categoría AIDU", cat_options, key="op_cat")
        cat_sel = "Todas" if cat_sel_label == "Todas" else cat_sel_label.split(" ")[0]

        # Región
        regs = regiones_disponibles()
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
        oportunidades = listar_oportunidades(
            filtro_categoria=cat_sel,
            filtro_region=reg_sel,
            monto_min=monto_min_m * 1_000_000 if monto_min_m > 0 else None,
            monto_max=monto_max_m * 1_000_000 if monto_max_m > 0 else None,
            score_min=score_min,
            solo_no_en_cartera=solo_nuevas,
            orden=orden_map[orden_label],
            limit=100
        )

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
