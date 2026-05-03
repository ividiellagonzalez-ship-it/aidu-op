"""
AIDU Op · Dashboard MERCADO
============================
Primera etapa del embudo. Vista ejecutiva del mercado público chileno.

6 secciones:
1. Filtros globales (Período + Región + Categoría)
2. KPIs macro con tendencia
3. Evolución temporal 12 meses
4. Distribución por tipo licitación
5. Top 15 organismos compradores
6. Tabla exploratoria descargable

Defensivo: tolera BD vacía o sin tablas v18.
"""
from __future__ import annotations
import streamlit as st
from datetime import datetime, timedelta, date
from app.db.migrator import get_connection


def _safe_count(conn, sql: str, params: tuple = ()) -> int:
    """Ejecuta SELECT COUNT(*) defensivo. Retorna 0 si hay cualquier error."""
    try:
        r = conn.execute(sql, params).fetchone()
        return int(r[0]) if r and r[0] is not None else 0
    except Exception:
        return 0


def _safe_sum(conn, sql: str, params: tuple = ()) -> int:
    """Ejecuta SELECT SUM(...) defensivo."""
    try:
        r = conn.execute(sql, params).fetchone()
        return int(r[0]) if r and r[0] is not None else 0
    except Exception:
        return 0


def _formato_clp(monto: int) -> str:
    """Formatea monto CLP con escala automática."""
    if monto >= 1_000_000_000:
        return f"${monto / 1_000_000_000:.2f} B"
    elif monto >= 1_000_000:
        return f"${monto / 1_000_000:.1f} M"
    elif monto >= 1_000:
        return f"${monto / 1_000:.0f} K"
    return f"${monto:,}"


def _delta_pct(actual: float, anterior: float) -> str:
    """Calcula y formatea delta % entre dos valores."""
    if anterior == 0 or anterior is None:
        return ""
    delta = (actual - anterior) / anterior * 100
    if abs(delta) < 0.5:
        return "→"
    flecha = "↑" if delta > 0 else "↓"
    return f"{flecha} {abs(delta):.1f}%"


