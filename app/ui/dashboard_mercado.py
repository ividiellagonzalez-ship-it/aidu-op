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
        # IMPORTANTE: usar DISTINCT codigo_externo para no contar múltiples veces
        # las licitaciones que están categorizadas en varias categorías AIDU.
        try:
            cl_pa, pa_pa = _build_clauses_for("l")
            where_pa = " WHERE " + " AND ".join(cl_pa) if cl_pa else ""
            
            # Monto en categorías AIDU: cada licitación cuenta UNA sola vez aunque tenga N categorías
            row_a = conn.execute(f"""
                SELECT COALESCE(SUM(monto_adjudicado), 0) AS m
                FROM mp_licitaciones_adj l
                WHERE l.codigo_externo IN (
                    SELECT DISTINCT c.codigo_externo FROM mp_categorizacion_aidu c
                )
                {' AND ' + ' AND '.join(cl_pa) if cl_pa else ''}
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
        
        # === KPIs clickeables: botones detalle ===
        col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
        ver_kpi_1 = col_btn1.button("🔍 Detalle", key="kpi_detail_1", use_container_width=True)
        ver_kpi_2 = col_btn2.button("🔍 Detalle", key="kpi_detail_2", use_container_width=True)
        ver_kpi_3 = col_btn3.button("🔍 Detalle", key="kpi_detail_3", use_container_width=True)
        ver_kpi_4 = col_btn4.button("🔍 Detalle", key="kpi_detail_4", use_container_width=True)
        
        # Popup KPI 1: Mercado adjudicado
        if ver_kpi_1:
            with st.expander("💰 Detalle · Mercado adjudicado", expanded=True):
                st.markdown("**Definición**: Suma de `monto_adjudicado` de todas las licitaciones que cumplen los filtros activos. Refleja el volumen real de negocio cerrado en el período y nicho elegido.")
                st.markdown(f"**Fórmula**: `SUM(monto_adjudicado) FROM mp_licitaciones_adj WHERE filtros`")
                st.markdown("---")
                
                if usar_adj and n_adj_filtrado > 0:
                    cl, pa = _build_clauses_for("l")
                    if cat_clause: cl.append(cat_clause); pa = pa + cat_params
                    w = " WHERE " + " AND ".join(cl) if cl else ""
                    
                    # Distribución
                    try:
                        rows_d = conn.execute(f"""
                            SELECT 
                                MIN(monto_adjudicado) AS minimo,
                                MAX(monto_adjudicado) AS maximo,
                                AVG(monto_adjudicado) AS promedio,
                                CAST(SUM(CASE WHEN monto_adjudicado < 5000000 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS pct_pequeño,
                                CAST(SUM(CASE WHEN monto_adjudicado BETWEEN 5000000 AND 30000000 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS pct_sweet,
                                CAST(SUM(CASE WHEN monto_adjudicado > 30000000 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS pct_grande
                            FROM mp_licitaciones_adj l {join_cat} {w}
                            AND monto_adjudicado > 0
                        """ if cl else f"""
                            SELECT 
                                MIN(monto_adjudicado) AS minimo,
                                MAX(monto_adjudicado) AS maximo,
                                AVG(monto_adjudicado) AS promedio,
                                CAST(SUM(CASE WHEN monto_adjudicado < 5000000 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS pct_pequeño,
                                CAST(SUM(CASE WHEN monto_adjudicado BETWEEN 5000000 AND 30000000 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS pct_sweet,
                                CAST(SUM(CASE WHEN monto_adjudicado > 30000000 THEN 1 ELSE 0 END) AS REAL) / COUNT(*) * 100 AS pct_grande
                            FROM mp_licitaciones_adj l {join_cat} WHERE monto_adjudicado > 0
                        """, pa).fetchone()
                        
                        d_col1, d_col2, d_col3 = st.columns(3)
                        d_col1.metric("Mínimo", _formato_clp(int(rows_d["minimo"] or 0)))
                        d_col2.metric("Promedio", _formato_clp(int(rows_d["promedio"] or 0)))
                        d_col3.metric("Máximo", _formato_clp(int(rows_d["maximo"] or 0)))
                        
                        st.markdown(f"""
                        **Distribución por tamaño** (sweet spot AIDU = $5M-$30M):
                        - 🔴 Pequeñas (<$5M): {rows_d['pct_pequeño']:.1f}%
                        - 🟢 Sweet spot ($5M-$30M): {rows_d['pct_sweet']:.1f}%
                        - 🟡 Grandes (>$30M): {rows_d['pct_grande']:.1f}%
                        """)
                    except Exception as e:
                        st.caption(f"Distribución no disponible: {e}")
                    
                    # Top 5
                    try:
                        rows_top = conn.execute(f"""
                            SELECT codigo_externo, nombre, organismo, region, monto_adjudicado, fecha_adjudicacion
                            FROM mp_licitaciones_adj l {join_cat} {w}
                            AND monto_adjudicado > 0 ORDER BY monto_adjudicado DESC LIMIT 5
                        """ if cl else f"""
                            SELECT codigo_externo, nombre, organismo, region, monto_adjudicado, fecha_adjudicacion
                            FROM mp_licitaciones_adj l {join_cat} WHERE monto_adjudicado > 0 ORDER BY monto_adjudicado DESC LIMIT 5
                        """, pa).fetchall()
                        if rows_top:
                            st.markdown("**Top 5 adjudicaciones**:")
                            for i, r in enumerate(rows_top, 1):
                                st.markdown(f"{i}. **{_formato_clp(int(r['monto_adjudicado']))}** · {(r['nombre'] or '')[:60]} · {(r['organismo'] or '')[:40]}")
                    except Exception:
                        pass
                else:
                    st.info("Activa 'Solo adjudicadas' o 'Todas' en el filtro Estado.")
        
        # Popup KPI 2: Perímetro AIDU
        if ver_kpi_2:
            with st.expander("🎯 Detalle · Perímetro AIDU", expanded=True):
                st.markdown("**Definición**: Porcentaje del mercado total que cae dentro de las categorías AIDU (CE-XX y GP-XX). Indica qué tan grande es tu nicho dentro del universo de licitaciones del período.")
                st.markdown("**Fórmula**: `(SUM($) en categorías AIDU / SUM($) total mercado) × 100`")
                st.markdown("---")
                d_col1, d_col2 = st.columns(2)
                d_col1.metric("$ en categorías AIDU (único)", _formato_clp(monto_aidu),
                              help="Cada licitación cuenta UNA sola vez aunque esté en varias categorías AIDU")
                d_col2.metric("$ total mercado (filtro)", _formato_clp(monto_total))
                
                # Desglose por categoría (aquí SÍ se cuenta varias veces si una licitación tiene varias categorías)
                try:
                    cl_pa, pa_pa = _build_clauses_for("l")
                    where_pa = " WHERE " + " AND ".join(cl_pa) if cl_pa else ""
                    rows_cat = conn.execute(f"""
                        SELECT c.cod_servicio_aidu, 
                               COUNT(DISTINCT l.codigo_externo) AS n_lic,
                               SUM(l.monto_adjudicado) AS monto
                        FROM mp_licitaciones_adj l
                        INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo
                        {where_pa}
                        GROUP BY c.cod_servicio_aidu ORDER BY monto DESC
                    """, pa_pa).fetchall()
                    if rows_cat:
                        st.markdown("**Desglose por categoría AIDU**:")
                        st.caption("ℹ️ Una licitación puede aparecer en varias categorías. Por eso la suma de esta tabla puede ser mayor al $ único de arriba.")
                        tabla = []
                        for r in rows_cat:
                            tabla.append({
                                "Categoría": r["cod_servicio_aidu"],
                                "Licitaciones únicas": int(r["n_lic"]),
                                "Monto": _formato_clp(int(r["monto"] or 0)),
                            })
                        st.dataframe(tabla, use_container_width=True, hide_index=True)
                except Exception as e:
                    st.caption(f"Desglose no disponible: {e}")
        
        # Popup KPI 3: Vigentes ahora
        if ver_kpi_3:
            with st.expander("🟢 Detalle · Vigentes ahora", expanded=True):
                st.markdown("**Definición**: Licitaciones publicadas en estado 'Publicada' que aún están abiertas para postular. **Independiente del filtro de período** porque las vigentes son siempre 'ahora'.")
                st.markdown("**Fórmula**: `COUNT(*) FROM mp_licitaciones_vigentes WHERE filtros (sin período)`")
                st.markdown("---")
                
                if n_vigentes > 0:
                    try:
                        from datetime import datetime as _dt
                        hoy_iso = _dt.now().date().isoformat()
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
                        join_v = "INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = l.codigo_externo" if cats_seleccionadas else ""
                        if cats_seleccionadas:
                            cl_v.append(cat_clause); pa_v = pa_v + cat_params
                        w_v = " WHERE " + " AND ".join(cl_v) if cl_v else ""
                        
                        # Cierres próximos
                        rows_cierre = conn.execute(f"""
                            SELECT 
                                SUM(CASE WHEN date(fecha_cierre) <= date(?, '+7 days') THEN 1 ELSE 0 END) AS prox_7d,
                                SUM(CASE WHEN date(fecha_cierre) > date(?, '+7 days') AND date(fecha_cierre) <= date(?, '+30 days') THEN 1 ELSE 0 END) AS prox_30d,
                                SUM(CASE WHEN date(fecha_cierre) > date(?, '+30 days') THEN 1 ELSE 0 END) AS lejanas
                            FROM mp_licitaciones_vigentes l {join_v} {w_v}
                            {'AND' if w_v else 'WHERE'} fecha_cierre IS NOT NULL
                        """, [hoy_iso, hoy_iso, hoy_iso, hoy_iso] + pa_v).fetchone()
                        
                        c1, c2, c3 = st.columns(3)
                        c1.metric("🔥 Cierran ≤7 días", int(rows_cierre["prox_7d"] or 0))
                        c2.metric("⏱️ Cierran 7-30 días", int(rows_cierre["prox_30d"] or 0))
                        c3.metric("📅 Cierran >30 días", int(rows_cierre["lejanas"] or 0))
                        
                        # Top 5 con cierre más cercano
                        rows_urg = conn.execute(f"""
                            SELECT codigo_externo, nombre, organismo, fecha_cierre, monto_referencial
                            FROM mp_licitaciones_vigentes l {join_v} {w_v}
                            {'AND' if w_v else 'WHERE'} fecha_cierre IS NOT NULL AND date(fecha_cierre) >= date(?)
                            ORDER BY fecha_cierre ASC LIMIT 5
                        """, pa_v + [hoy_iso]).fetchall()
                        if rows_urg:
                            st.markdown("**Top 5 con cierre más urgente**:")
                            for r in rows_urg:
                                st.markdown(f"- **{r['fecha_cierre'][:10]}** · {(r['nombre'] or '')[:60]} · {_formato_clp(int(r['monto_referencial'] or 0))}")
                    except Exception as e:
                        st.caption(f"Cierres no disponibles: {e}")
                else:
                    st.info("Sin vigentes con los filtros activos.")
        
        # Popup KPI 4: Ticket promedio
        if ver_kpi_4:
            with st.expander("💵 Detalle · Ticket promedio", expanded=True):
                st.markdown("**Definición**: Monto promedio adjudicado por licitación en el filtro actual. **Promedio aritmético** (no mediana). Útil para calibrar tarifas y entender el tamaño típico de proyecto.")
                st.markdown("**Fórmula**: `AVG(monto_adjudicado) WHERE monto > 0`")
                st.markdown("---")
                
                if usar_adj and n_adj_filtrado > 0:
                    try:
                        cl, pa = _build_clauses_for("l")
                        if cat_clause: cl.append(cat_clause); pa = pa + cat_params
                        w = " WHERE " + " AND ".join(cl) if cl else ""
                        
                        # Mediana aproximada con percentiles
                        rows = conn.execute(f"""
                            SELECT monto_adjudicado FROM mp_licitaciones_adj l {join_cat} {w}
                            {'AND' if w else 'WHERE'} monto_adjudicado > 0
                            ORDER BY monto_adjudicado ASC
                        """, pa).fetchall()
                        montos = [int(r["monto_adjudicado"]) for r in rows]
                        if montos:
                            n = len(montos)
                            mediana = montos[n // 2]
                            p25 = montos[n // 4]
                            p75 = montos[3 * n // 4]
                            
                            c1, c2, c3, c4 = st.columns(4)
                            c1.metric("P25", _formato_clp(p25), help="25% de licitaciones bajo este monto")
                            c2.metric("Mediana", _formato_clp(mediana), help="50%: típico real")
                            c3.metric("Promedio", _formato_clp(ticket_prom), help="Sesgado por outliers")
                            c4.metric("P75", _formato_clp(p75), help="75% bajo este monto")
                            
                            if mediana < ticket_prom * 0.7:
                                st.warning(f"⚠️ Promedio ({_formato_clp(ticket_prom)}) está sesgado hacia arriba por licitaciones grandes. La **mediana ({_formato_clp(mediana)})** representa mejor el tamaño típico.")
                            else:
                                st.success(f"✅ Distribución equilibrada. Promedio y mediana son similares.")
                    except Exception as e:
                        st.caption(f"Estadísticos no disponibles: {e}")
                else:
                    st.info("Activa 'Solo adjudicadas' para ver estadísticos.")
        
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
        
        # ============ INTELIGENCIA DE PRECIOS (S11.3) ============
        st.divider()
        st.markdown("##### 💎 Inteligencia de precios · Tarifas de mercado vs tu costo")
        st.caption("CLP/HH del mercado por categoría y tipo de licitación. Comparado contra tu costo HH AIDU. Tu calculadora de tarifa competitiva.")
        
        try:
            from app.core.inteligencia_precios_v2 import (
                tarifas_por_categoria, tarifas_por_categoria_y_tipo,
                clp_m2_por_categoria, benchmark_tipo_licitacion,
                stats_globales_inteligencia, COSTO_HH_AIDU
            )
            
            stats_ip = stats_globales_inteligencia()
            n_cats = stats_ip.get("n_categorias_con_data", 0)
            n_tipos = stats_ip.get("n_tipos_con_data", 0)
            
            if n_cats == 0:
                st.info(
                    "📭 Sin datos suficientes para inteligencia de precios. Necesitas:\n"
                    "1. Licitaciones adjudicadas con monto > 0\n"
                    "2. Categorización AIDU (CE-XX/GP-XX) en mp_categorizacion_aidu\n"
                    "3. HH (tabla maestra o extraídas)\n\n"
                    "💡 Acción: scroll abajo y ejecuta '⚡ Extraer indicadores (lote)' "
                    "para asignar HH desde la tabla maestra."
                )
            else:
                # KPI cards top
                ip_c1, ip_c2, ip_c3, ip_c4 = st.columns(4)
                ip_c1.metric("Categorías con tarifa", f"{n_cats}",
                             help="Categorías AIDU que tienen al menos 1 licitación con HH calculadas")
                ip_c2.metric("Tipos analizados", f"{n_tipos}",
                             help="LE/LP/LR/LQ/AGIL/etc presentes en BD")
                
                mejor = stats_ip.get("mejor_categoria")
                peor = stats_ip.get("peor_categoria")
                if mejor:
                    ip_c3.metric(
                        f"💰 Mejor margen: {mejor['categoria']}",
                        f"${mejor['clp_hh_mediana']:,}/HH",
                        delta=f"{mejor['margen_vs_aidu_pct']:+.1f}% vs tu costo",
                    )
                if peor and peor != mejor:
                    ip_c4.metric(
                        f"⚠️ Menor margen: {peor['categoria']}",
                        f"${peor['clp_hh_mediana']:,}/HH",
                        delta=f"{peor['margen_vs_aidu_pct']:+.1f}% vs tu costo",
                    )
                
                # Tabla principal: tarifas por categoría
                st.markdown("**📊 Tarifas por categoría AIDU** (tu costo HH = $92,040)")
                cats_data = tarifas_por_categoria()
                if cats_data:
                    tabla_ip = []
                    for r in cats_data:
                        margen = r["margen_vs_aidu_pct"]
                        if margen >= 30:
                            color = "🟢"
                        elif margen >= 10:
                            color = "🟡"
                        elif margen >= 0:
                            color = "🟠"
                        else:
                            color = "🔴"
                        tabla_ip.append({
                            "Categoría": r["categoria"],
                            "N° lic.": r["n_licitaciones"],
                            "CLP/HH min": f"${r['clp_hh_min']:,}",
                            "CLP/HH mediana": f"${r['clp_hh_mediana']:,}",
                            "CLP/HH max": f"${r['clp_hh_max']:,}",
                            "Margen vs AIDU": f"{color} {margen:+.1f}%",
                        })
                    st.dataframe(tabla_ip, use_container_width=True, hide_index=True)
                
                # Benchmark por tipo licitación
                with st.expander("🔍 Benchmark por tipo de licitación (LE/LP/LR/LQ/AGIL)", expanded=False):
                    st.caption("¿Qué tipo de licitación paga mejor por hora?")
                    tipos_data = benchmark_tipo_licitacion()
                    if tipos_data:
                        tabla_tipos = []
                        for r in tipos_data:
                            tabla_tipos.append({
                                "Tipo": r["tipo"],
                                "N° lic.": r["n"],
                                "CLP/HH mediana": f"${r['clp_hh_mediana']:,}",
                                "CLP/HH promedio": f"${r['clp_hh_promedio']:,}",
                                "Margen vs AIDU": f"{r['margen_vs_aidu_pct']:+.1f}%",
                            })
                        st.dataframe(tabla_tipos, use_container_width=True, hide_index=True)
                        
                        # Insight automático
                        if len(tipos_data) >= 2:
                            mejor_tipo = tipos_data[0]
                            peor_tipo = tipos_data[-1]
                            diff = mejor_tipo["clp_hh_mediana"] - peor_tipo["clp_hh_mediana"]
                            st.info(
                                f"💡 **Insight**: {mejor_tipo['tipo']} paga ${diff:,}/HH más que {peor_tipo['tipo']} "
                                f"(diferencia mediana). Prioriza {mejor_tipo['tipo']} si tienes flexibilidad."
                            )
                    else:
                        st.caption("Sin datos de tipos.")
                
                # Detalle categoría × tipo
                with st.expander("🔬 Detalle categoría × tipo (matriz fina)", expanded=False):
                    st.caption("Ejemplo: 'CE-01 en LP' vs 'CE-01 en AGIL'")
                    detalle_data = tarifas_por_categoria_y_tipo()
                    if detalle_data:
                        tabla_det = []
                        for r in detalle_data:
                            tabla_det.append({
                                "Categoría": r["categoria"],
                                "Tipo": r["tipo"],
                                "N°": r["n_licitaciones"],
                                "CLP/HH mediana": f"${r['clp_hh_mediana']:,}",
                                "Margen": f"{r['margen_vs_aidu_pct']:+.1f}%",
                            })
                        st.dataframe(tabla_det, use_container_width=True, hide_index=True)
                
                # CLP/m² para categorías que aplican
                m2_data = clp_m2_por_categoria()
                if m2_data:
                    with st.expander("🏗️ CLP/m² (categorías con superficie)", expanded=False):
                        st.caption("Para CE-01/02/03 cuando se extrajo m² del texto.")
                        tabla_m2 = []
                        for r in m2_data:
                            tabla_m2.append({
                                "Categoría": r["categoria"],
                                "N° muestras": r["n_muestras"],
                                "CLP/m² min": f"${r['clp_m2_min']:,}",
                                "CLP/m² mediana": f"${r['clp_m2_mediana']:,}",
                                "CLP/m² max": f"${r['clp_m2_max']:,}",
                            })
                        st.dataframe(tabla_m2, use_container_width=True, hide_index=True)
        except Exception as e:
            st.warning(f"⚠️ Inteligencia de precios no disponible: {e}")
        
        # ============ TABLA MAESTRA HOMOLOGACIÓN (editable) ============
        st.divider()
        st.markdown("##### 🛠️ Tabla maestra de homologación · Tu conocimiento técnico")
        st.caption("Edita HH típicas, plazo, entregables por categoría AIDU. Estos valores alimentan la inteligencia de precios y se aplican como fallback cuando no se pueden extraer del texto de la licitación.")
        
        try:
            from app.core.homologacion import (
                seed_homologacion, listar_homologacion, actualizar_homologacion,
                stats_extraccion, extraer_lote
            )
            
            # Auto-seed la primera vez
            try:
                seed_homologacion(forzar=False)
            except Exception:
                pass
            
            # Stats extracción
            try:
                ext_stats = stats_extraccion()
            except Exception:
                ext_stats = {"total_adj": 0, "extraidas": 0, "pct_cobertura": 0,
                             "pct_plazo": 0, "pct_m2": 0, "pct_hh": 0}
            
            ce_col1, ce_col2, ce_col3, ce_col4 = st.columns(4)
            ce_col1.metric("Cobertura extracción", f"{ext_stats['pct_cobertura']:.1f}%",
                           delta=f"{ext_stats['extraidas']:,} de {ext_stats['total_adj']:,}")
            ce_col2.metric("Con plazo extraído", f"{ext_stats['pct_plazo']:.1f}%")
            ce_col3.metric("Con m² extraído", f"{ext_stats['pct_m2']:.1f}%")
            ce_col4.metric("Con HH estimadas", f"{ext_stats['pct_hh']:.1f}%")
            
            # Botón ejecutar extracción lote
            ce_btn1, ce_btn2 = st.columns([1, 3])
            with ce_btn1:
                if st.button("⚡ Extraer indicadores (lote)", use_container_width=True, key="extr_lote_btn",
                             help="Aplica heurísticas a hasta 1000 licitaciones pendientes."):
                    with st.spinner("Extrayendo indicadores de hasta 1000 licitaciones..."):
                        try:
                            res = extraer_lote(limit=1000, solo_pendientes=True)
                            st.success(
                                f"✅ Procesadas {res['total']} · "
                                f"con plazo: {res['con_plazo']} · "
                                f"con m²: {res['con_m2']} · "
                                f"con entregables: {res['con_entregables']} · "
                                f"con HH: {res['con_hh']}"
                            )
                        except Exception as e:
                            st.error(f"Error: {e}")
            with ce_btn2:
                st.caption("💡 La extracción heurística busca patrones de plazo/m²/entregables en el texto de cada licitación. Las HH se asignan desde la tabla maestra según la categoría AIDU.")
            
            with st.expander("✏️ Editar tabla maestra", expanded=False):
                st.caption("Edita los valores directamente. Los cambios se guardan al hacer click en '💾 Guardar cambios'.")
                
                items = listar_homologacion()
                if items:
                    import pandas as pd
                    df_hom = pd.DataFrame(items)
                    df_hom_show = df_hom[[
                        "cod_servicio_aidu", "nombre_servicio", "linea",
                        "hh_tipicas", "plazo_dias_tipico", "entregables_tipicos",
                        "aplica_m2", "m2_referencia", "notas"
                    ]].copy()
                    df_hom_show.columns = [
                        "Código", "Servicio", "Línea",
                        "HH típicas", "Plazo días", "Entregables típicos",
                        "Aplica m²", "m² ref.", "Notas"
                    ]
                    
                    edited_df = st.data_editor(
                        df_hom_show,
                        use_container_width=True,
                        hide_index=True,
                        height=460,
                        column_config={
                            "Código": st.column_config.TextColumn(disabled=True, width="small"),
                            "Línea": st.column_config.TextColumn(disabled=True, width="small"),
                            "HH típicas": st.column_config.NumberColumn(min_value=1, max_value=10000, step=10),
                            "Plazo días": st.column_config.NumberColumn(min_value=1, max_value=730, step=5),
                            "Aplica m²": st.column_config.CheckboxColumn(),
                            "m² ref.": st.column_config.NumberColumn(min_value=0, max_value=100000, step=50),
                        },
                        key="data_editor_homologacion"
                    )
                    
                    if st.button("💾 Guardar cambios en tabla maestra", type="primary", key="save_hom_btn"):
                        cambios = 0
                        for idx, row in edited_df.iterrows():
                            cod = row["Código"]
                            try:
                                actualizar_homologacion(
                                    cod,
                                    nombre_servicio=row["Servicio"],
                                    hh_tipicas=int(row["HH típicas"]),
                                    plazo_dias_tipico=int(row["Plazo días"]),
                                    entregables_tipicos=row["Entregables típicos"] or "",
                                    aplica_m2=1 if row["Aplica m²"] else 0,
                                    m2_referencia=int(row["m² ref."] or 0),
                                    notas=row["Notas"] or "",
                                )
                                cambios += 1
                            except Exception as e:
                                st.error(f"Error guardando {cod}: {e}")
                        st.success(f"✅ {cambios} categorías actualizadas")
                else:
                    st.info("Tabla maestra vacía. Recarga la página para auto-seed.")
        except Exception as e:
            st.warning(f"⚠️ Tabla maestra no disponible: {e}")
        
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
                
                col_chk = st.columns(4)
                inc_vig = col_chk[0].checkbox("Vigentes", value=True, key="dl_inc_vig")
                inc_adj = col_chk[1].checkbox("Adjudicadas", value=True, key="dl_inc_adj")
                inc_agiles = col_chk[2].checkbox("🚀 Compras Ágiles", value=True, key="dl_inc_agil",
                                                  help="<100 UTM, plazos cortos. Vector de entrada AIDU.")
                saltar = col_chk[3].checkbox("Saltar días descargados", value=True, key="dl_skip")
                
                if st.button("🚀 Iniciar descarga histórica", type="primary", use_container_width=True, key="dl_btn"):
                    progress_bar = st.progress(0)
                    status = st.empty()
                    
                    def cb(actual, total, fecha, n_vig, n_adj_dia, st_str):
                        progress_bar.progress(actual / total if total else 0)
                        status.text(f"📅 {fecha} · {actual}/{total} · +{n_vig} vig / +{n_adj_dia} adj · {st_str}")
                    
                    try:
                        res = descargar_rango(
                            fecha_inicio=fecha_desde_dl, fecha_fin=fecha_hasta_dl,
                            incluir_vigentes=inc_vig, incluir_adjudicadas=inc_adj,
                            incluir_agiles=inc_agiles,
                            saltar_descargados=saltar, progress_callback=cb,
                        )
                        progress_bar.progress(1.0)
                        st.success(f"""🎉 Descarga completa
- Días: {res.get('dias_procesados', 0)} (saltados: {res.get('dias_saltados', 0)})
- Vigentes: +{res.get('total_vigentes', 0)}
- Adjudicadas: +{res.get('total_adjudicadas', 0)}
- 🚀 Compras Ágiles: +{res.get('total_agiles', 0)}

🔄 Recarga la página (R) para ver los nuevos datos.""")
                    except Exception as e:
                        st.error(f"Error: {e}")
            except Exception as e:
                st.caption(f"Gestión BD: {e}")
    finally:
        conn.close()
