"""
AIDU Op · Dashboard MERCADO v2 — Interactivo
==============================================
- Filtros multi-select (Tipo, Organismo, Estado, Categoría, Región)
- Default período "Todo el histórico" para no cargar vacío
- Tabla exploratoria nativa Streamlit (filtrable, ordenable, descargable)
- Diagnóstico visible: rango de fechas, totales BD, alertas si filtros vacían resultado
- Estado: vigentes + adjudicadas combinables en queries
"""
from __future__ import annotations
import streamlit as st
from datetime import datetime, timedelta, date
from app.db.migrator import get_connection


def _safe_count(conn, sql: str, params: tuple = ()) -> int:
    try:
        r = conn.execute(sql, params).fetchone()
        return int(r[0]) if r and r[0] is not None else 0
    except Exception:
        return 0


def _formato_clp(monto: int) -> str:
    if monto >= 1_000_000_000:
        return f"${monto / 1_000_000_000:.2f} B"
    elif monto >= 1_000_000:
        return f"${monto / 1_000_000:.1f} M"
    elif monto >= 1_000:
        return f"${monto / 1_000:.0f} K"
    return f"${monto:,}"


def render_dashboard_mercado():
    """Dashboard Mercado v2 interactivo."""
    
    hora = datetime.now().strftime("%H:%M")
    fecha_hoy = datetime.now().strftime("%d %b %Y")
    
    st.markdown(f"""
    <div style="background:linear-gradient(135deg, #0F172A 0%, #1E3A8A 100%); padding:20px 24px; border-radius:12px; margin-bottom:16px; color:white;">
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
    
    conn = get_connection()
    try:
        # ============ DIAGNÓSTICO BD ============
        n_vig_total = _safe_count(conn, "SELECT COUNT(*) FROM mp_licitaciones_vigentes")
        n_adj_total = _safe_count(conn, "SELECT COUNT(*) FROM mp_licitaciones_adj")
        
        try:
            r_fechas = conn.execute("""
                SELECT MIN(fecha_publicacion) AS min_f, MAX(fecha_publicacion) AS max_f
                FROM (
                    SELECT fecha_publicacion FROM mp_licitaciones_adj WHERE fecha_publicacion IS NOT NULL AND fecha_publicacion != ''
                    UNION ALL
                    SELECT fecha_publicacion FROM mp_licitaciones_vigentes WHERE fecha_publicacion IS NOT NULL AND fecha_publicacion != ''
                )
            """).fetchone()
            fecha_min_bd = r_fechas["min_f"]
            fecha_max_bd = r_fechas["max_f"]
        except Exception:
            fecha_min_bd = fecha_max_bd = None
        
        st.markdown(f"""
        <div style="background:#F0F9FF; border-left:4px solid #0EA5E9; padding:8px 14px; border-radius:6px; margin-bottom:14px; font-size:12px; color:#075985;">
            <strong>📊 BD activa:</strong> {n_vig_total:,} vigentes · {n_adj_total:,} adjudicadas · 
            <strong>Rango:</strong> {fecha_min_bd or '—'} → {fecha_max_bd or '—'}
        </div>
        """, unsafe_allow_html=True)
        
        # ============ FILTROS ============
        st.markdown("##### 🎛️ Filtros del cockpit")
        
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            periodo = st.selectbox(
                "📅 Período",
                ["Últimos 30 días", "Últimos 90 días", "Últimos 6 meses",
                 "Últimos 12 meses", "Últimos 24 meses", "Todo el histórico"],
                index=5, key="dash_periodo",
                help="Default 'Todo' para no cargar vacío. Cambia según tu análisis."
            )
            periodo_dias = {
                "Últimos 30 días": 30, "Últimos 90 días": 90, "Últimos 6 meses": 180,
                "Últimos 12 meses": 365, "Últimos 24 meses": 730, "Todo el histórico": 99999
            }[periodo]
        
        with col_f2:
            estado_lic = st.selectbox(
                "📋 Estado",
                ["Todas", "Solo vigentes (publicadas)", "Solo adjudicadas (cerradas)"],
                index=0, key="dash_estado"
            )
        
        with col_f3:
            from app.core.catalogo_aidu import CATALOGO_AIDU, label_servicio
            cats_seleccionadas = st.multiselect(
                "🎯 Categorías AIDU",
                options=list(CATALOGO_AIDU.keys()),
                format_func=lambda c: label_servicio(c, "completo"),
                default=[], key="dash_categorias",
                help="Multi-select. Vacío = todas."
            )
        
        col_f4, col_f5, col_f6 = st.columns(3)
        with col_f4:
            try:
                rows = conn.execute("""
                    SELECT DISTINCT region FROM mp_licitaciones_adj WHERE region IS NOT NULL AND region != ''
                    UNION
                    SELECT DISTINCT region FROM mp_licitaciones_vigentes WHERE region IS NOT NULL AND region != ''
                    ORDER BY region
                """).fetchall()
                regiones_bd = [r["region"] for r in rows]
            except Exception:
                regiones_bd = []
            regs_seleccionadas = st.multiselect(
                "📍 Regiones", options=regiones_bd, default=[], key="dash_regiones",
                help=f"{len(regiones_bd)} en BD. Multi-select."
            )
        
        with col_f5:
            try:
                rows = conn.execute("""
                    SELECT DISTINCT tipo FROM mp_licitaciones_adj WHERE tipo IS NOT NULL AND tipo != ''
                    UNION
                    SELECT DISTINCT tipo FROM mp_licitaciones_vigentes WHERE tipo IS NOT NULL AND tipo != ''
                    ORDER BY tipo
                """).fetchall()
                tipos_bd = [r["tipo"] for r in rows]
            except Exception:
                tipos_bd = []
            tipos_seleccionados = st.multiselect(
                "📜 Tipo licitación", options=tipos_bd, default=[], key="dash_tipos",
                help=f"{len(tipos_bd)} tipos. LE/LP/LR/LQ/CO/etc."
            )
        
        with col_f6:
            try:
                rows = conn.execute("""
                    SELECT organismo, COUNT(*) AS n FROM (
                        SELECT organismo FROM mp_licitaciones_adj WHERE organismo IS NOT NULL AND organismo != ''
                        UNION ALL
                        SELECT organismo FROM mp_licitaciones_vigentes WHERE organismo IS NOT NULL AND organismo != ''
                    )
                    GROUP BY organismo ORDER BY n DESC LIMIT 300
                """).fetchall()
                organismos_bd = [r["organismo"] for r in rows]
            except Exception:
                organismos_bd = []
            orgs_seleccionados = st.multiselect(
                "🏛️ Organismos", options=organismos_bd, default=[], key="dash_organismos",
                help=f"Top 300 por frecuencia."
            )
        
        # ============ HELPERS WHERE ============
        hoy = datetime.now().date()
        fecha_desde = (hoy - timedelta(days=periodo_dias)).isoformat()
        usar_adj = estado_lic in ("Todas", "Solo adjudicadas (cerradas)")
        usar_vig = estado_lic in ("Todas", "Solo vigentes (publicadas)")
        
        def _build_clauses_for(tabla_alias="l"):
            """Construye lista de clauses + params según los filtros activos."""
            clauses = []
            params = []
            if periodo_dias < 99999:
                clauses.append(f"{tabla_alias}.fecha_publicacion >= ?")
                params.append(fecha_desde)
            if regs_seleccionadas:
                ph = ",".join(["?"] * len(regs_seleccionadas))
                clauses.append(f"{tabla_alias}.region IN ({ph})")
                params.extend(regs_seleccionadas)
            if tipos_seleccionados:
                ph = ",".join(["?"] * len(tipos_seleccionados))
                clauses.append(f"{tabla_alias}.tipo IN ({ph})")
                params.extend(tipos_seleccionados)
            if orgs_seleccionados:
                ph = ",".join(["?"] * len(orgs_seleccionados))
                clauses.append(f"{tabla_alias}.organismo IN ({ph})")
                params.extend(orgs_seleccionados)
            return clauses, params
        
        join_cat = ""
        cat_clause = ""
        cat_params = []
        if cats_seleccionadas:
            join_cat = "INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo"
            ph = ",".join(["?"] * len(cats_seleccionadas))
            cat_clause = f"c.cod_servicio_aidu IN ({ph})"
            cat_params = list(cats_seleccionadas)
        
        st.divider()
        
        # ============ KPIs ============
        st.markdown("##### 📊 KPIs del mercado · Filtros aplicados")
        
        # KPI Mercado total adjudicado
        monto_adj = 0
        n_adj_filtrado = 0
        if usar_adj:
            clauses, params = _build_clauses_for("l")
            if cat_clause:
                clauses.append(cat_clause)
                params = params + cat_params
            where_str = " WHERE " + " AND ".join(clauses) if clauses else ""
            try:
                row = conn.execute(f"""
                    SELECT COUNT(*) AS n, COALESCE(SUM(monto_adjudicado), 0) AS monto
                    FROM mp_licitaciones_adj l {join_cat} {where_str}
                """, params).fetchone()
                n_adj_filtrado = int(row["n"] or 0)
                monto_adj = int(row["monto"] or 0)
            except Exception as e:
                st.caption(f"⚠️ Adj: {e}")
        
        # KPI Vigentes (sin filtro de período)
        n_vigentes = 0
        if usar_vig:
            cl_v = []
            pa_v = []
            if regs_seleccionadas:
                ph = ",".join(["?"] * len(regs_seleccionadas))
                cl_v.append(f"l.region IN ({ph})"); pa_v.extend(regs_seleccionadas)
            if tipos_seleccionados:
                ph = ",".join(["?"] * len(tipos_seleccionados))
                cl_v.append(f"l.tipo IN ({ph})"); pa_v.extend(tipos_seleccionados)
            if orgs_seleccionados:
                ph = ",".join(["?"] * len(orgs_seleccionados))
                cl_v.append(f"l.organismo IN ({ph})"); pa_v.extend(orgs_seleccionados)
            
            join_v = ""
            if cats_seleccionadas:
                join_v = "INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo"
                cl_v.append(cat_clause)
                pa_v = pa_v + cat_params
            
            where_v_str = " WHERE " + " AND ".join(cl_v) if cl_v else ""
            try:
                row = conn.execute(f"""
                    SELECT COUNT(*) AS n FROM mp_licitaciones_vigentes l {join_v} {where_v_str}
                """, pa_v).fetchone()
                n_vigentes = int(row["n"] or 0)
            except Exception as e:
                st.caption(f"⚠️ Vig: {e}")
        
        ticket_prom = int(monto_adj / n_adj_filtrado) if n_adj_filtrado > 0 else 0
        
        # KPI Perímetro AIDU
        try:
            cl_pa, pa_pa = _build_clauses_for("l")
            where_pa = " WHERE " + " AND ".join(cl_pa) if cl_pa else ""
            row_a = conn.execute(f"""
                SELECT COALESCE(SUM(monto_adjudicado), 0) AS m
                FROM mp_licitaciones_adj l
                INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
                {where_pa}
            """, pa_pa).fetchone()
            monto_aidu = int(row_a["m"] or 0)
            row_t = conn.execute(f"""
                SELECT COALESCE(SUM(monto_adjudicado), 0) AS m FROM mp_licitaciones_adj l {where_pa}
            """, pa_pa).fetchone()
            monto_total = int(row_t["m"] or 0)
            pct_aidu = (monto_aidu / monto_total * 100) if monto_total > 0 else 0
        except Exception:
            monto_aidu = 0; pct_aidu = 0
        
        col_k1, col_k2, col_k3, col_k4 = st.columns(4)
        col_k1.metric("💰 Mercado adjudicado", _formato_clp(monto_adj),
                      delta=f"{n_adj_filtrado:,} licitaciones")
        col_k2.metric("🎯 Perímetro AIDU", f"{pct_aidu:.1f}%",
                      delta=f"{_formato_clp(monto_aidu)} en CE/GP")
        col_k3.metric("🟢 Vigentes ahora", f"{n_vigentes:,}",
                      delta="abiertas a postular")
        col_k4.metric("💵 Ticket promedio", _formato_clp(ticket_prom),
                      delta=f"{n_adj_filtrado:,} muestras")
        
        if monto_adj == 0 and n_vigentes == 0:
            st.warning(
                f"⚠️ Sin licitaciones con estos filtros. BD: {n_vig_total:,} vig + {n_adj_total:,} adj. "
                f"Rango fechas {fecha_min_bd} → {fecha_max_bd}. Prueba ampliar período o quitar filtros."
            )
        
        st.divider()
        
        # ============ DISTRIBUCIONES ============
        col_d1, col_d2 = st.columns(2)
        
        def _query_dist(group_col, limit=15):
            queries = []
            params_all = []
            
            if usar_adj:
                cl, pa = _build_clauses_for("l")
                if cat_clause:
                    cl.append(cat_clause); pa = pa + cat_params
                w = " WHERE " + " AND ".join(cl) if cl else ""
                queries.append(f"""
                    SELECT {group_col} AS grp, COUNT(*) AS n, COALESCE(SUM(monto_adjudicado), 0) AS monto
                    FROM mp_licitaciones_adj l {join_cat} {w}
                    GROUP BY {group_col}
                """)
                params_all.extend(pa)
            
            if usar_vig:
                cl_v = []; pa_v = []
                if regs_seleccionadas:
                    ph = ",".join(["?"] * len(regs_seleccionadas))
                    cl_v.append(f"l.region IN ({ph})"); pa_v.extend(regs_seleccionadas)
                if tipos_seleccionados:
                    ph = ",".join(["?"] * len(tipos_seleccionados))
                    cl_v.append(f"l.tipo IN ({ph})"); pa_v.extend(tipos_seleccionados)
                if orgs_seleccionados:
                    ph = ",".join(["?"] * len(orgs_seleccionados))
                    cl_v.append(f"l.organismo IN ({ph})"); pa_v.extend(orgs_seleccionados)
                join_v = ""
                if cats_seleccionadas:
                    join_v = "INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo"
                    cl_v.append(cat_clause); pa_v = pa_v + cat_params
                w = " WHERE " + " AND ".join(cl_v) if cl_v else ""
                queries.append(f"""
                    SELECT {group_col} AS grp, COUNT(*) AS n, COALESCE(SUM(monto_referencial), 0) AS monto
                    FROM mp_licitaciones_vigentes l {join_v} {w}
                    GROUP BY {group_col}
                """)
                params_all.extend(pa_v)
            
            if not queries:
                return []
            sql = f"""
                SELECT grp, SUM(n) AS n, SUM(monto) AS monto FROM (
                    {' UNION ALL '.join(queries)}
                )
                WHERE grp IS NOT NULL AND grp != ''
                GROUP BY grp ORDER BY n DESC LIMIT {limit}
            """
            try:
                return conn.execute(sql, params_all).fetchall()
            except Exception as e:
                return []
        
        with col_d1:
            st.markdown("##### 🥧 Por tipo de licitación")
            rows = _query_dist("l.tipo", 10)
            if rows:
                total_n = sum(r["n"] for r in rows)
                tabla = []
                for r in rows:
                    pct = (r["n"] / total_n * 100) if total_n else 0
                    tabla.append({
                        "Tipo": r["grp"], "N°": int(r["n"]), "%": f"{pct:.1f}%",
                        "Monto": _formato_clp(int(r["monto"] or 0))
                    })
                st.dataframe(tabla, use_container_width=True, hide_index=True, height=300)
            else:
                st.caption("Sin datos.")
        
        with col_d2:
            st.markdown("##### 🗺️ Por región")
            rows = _query_dist("l.region", 15)
            if rows:
                tabla = []
                for r in rows:
                    tabla.append({
                        "Región": (r["grp"] or "")[:40], "N°": int(r["n"]),
                        "Monto": _formato_clp(int(r["monto"] or 0))
                    })
                st.dataframe(tabla, use_container_width=True, hide_index=True, height=300)
            else:
                st.caption("Sin datos.")
        
        st.divider()
        
        # ============ TOP 15 ORGANISMOS ============
        st.markdown("##### 🏛️ Top 15 organismos compradores")
        st.caption("Ranking por monto adjudicado en el filtro actual.")
        
        if usar_adj:
            cl, pa = _build_clauses_for("l")
            if cat_clause:
                cl.append(cat_clause); pa = pa + cat_params
            cl.append("l.organismo IS NOT NULL AND l.organismo != ''")
            w = " WHERE " + " AND ".join(cl) if cl else ""
            try:
                rows = conn.execute(f"""
                    SELECT l.organismo, l.region, COUNT(*) AS n,
                           COALESCE(SUM(monto_adjudicado), 0) AS monto_total,
                           COALESCE(AVG(monto_adjudicado), 0) AS ticket
                    FROM mp_licitaciones_adj l {join_cat} {w}
                    GROUP BY l.organismo, l.region
                    ORDER BY monto_total DESC LIMIT 15
                """, pa).fetchall()
                
                if rows:
                    tabla = []
                    for i, r in enumerate(rows, 1):
                        tabla.append({
                            "#": i,
                            "Organismo": (r["organismo"] or "")[:55],
                            "Región": (r["region"] or "—")[:25],
                            "Licitaciones": f"{int(r['n']):,}",
                            "Monto total": _formato_clp(int(r["monto_total"] or 0)),
                            "Ticket prom.": _formato_clp(int(r["ticket"] or 0)),
                        })
                    st.dataframe(tabla, use_container_width=True, hide_index=True)
                else:
                    st.info("📭 Sin organismos en el filtro.")
            except Exception as e:
                st.caption(f"Error: {e}")
        else:
            st.caption("Activa 'Todas' o 'Solo adjudicadas' para ver ranking.")
        
        st.divider()
        
        # ============ TABLA EXPLORATORIA INTERACTIVA ============
        st.markdown("##### 📋 Tabla exploratoria · Interactiva")
        st.caption("Click columnas para ordenar · descarga CSV · busca con la lupa de Streamlit")
        
        queries_explo = []
        params_explo = []
        
        if usar_adj:
            cl, pa = _build_clauses_for("l")
            if cat_clause:
                cl.append(cat_clause); pa = pa + cat_params
            w = " WHERE " + " AND ".join(cl) if cl else ""
            j = "INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo" if cats_seleccionadas else "LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo"
            queries_explo.append(f"""
                SELECT 'Adjudicada' AS estado, l.codigo_externo, l.nombre, l.organismo, l.region, l.tipo,
                       l.fecha_publicacion, l.fecha_cierre, l.fecha_adjudicacion,
                       COALESCE(l.monto_referencial, 0) AS monto_referencial,
                       COALESCE(l.monto_adjudicado, 0) AS monto_adjudicado,
                       COALESCE(c.cod_servicio_aidu, '') AS cat_aidu
                FROM mp_licitaciones_adj l {j} {w}
            """)
            params_explo.extend(pa)
        
        if usar_vig:
            cl_v = []; pa_v = []
            if periodo_dias < 99999:
                cl_v.append("l.fecha_publicacion >= ?"); pa_v.append(fecha_desde)
            if regs_seleccionadas:
                ph = ",".join(["?"] * len(regs_seleccionadas))
                cl_v.append(f"l.region IN ({ph})"); pa_v.extend(regs_seleccionadas)
            if tipos_seleccionados:
                ph = ",".join(["?"] * len(tipos_seleccionados))
                cl_v.append(f"l.tipo IN ({ph})"); pa_v.extend(tipos_seleccionados)
            if orgs_seleccionados:
                ph = ",".join(["?"] * len(orgs_seleccionados))
                cl_v.append(f"l.organismo IN ({ph})"); pa_v.extend(orgs_seleccionados)
            j_v = "INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo" if cats_seleccionadas else "LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo"
            if cats_seleccionadas:
                cl_v.append(cat_clause); pa_v = pa_v + cat_params
            w_v = " WHERE " + " AND ".join(cl_v) if cl_v else ""
            queries_explo.append(f"""
                SELECT 'Vigente' AS estado, l.codigo_externo, l.nombre, l.organismo, l.region, l.tipo,
                       l.fecha_publicacion, l.fecha_cierre, NULL AS fecha_adjudicacion,
                       COALESCE(l.monto_referencial, 0) AS monto_referencial,
                       0 AS monto_adjudicado,
                       COALESCE(c.cod_servicio_aidu, '') AS cat_aidu
                FROM mp_licitaciones_vigentes l {j_v} {w_v}
            """)
            params_explo.extend(pa_v)
        
        if queries_explo:
            sql = " UNION ALL ".join(queries_explo) + " ORDER BY fecha_publicacion DESC LIMIT 1500"
            try:
                rows = conn.execute(sql, params_explo).fetchall()
                if rows:
                    import pandas as pd
                    df = pd.DataFrame([dict(r) for r in rows])
                    df.columns = ["Estado", "Código", "Nombre", "Organismo", "Región", "Tipo",
                                  "Publicación", "Cierre", "Adjudicación",
                                  "Monto ref.", "Monto adj.", "Cat. AIDU"]
                    
                    st.dataframe(
                        df, use_container_width=True, hide_index=True, height=480,
                        column_config={
                            "Monto ref.": st.column_config.NumberColumn(format="$%d"),
                            "Monto adj.": st.column_config.NumberColumn(format="$%d"),
                            "Estado": st.column_config.TextColumn(width="small"),
                            "Tipo": st.column_config.TextColumn(width="small"),
                        }
                    )
                    
                    col_e1, col_e2 = st.columns([1, 4])
                    with col_e1:
                        csv = df.to_csv(index=False).encode("utf-8-sig")
                        st.download_button(
                            "📥 Descargar CSV", data=csv,
                            file_name=f"mercado_aidu_{hoy.isoformat()}.csv",
                            mime="text/csv", use_container_width=True
                        )
                    with col_e2:
                        st.caption(
                            f"📊 {len(df):,} licitaciones cumplen el filtro. "
                            f"Click en encabezado para ordenar. CSV con BOM UTF-8 (Excel-friendly)."
                        )
                else:
                    st.info("📭 Sin licitaciones que cumplan los filtros.")
            except Exception as e:
                st.warning(f"Tabla error: {e}")
        else:
            st.info("Selecciona al menos un estado para ver la tabla.")
        
        # ============ GESTIÓN BD ============
        st.divider()
        with st.expander("💾 Gestión de BD · Descarga + sincronización", expanded=False):
            try:
                from app.core.descarga_diaria import ejecutar_descarga
                from app.core.descarga_historica import descargar_rango
                
                col_b1, col_b2, col_b3, col_b4 = st.columns(4)
                col_b1.metric("Vigentes en BD", f"{n_vig_total:,}")
                col_b2.metric("Histórico en BD", f"{n_adj_total:,}")
                
                bd_n_cat = _safe_count(conn, "SELECT COUNT(*) FROM mp_categorizacion_aidu")
                col_b3.metric("Categorizadas AIDU", f"{bd_n_cat:,}")
                col_b4.metric("Cobertura", f"{bd_n_cat * 100 / n_adj_total:.0f}%" if n_adj_total else "0%")
                
                st.markdown("---")
                st.markdown("**🔄 Sincronización rápida (últimos 2 días)**")
                if st.button("🔄 Sincronizar", use_container_width=True, key="sync_btn"):
                    with st.spinner("Sincronizando..."):
                        try:
                            res = ejecutar_descarga(dias_atras=2)
                            st.success("✅ Sincronización completa")
                            st.json(res)
                        except Exception as e:
                            st.error(f"Error: {e}")
                
                st.markdown("---")
                st.markdown("**⏬ Descarga histórica retroactiva**")
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    fecha_desde_dl = st.date_input("Desde", value=hoy - timedelta(days=30), key="dl_desde")
                with col_d2:
                    fecha_hasta_dl = st.date_input("Hasta", value=hoy, key="dl_hasta")
                
                col_chk = st.columns(3)
                inc_vig = col_chk[0].checkbox("Vigentes", value=True, key="dl_inc_vig")
                inc_adj = col_chk[1].checkbox("Adjudicadas", value=True, key="dl_inc_adj")
                saltar = col_chk[2].checkbox("Saltar días descargados", value=True, key="dl_skip")
                
                if st.button("🚀 Iniciar descarga histórica", type="primary", use_container_width=True, key="dl_btn"):
                    progress_bar = st.progress(0)
                    status = st.empty()
                    
                    def cb(actual, total, fecha, n_vig, n_adj_dia, st_str):
                        progress_bar.progress(actual / total if total else 0)
                        status.text(f"📅 {fecha} · {actual}/{total} · +{n_vig} vig / +{n_adj_dia} adj")
                    
                    try:
                        res = descargar_rango(
                            fecha_inicio=fecha_desde_dl, fecha_fin=fecha_hasta_dl,
                            incluir_vigentes=inc_vig, incluir_adjudicadas=inc_adj,
                            saltar_descargados=saltar, progress_callback=cb,
                        )
                        progress_bar.progress(1.0)
                        st.success(f"""🎉 Descarga completa
- Días: {res.get('dias_procesados', 0)} (saltados: {res.get('dias_saltados', 0)})
- Vigentes: +{res.get('vigentes_total', 0)}
- Adjudicadas: +{res.get('adjudicadas_total', 0)}

🔄 Recarga la página (R) para ver los nuevos datos.""")
                    except Exception as e:
                        st.error(f"Error: {e}")
            except Exception as e:
                st.caption(f"Gestión BD: {e}")
    finally:
        conn.close()