def render_dashboard_mercado():
    """Renderiza el dashboard Mercado completo."""
    
    # ========================================
    # HERO ESTILO BLOOMBERG
    # ========================================
    hora = datetime.now().strftime("%H:%M")
    fecha_hoy = datetime.now().strftime("%d %b %Y")
    
    st.markdown(f"""
    <div style="background:linear-gradient(135deg, #0F172A 0%, #1E3A8A 100%); padding:20px 24px; border-radius:12px; margin-bottom:20px; color:white;">
        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
            <div>
                <div style="font-size:11px; text-transform:uppercase; letter-spacing:1.5px; color:#94A3B8;">AIDU OP · MARKET INTELLIGENCE · ETAPA 1 DEL EMBUDO</div>
                <div style="font-size:24px; font-weight:800; margin-top:4px;">📊 MERCADO</div>
                <div style="font-size:12px; color:#CBD5E1; margin-top:2px;">Compras Públicas Chile · Cockpit ejecutivo</div>
            </div>
            <div style="text-align:right;">
                <div style="font-size:11px; color:#94A3B8;">{fecha_hoy}</div>
                <div style="font-size:20px; font-weight:700; margin-top:2px; font-family:'JetBrains Mono', monospace;">{hora}</div>
                <div style="font-size:11px; color:#10B981; margin-top:2px;">● MERCADO ABIERTO</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ========================================
    # SECCIÓN 1: FILTROS GLOBALES (Período + Región + Categoría)
    # ========================================
    st.markdown("##### 🎛️ Filtros del cockpit")
    
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        periodo = st.selectbox(
            "📅 Período",
            options=["Últimos 30 días", "Últimos 90 días", "Últimos 6 meses",
                     "Últimos 12 meses", "Últimos 24 meses", "Todo el histórico"],
            index=3,
            key="dash_periodo"
        )
        periodo_dias = {
            "Últimos 30 días": 30,
            "Últimos 90 días": 90,
            "Últimos 6 meses": 180,
            "Últimos 12 meses": 365,
            "Últimos 24 meses": 730,
            "Todo el histórico": 99999,
        }[periodo]
    
    with col_f2:
        from app.core.catalogo_aidu import REGIONES_INTERES_AIDU
        regs_disponibles = ["Todas"] + list(REGIONES_INTERES_AIDU.keys())
        reg_seleccionada = st.selectbox(
            "📍 Región",
            options=regs_disponibles,
            format_func=lambda r: "Todas las regiones" if r == "Todas" else f"{r} — {REGIONES_INTERES_AIDU[r]}",
            key="dash_region"
        )
    
    with col_f3:
        from app.core.catalogo_aidu import CATALOGO_AIDU, label_servicio
        cats_disponibles = ["Todas"] + list(CATALOGO_AIDU.keys())
        cat_seleccionada = st.selectbox(
            "🎯 Categoría AIDU",
            options=cats_disponibles,
            format_func=lambda c: "Todas las categorías" if c == "Todas" else label_servicio(c, "completo"),
            key="dash_categoria"
        )
    
    # Construir cláusula WHERE común para reutilizar
    hoy = datetime.now().date()
    fecha_desde = (hoy - timedelta(days=periodo_dias)).isoformat()
    
    where_clauses = ["fecha_publicacion >= ?"]
    where_params = [fecha_desde]
    
    if reg_seleccionada != "Todas":
        nombre_region = REGIONES_INTERES_AIDU.get(reg_seleccionada, "")
        if nombre_region:
            where_clauses.append("region LIKE ?")
            where_params.append(f"%{nombre_region}%")
    
    where_sql = " AND ".join(where_clauses)
    
    st.divider()
    
    # ========================================
    # CARGA DE DATOS BASE
    # ========================================
    conn = get_connection()
    try:
        # Determinar JOIN con categorización si se filtra por categoría
        if cat_seleccionada != "Todas":
            join_cat = "INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo"
            where_clauses.append("c.cod_servicio_aidu = ?")
            where_params.append(cat_seleccionada)
            where_sql = " AND ".join(where_clauses)
        else:
            join_cat = ""
        
        # Reemplazo "fecha_publicacion" → "l.fecha_publicacion" en where_sql
        where_sql_alias = where_sql.replace("fecha_publicacion >=", "l.fecha_publicacion >=").replace("region LIKE", "l.region LIKE")
        
        # KPIs
        # Mercado total adjudicado en período
        try:
            row = conn.execute(f"""
                SELECT COUNT(*) AS n, COALESCE(SUM(monto_adjudicado), 0) AS monto
                FROM mp_licitaciones_adj l
                {join_cat}
                WHERE {where_sql_alias}
            """, where_params).fetchone()
            n_adj = int(row["n"] or 0)
            monto_adj = int(row["monto"] or 0)
        except Exception:
            n_adj = 0
            monto_adj = 0
        
        # Vigentes ahora (no depende del filtro de período)
        try:
            where_vig = []
            params_vig = []
            if reg_seleccionada != "Todas":
                where_vig.append("l.region LIKE ?")
                params_vig.append(f"%{nombre_region}%")
            join_cat_vig = ""
            if cat_seleccionada != "Todas":
                join_cat_vig = "INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo"
                where_vig.append("c.cod_servicio_aidu = ?")
                params_vig.append(cat_seleccionada)
            where_vig_sql = " WHERE " + " AND ".join(where_vig) if where_vig else ""
            row_vig = conn.execute(f"""
                SELECT COUNT(*) AS n FROM mp_licitaciones_vigentes l
                {join_cat_vig}
                {where_vig_sql}
            """, params_vig).fetchone()
            n_vigentes = int(row_vig["n"] or 0)
        except Exception:
            n_vigentes = 0
        
        # Ticket promedio
        ticket_prom = int(monto_adj / n_adj) if n_adj > 0 else 0
        
        # KPI Perímetro AIDU: % del mercado en categorías AIDU
        try:
            row_aidu = conn.execute(f"""
                SELECT COALESCE(SUM(monto_adjudicado), 0) AS monto
                FROM mp_licitaciones_adj l
                INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
                WHERE {where_sql_alias if cat_seleccionada == 'Todas' else where_sql_alias}
            """, where_params).fetchone()
            monto_aidu = int(row_aidu["monto"] or 0)
            pct_aidu = (monto_aidu / monto_adj * 100) if monto_adj > 0 else 0
        except Exception:
            monto_aidu = 0
            pct_aidu = 0
        
        # Período anterior (para tendencia)
        fecha_desde_prev = (hoy - timedelta(days=periodo_dias * 2)).isoformat()
        fecha_hasta_prev = fecha_desde
        try:
            params_prev = [fecha_desde_prev, fecha_hasta_prev] + where_params[1:]
            row_prev = conn.execute(f"""
                SELECT COUNT(*) AS n, COALESCE(SUM(monto_adjudicado), 0) AS monto
                FROM mp_licitaciones_adj l
                {join_cat}
                WHERE l.fecha_publicacion >= ? AND l.fecha_publicacion < ?
                  {' AND ' + ' AND '.join(where_clauses[1:]) if len(where_clauses) > 1 else ''}
            """, params_prev).fetchone()
            n_adj_prev = int(row_prev["n"] or 0)
            monto_adj_prev = int(row_prev["monto"] or 0)
        except Exception:
            n_adj_prev = 0
            monto_adj_prev = 0
        
        # ========================================
        # SECCIÓN 2: KPIs MACRO
        # ========================================
        st.markdown("##### 📊 KPIs del mercado · Período seleccionado")
        
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        
        with col_k1:
            delta_monto = _delta_pct(monto_adj, monto_adj_prev)
            st.metric(
                "Mercado total adjudicado",
                _formato_clp(monto_adj),
                delta=f"{delta_monto} vs período anterior" if delta_monto else None,
                help=f"Total CLP adjudicado en {n_adj:,} licitaciones del período"
            )
        
        with col_k2:
            st.metric(
                "Perímetro AIDU",
                f"{pct_aidu:.1f}%",
                delta=f"{_formato_clp(monto_aidu)} en categorías CE/GP",
                help="% del mercado total que cae en categorías AIDU (CE-XX, GP-XX)"
            )
        
        with col_k3:
            st.metric(
                "Vigentes ahora",
                f"{n_vigentes:,}",
                delta="licitaciones abiertas",
                help="Licitaciones publicadas y abiertas a postular"
            )
        
        with col_k4:
            st.metric(
                "Ticket promedio",
                _formato_clp(ticket_prom),
                delta=f"{n_adj:,} adjudicaciones",
                help="Monto promedio por licitación adjudicada"
            )
        
        st.divider()
        
        # ========================================
        # SECCIÓN 3: EVOLUCIÓN TEMPORAL
        # ========================================
        st.markdown("##### 📈 Evolución del mercado · Últimos 12 meses")
        
        try:
            mes_desde = (hoy - timedelta(days=365)).isoformat()
            params_evo = [mes_desde] + where_params[1:]
            
            rows_mes = conn.execute(f"""
                SELECT 
                    strftime('%Y-%m', l.fecha_publicacion) AS mes,
                    COUNT(*) AS n,
                    COALESCE(SUM(monto_adjudicado), 0) AS monto
                FROM mp_licitaciones_adj l
                {join_cat}
                WHERE l.fecha_publicacion >= ?
                  {' AND ' + ' AND '.join(where_clauses[1:]) if len(where_clauses) > 1 else ''}
                GROUP BY mes
                ORDER BY mes ASC
            """, params_evo).fetchall()
            
            if rows_mes:
                try:
                    import plotly.graph_objects as go
                    
                    meses = [r["mes"] for r in rows_mes]
                    montos = [r["monto"] / 1_000_000 for r in rows_mes]  # En MM
                    cantidades = [r["n"] for r in rows_mes]
                    
                    fig = go.Figure()
                    fig.add_trace(go.Bar(
                        x=meses, y=montos, name="Monto adjudicado (MM CLP)",
                        marker_color="#1E3A8A", yaxis="y"
                    ))
                    fig.add_trace(go.Scatter(
                        x=meses, y=cantidades, name="N° licitaciones",
                        mode="lines+markers", line=dict(color="#F59E0B", width=2),
                        yaxis="y2"
                    ))
                    fig.update_layout(
                        height=320,
                        margin=dict(l=10, r=10, t=10, b=10),
                        yaxis=dict(title="MM CLP", side="left"),
                        yaxis2=dict(title="N° licitaciones", side="right", overlaying="y"),
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                        plot_bgcolor="white",
                    )
                    st.plotly_chart(fig, use_container_width=True)
                except ImportError:
                    # Fallback sin plotly: tabla simple
                    import pandas as pd
                    df_mes = pd.DataFrame([
                        {"Mes": r["mes"], "N": r["n"], "Monto MM": round(r["monto"]/1_000_000, 1)}
                        for r in rows_mes
                    ])
                    st.bar_chart(df_mes.set_index("Mes")["Monto MM"])
            else:
                st.info("📭 Sin datos en el período. Ejecuta una descarga histórica.")
        except Exception as e:
            st.caption(f"Evolución no disponible: {e}")
        
        st.divider()
        
        # ========================================
        # SECCIÓN 4: DISTRIBUCIÓN POR TIPO Y REGIÓN
        # ========================================
        col_dist1, col_dist2 = st.columns(2)
        
        with col_dist1:
            st.markdown("##### 🥧 Por tipo de licitación")
            try:
                rows_tipo = conn.execute(f"""
                    SELECT 
                        COALESCE(NULLIF(tipo, ''), 'Sin clasificar') AS tipo,
                        COUNT(*) AS n,
                        COALESCE(SUM(monto_adjudicado), 0) AS monto
                    FROM mp_licitaciones_adj l
                    {join_cat}
                    WHERE {where_sql_alias}
                    GROUP BY tipo
                    ORDER BY n DESC
                    LIMIT 10
                """, where_params).fetchall()
                
                if rows_tipo:
                    tabla_tipo = []
                    total_n = sum(r["n"] for r in rows_tipo)
                    for r in rows_tipo:
                        pct = (r["n"] / total_n * 100) if total_n else 0
                        tabla_tipo.append({
                            "Tipo": r["tipo"],
                            "N°": r["n"],
                            "%": f"{pct:.1f}%",
                            "Monto": _formato_clp(int(r["monto"])),
                        })
                    st.dataframe(tabla_tipo, use_container_width=True, hide_index=True, height=300)
                else:
                    st.caption("Sin datos de tipo.")
            except Exception as e:
                st.caption(f"No disponible: {e}")
        
        with col_dist2:
            st.markdown("##### 🗺️ Por región")
            try:
                rows_reg = conn.execute(f"""
                    SELECT 
                        COALESCE(NULLIF(region, ''), 'Sin región') AS region,
                        COUNT(*) AS n,
                        COALESCE(SUM(monto_adjudicado), 0) AS monto
                    FROM mp_licitaciones_adj l
                    {join_cat}
                    WHERE {where_sql_alias}
                    GROUP BY region
                    ORDER BY n DESC
                    LIMIT 10
                """, where_params).fetchall()
                
                if rows_reg:
                    tabla_reg = []
                    for r in rows_reg:
                        tabla_reg.append({
                            "Región": r["region"][:35],
                            "N°": r["n"],
                            "Monto": _formato_clp(int(r["monto"])),
                        })
                    st.dataframe(tabla_reg, use_container_width=True, hide_index=True, height=300)
                else:
                    st.caption("Sin datos de región.")
            except Exception as e:
                st.caption(f"No disponible: {e}")
        
        st.divider()
        
        # ========================================
        # SECCIÓN 5: TOP 15 ORGANISMOS
        # ========================================
        st.markdown("##### 🏛️ Top 15 organismos compradores")
        st.caption("Click en un organismo para ver sus licitaciones (drill-down disponible en próxima iteración).")
        
        try:
            rows_org = conn.execute(f"""
                SELECT 
                    organismo,
                    region,
                    COUNT(*) AS n_licitaciones,
                    COALESCE(SUM(monto_adjudicado), 0) AS monto_total,
                    COALESCE(AVG(monto_adjudicado), 0) AS ticket_promedio
                FROM mp_licitaciones_adj l
                {join_cat}
                WHERE {where_sql_alias}
                  AND organismo IS NOT NULL AND organismo != ''
                GROUP BY organismo, region
                ORDER BY monto_total DESC
                LIMIT 15
            """, where_params).fetchall()
            
            if rows_org:
                tabla_org = []
                for i, r in enumerate(rows_org, 1):
                    tabla_org.append({
                        "#": i,
                        "Organismo": (r["organismo"] or "")[:55],
                        "Región": (r["region"] or "—")[:25],
                        "Licitaciones": f"{r['n_licitaciones']:,}",
                        "Monto total": _formato_clp(int(r["monto_total"])),
                        "Ticket prom.": _formato_clp(int(r["ticket_promedio"])),
                    })
                st.dataframe(tabla_org, use_container_width=True, hide_index=True)
            else:
                st.info("📭 Sin organismos en el período.")
        except Exception as e:
            st.caption(f"Top organismos no disponible: {e}")
        
        st.divider()
        
        # ========================================
        # SECCIÓN 6: TABLA EXPLORATORIA
        # ========================================
        st.markdown("##### 📋 Tabla exploratoria · Todas las licitaciones del filtro")
        st.caption("Ordena, filtra y descarga como Excel. La tabla aplica los filtros globales de arriba.")
        
        try:
            rows_explo = conn.execute(f"""
                SELECT 
                    l.codigo_externo,
                    l.nombre,
                    l.organismo,
                    l.region,
                    l.tipo,
                    l.fecha_publicacion,
                    l.fecha_adjudicacion,
                    l.monto_referencial,
                    l.monto_adjudicado
                FROM mp_licitaciones_adj l
                {join_cat}
                WHERE {where_sql_alias}
                ORDER BY l.fecha_publicacion DESC
                LIMIT 500
            """, where_params).fetchall()
            
            if rows_explo:
                import pandas as pd
                df = pd.DataFrame([dict(r) for r in rows_explo])
                df["monto_referencial"] = df["monto_referencial"].fillna(0).astype(int)
                df["monto_adjudicado"] = df["monto_adjudicado"].fillna(0).astype(int)
                df.columns = ["Código", "Nombre", "Organismo", "Región", "Tipo", 
                              "Publicación", "Adjudicación", "Monto ref.", "Monto adj."]
                
                st.dataframe(df, use_container_width=True, hide_index=True, height=400)
                
                col_exp1, col_exp2 = st.columns([1, 4])
                with col_exp1:
                    csv = df.to_csv(index=False).encode("utf-8-sig")
                    st.download_button(
                        "📥 Descargar Excel",
                        data=csv,
                        file_name=f"mercado_aidu_{hoy.isoformat()}.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
                with col_exp2:
                    st.caption(f"Mostrando {len(df)} de las primeras 500 filas. Filtra arriba para refinar.")
            else:
                st.info("📭 Sin licitaciones en el filtro actual.")
        except Exception as e:
            st.caption(f"Tabla exploratoria no disponible: {e}")
        
        # ========================================
        # GESTIÓN DE BASE DE DATOS (compactado al final)
        # ========================================
        st.divider()
        with st.expander("💾 Gestión de base de datos · Descarga histórica + sincronización", expanded=False):
            try:
                from app.core.descarga_diaria import ejecutar_descarga
                from app.core.descarga_historica import descargar_rango
                import os as _os
                
                # Stats actuales
                bd_n_vigentes = _safe_count(conn, "SELECT COUNT(*) FROM mp_licitaciones_vigentes")
                bd_n_adj = _safe_count(conn, "SELECT COUNT(*) FROM mp_licitaciones_adj")
                bd_n_cat = _safe_count(conn, "SELECT COUNT(*) FROM mp_categorizacion_aidu")
                
                col_bd1, col_bd2, col_bd3, col_bd4 = st.columns(4)
                col_bd1.metric("Vigentes en BD", f"{bd_n_vigentes:,}")
                col_bd2.metric("Histórico en BD", f"{bd_n_adj:,}")
                col_bd3.metric("Categorizadas AIDU", f"{bd_n_cat:,}")
                col_bd4.metric("Cobertura", f"{bd_n_cat * 100 / bd_n_adj:.0f}%" if bd_n_adj else "0%")
                
                st.markdown("---")
                
                # Sincronización rápida
                st.markdown("**🔄 Sincronización rápida (últimos 2 días)**")
                col_s1, col_s2 = st.columns([3, 1])
                with col_s1:
                    st.caption("Trae las licitaciones de los últimos 2 días. ~20 segundos.")
                with col_s2:
                    if st.button("🔄 Sincronizar", use_container_width=True, key="sync_btn"):
                        with st.spinner("Sincronizando..."):
                            try:
                                res = ejecutar_descarga(dias_atras=2)
                                st.success(
                                    f"✅ Vigentes: +{res.get('vigentes', {}).get('nuevas', 0)} nuevas, "
                                    f"+{res.get('vigentes', {}).get('actualizadas', 0)} actualizadas"
                                )
                                with st.expander("Detalle"):
                                    st.json(res)
                            except Exception as e:
                                st.error(f"Error: {e}")
                
                st.markdown("---")
                
                # Descarga histórica
                st.markdown("**⏬ Descarga histórica retroactiva**")
                st.caption("Construye la BD histórica para análisis de mercado.")
                
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    fecha_desde_dl = st.date_input("Desde", value=hoy - timedelta(days=30), key="dl_desde")
                with col_d2:
                    fecha_hasta_dl = st.date_input("Hasta", value=hoy, key="dl_hasta")
                
                col_chk = st.columns(3)
                inc_vig = col_chk[0].checkbox("Vigentes (publicadas)", value=True, key="dl_inc_vig")
                inc_adj = col_chk[1].checkbox("Adjudicadas", value=True, key="dl_inc_adj")
                saltar = col_chk[2].checkbox("Saltar días ya descargados", value=True, key="dl_skip")
                
                if st.button("🚀 Iniciar descarga histórica", type="primary", use_container_width=True, key="dl_btn"):
                    progress_bar = st.progress(0)
                    status = st.empty()
                    
                    def cb(actual, total, fecha, n_vig, n_adj_dia, st_str):
                        progress_bar.progress(actual / total if total else 0)
                        status.text(f"📅 {fecha} · {actual}/{total} días · "
                                    f"+{n_vig} vig / +{n_adj_dia} adj · {st_str}")
                    
                    try:
                        res = descargar_rango(
                            fecha_inicio=fecha_desde_dl,
                            fecha_fin=fecha_hasta_dl,
                            incluir_vigentes=inc_vig,
                            incluir_adjudicadas=inc_adj,
                            saltar_descargados=saltar,
                            progress_callback=cb,
                        )
                        
                        progress_bar.progress(1.0)
                        
                        # Reporte ejecutivo
                        st.success(f"""🎉 **Descarga completa**
                                   
- 📅 Días procesados: {res.get('dias_procesados', 0)}
- ⏭️  Saltados: {res.get('dias_saltados', 0)}
- ✨ Nuevas vigentes: {res.get('vigentes_total', 0)}
- ✨ Nuevas adjudicadas: {res.get('adjudicadas_total', 0)}
- ⚠️  Fallidas: {res.get('fallidas', 0)}

Recarga la página (R) para ver los nuevos datos en KPIs.""")
                    except Exception as e:
                        st.error(f"Error en descarga: {e}")
            except Exception as e:
                st.caption(f"Gestión BD no disponible: {e}")
    finally:
        conn.close()
