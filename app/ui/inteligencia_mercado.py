"""
AIDU Op · Pantalla Inteligencia de Mercado (S13)
==================================================
Consume `inteligencia_precios` y expone:

  Tab 1 - Buscador de precios:
    - Input de texto libre (busca en producto_descripcion).
    - Filtros: linea AIDU, tipo objeto, organismo, proveedor,
      rango de fecha de adjudicacion, rango de precio_unitario.
    - Tabla de resultados.
    - Stats agregadas: mediana / p25 / p75 / min / max / n.
    - Top 5 proveedores ganadores del filtro actual.
    - Export Excel.

  Tab 2 - Productos mas comprados:
    - Ranking 50 productos con mayor monto_total acumulado.
    - Columnas: producto, monto_total, cantidad_total, frecuencia
      (n_licitaciones), top 3 organismos compradores, proveedor dominante.
    - Filtro por linea AIDU.
    - Export Excel.

Source: tabla `inteligencia_precios` (mig 009). Una fila = un item adjudicado.
Las estadisticas se calculan al vuelo desde pandas — no hay vistas
materializadas (spec D3 + sec 2.3).
"""
from __future__ import annotations

import io
import logging
import os
from datetime import date, timedelta
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st

from app.db import turso_http_client
from app.db._hrana_types import arg_for_value
from app.db.migrator import get_connection

logger = logging.getLogger(__name__)


# Columnas en orden estricto para zipear los resultados de Turso a un DataFrame.
# Cualquier cambio aqui debe replicarse en el SELECT de _cargar_inteligencia_precios.
_COLS_INTELIGENCIA = [
    "id_item", "codigo_mp", "correlativo_item", "fecha_adjudicacion",
    "tipo_licitacion", "organismo_comprador", "unit_code",
    "organismo_region", "region_entrega", "producto_descripcion",
    "unidad_medida", "cantidad", "precio_unitario", "monto_total",
    "proveedor_nombre", "proveedor_rut", "n_oferentes",
    "linea_aidu", "tipo_objeto", "keywords_matched", "lote_id",
    # S13.4.3: columnas de clasificacion semantica.
    "es_producto_granular", "confidence_score", "clasificacion_metodo",
]


def _safe_int(v, default: int = 0) -> int:
    """Defensive: Hrana puede devolver numeros como string. Coerce a int
    antes de aplicar format spec ':d' o ':,' (evita el bug cosmetico
    documentado en S13.4.2-cleanup)."""
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return default


def _safe_float(v, default: float = 0.0) -> float:
    """Defensive: idem _safe_int para floats."""
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _modo_produccion() -> bool:
    """True si la app debe leer datos via turso_http_client (HTTP) en lugar
    de get_connection() (libsql + SQLite local).

    Detection explicita por env var TURSO_DATABASE_URL: en produccion
    Streamlit Cloud SIEMPRE esta seteada (sino el cron diario tampoco
    funcionaria). Si esta variable existe, el data layer NUNCA cae al
    fallback de SQLite local, aunque turso_http_client.is_configured()
    devuelva False por algun bug de carga de credenciales.

    Tambien acepta st.secrets para corridas en Streamlit Cloud antes de
    que config.settings._load_env() haya inyectado las creds al env.
    """
    if os.getenv("TURSO_DATABASE_URL"):
        return True
    try:
        if hasattr(st, "secrets") and st.secrets.get("TURSO_DATABASE_URL"):
            return True
    except Exception:
        pass
    return False


# ============================================================
# CONSTANTES UI
# ============================================================
# S13.4.2 D4: importar la lista canonica desde el modulo categorizador
# (antes habia 2 listas hardcoded divergentes: el modulo tenia 4 lineas,
# la UI tenia 5). Una unica fuente de verdad.
from app.core.categorizador_aidu_fast import LINEAS_AIDU_FAST_CON_OTROS

LINEAS_AIDU_FAST = LINEAS_AIDU_FAST_CON_OTROS
TIPOS_OBJETO = ["producto", "servicio", "hibrido"]


# ============================================================
# QUERIES (data layer)
# ============================================================

_SELECT_INTELIGENCIA = (
    "SELECT id_item, codigo_mp, correlativo_item, fecha_adjudicacion, "
    "       tipo_licitacion, organismo_comprador, unit_code, "
    "       organismo_region, region_entrega, producto_descripcion, "
    "       unidad_medida, cantidad, precio_unitario, monto_total, "
    "       proveedor_nombre, proveedor_rut, n_oferentes, "
    "       linea_aidu, tipo_objeto, keywords_matched, lote_id, "
    "       es_producto_granular, confidence_score, clasificacion_metodo "
    "  FROM inteligencia_precios "
    " WHERE fecha_adjudicacion BETWEEN ? AND ?"
)


@st.cache_data(ttl=300)
def _cargar_inteligencia_precios(
    fecha_desde_iso: str,
    fecha_hasta_iso: str,
) -> pd.DataFrame:
    """Trae todas las filas del rango.

    Cache 5 min para evitar hits a Turso en cada interaccion del usuario.

    Data layer (S13.2):
      - PRODUCCION (TURSO_DATABASE_URL seteada): consulta directa via
        turso_http_client.query_all() sobre /v2/pipeline. Bypasa libsql,
        bypasa el SQLite local del container (que puede estar corrupto
        o sin schema en Streamlit Cloud), va directo al Turso productivo.
      - DEV/CI (sin TURSO_DATABASE_URL): fallback a get_connection() para
        que los tests y el desarrollo local sigan funcionando.

    Devuelve DataFrame vacio si Turso falla o la migracion 009 no esta
    aplicada. No crashea la UI en ningun caso.
    """
    if _modo_produccion():
        try:
            rows = turso_http_client.query_all(
                _SELECT_INTELIGENCIA,
                [arg_for_value(fecha_desde_iso), arg_for_value(fecha_hasta_iso)],
            )
        except Exception as e:
            logger.warning("inteligencia_mercado: turso_http_client fallo (%s)", e)
            st.warning(
                f"No se pudo leer inteligencia_precios desde Turso ({e}). "
                "Revisar logs y conectividad a /v2/pipeline."
            )
            return pd.DataFrame(columns=_COLS_INTELIGENCIA)
        # rows es lista de listas (Hrana value-extracted). Mapear a DataFrame.
        return pd.DataFrame(rows, columns=_COLS_INTELIGENCIA)

    # DEV/CI: fallback a SQLite local via get_connection().
    # NO se entra aca en produccion: la deteccion explicita por
    # TURSO_DATABASE_URL impide caer al SQLite corrupto.
    try:
        conn = get_connection()
        try:
            cur = conn.execute(
                _SELECT_INTELIGENCIA,
                (fecha_desde_iso, fecha_hasta_iso),
            )
            cols = [d[0] for d in cur.description]
            db_rows = cur.fetchall()
            return pd.DataFrame(db_rows, columns=cols)
        finally:
            conn.close()
    except Exception as e:
        logger.warning("inteligencia_mercado fallback get_connection fallo (%s)", e)
        st.warning(
            f"No se pudo leer inteligencia_precios ({e}). "
            "Verificar que la migracion 009 este aplicada."
        )
        return pd.DataFrame(columns=_COLS_INTELIGENCIA)


# ============================================================
# UTILIDADES
# ============================================================

def _aplicar_filtros(
    df: pd.DataFrame,
    *,
    texto: str,
    linea: Optional[str],
    tipo_objeto: Optional[str],
    organismo: Optional[str],
    proveedor: Optional[str],
    precio_min: Optional[float],
    precio_max: Optional[float],
    solo_granulares: bool = False,
    confidence_min: float = 0.0,
) -> pd.DataFrame:
    if df.empty:
        return df
    f = df
    if texto:
        t = texto.lower()
        f = f[f["producto_descripcion"].fillna("").str.lower().str.contains(t, na=False)]
    if linea and linea != "(todas)":
        f = f[f["linea_aidu"] == linea]
    if tipo_objeto and tipo_objeto != "(todos)":
        f = f[f["tipo_objeto"] == tipo_objeto]
    if organismo:
        f = f[f["organismo_comprador"].fillna("").str.contains(organismo, case=False, na=False)]
    if proveedor:
        f = f[f["proveedor_nombre"].fillna("").str.contains(proveedor, case=False, na=False)]
    if precio_min is not None:
        f = f[f["precio_unitario"].fillna(-1) >= precio_min]
    if precio_max is not None and precio_max > 0:
        f = f[f["precio_unitario"].fillna(1e18) <= precio_max]
    # S13.4.3: filtros nuevos.
    if solo_granulares and "es_producto_granular" in f.columns:
        # Acepta 1, True. Items con NULL (no clasificados semanticamente)
        # tambien se incluyen como "no granulares" para ser conservador.
        f = f[f["es_producto_granular"].apply(lambda v: _safe_int(v) == 1)]
    if confidence_min > 0.0 and "confidence_score" in f.columns:
        f = f[f["confidence_score"].apply(lambda v: _safe_float(v) >= confidence_min)]
    return f


def _df_a_excel_bytes(df: pd.DataFrame, sheet_name: str = "datos") -> bytes:
    """Convierte DataFrame a bytes XLSX para st.download_button."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=sheet_name, index=False)
    return buf.getvalue()


def _stats_precio(df: pd.DataFrame) -> dict:
    """Calcula mediana / p25 / p75 / min / max / n sobre precio_unitario.
    Ignora NULL (esperable hasta 36% en L1 segun hallazgo S13.0)."""
    precios = df["precio_unitario"].dropna()
    if precios.empty:
        return {"n": 0, "mediana": None, "p25": None, "p75": None,
                "minimo": None, "maximo": None}
    return {
        "n": int(len(precios)),
        "mediana": float(precios.median()),
        "p25": float(precios.quantile(0.25)),
        "p75": float(precios.quantile(0.75)),
        "minimo": float(precios.min()),
        "maximo": float(precios.max()),
    }


def _top_proveedores(df: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["proveedor", "n_items", "monto_total"])
    agg = (
        df.groupby(["proveedor_rut", "proveedor_nombre"], dropna=False)
        .agg(n_items=("id_item", "count"), monto_total=("monto_total", "sum"))
        .reset_index()
        .sort_values("monto_total", ascending=False)
        .head(n)
    )
    return agg


def _ranking_productos(df: pd.DataFrame, top_n: int = 50) -> pd.DataFrame:
    """Agrupa por (producto_descripcion lowercase truncated) — proxy de
    'mismo producto' sin requerir homologacion fuerte. Para una version
    posterior, se puede sustituir por clusterizacion semantica."""
    if df.empty:
        return pd.DataFrame(columns=[
            "producto", "monto_total", "cantidad_total", "frecuencia",
            "top_organismos", "proveedor_dominante",
        ])
    f = df.copy()
    f["producto_norm"] = (
        f["producto_descripcion"].fillna("").str.lower().str.strip().str[:80]
    )
    grupos = []
    for producto, sub in f.groupby("producto_norm"):
        if not producto:
            continue
        monto = float(sub["monto_total"].fillna(0).sum())
        cantidad = float(sub["cantidad"].fillna(0).sum())
        freq = int(sub["codigo_mp"].nunique())
        top_orgs = (
            sub["organismo_comprador"].fillna("")
            .value_counts().head(3).index.tolist()
        )
        prov_dom = (
            sub["proveedor_nombre"].fillna("")
            .value_counts().head(1).index.tolist()
        )
        grupos.append({
            "producto": producto,
            "monto_total": monto,
            "cantidad_total": cantidad,
            "frecuencia": freq,
            "top_organismos": " | ".join(o for o in top_orgs if o),
            "proveedor_dominante": prov_dom[0] if prov_dom else "",
        })
    out = pd.DataFrame(grupos).sort_values("monto_total", ascending=False).head(top_n)
    return out


# ============================================================
# RENDER
# ============================================================

def render_inteligencia_mercado() -> None:
    """Entry point invocado desde streamlit_app.py."""
    st.markdown("""
    <div style="margin-bottom:18px;">
      <h1 style="margin:0; font-size:28px;">🛒 Inteligencia de Mercado · O'Higgins</h1>
      <p style="margin:4px 0 0 0; font-size:13px; color:#64748B;">
        Adjudicaciones L1 + LE + CO &lt; 1.000 UTM en Region O'Higgins,
        ventana 90 dias. Fuente: tabla <code>inteligencia_precios</code>.
        (CA fuera del scope hasta resolver
        <a href="#" title="docs/sprints/AIDU_Op_S13_1_Restaurar_Compras_Agiles.md">S13.1</a>.)
      </p>
    </div>
    """, unsafe_allow_html=True)

    # Rango global por defecto: ultimos 90 dias
    hoy = date.today()
    rango_default = (hoy - timedelta(days=90), hoy)
    df_full = _cargar_inteligencia_precios(
        rango_default[0].isoformat(),
        rango_default[1].isoformat(),
    )

    if df_full.empty:
        st.info(
            "**Sin datos todavia.** La tabla `inteligencia_precios` esta vacia. "
            "Para poblarla: disparar el workflow `inteligencia_backfill_lote.yml` "
            "(lote 1 a 4 cubre 90 dias) o esperar al cron diario."
        )
        return

    tab_buscar, tab_top = st.tabs([
        "🔍 Buscador de precios",
        "📈 Productos mas comprados",
    ])

    with tab_buscar:
        _render_tab_buscador(df_full)
    with tab_top:
        _render_tab_top_productos(df_full)


def _render_tab_buscador(df_full: pd.DataFrame) -> None:
    st.subheader("Buscar precios adjudicados")
    col_izq, col_der = st.columns([2, 1])
    with col_izq:
        texto = st.text_input(
            "Buscar en descripcion del item",
            placeholder="Ej: cemento, papel higienico, computador, ...",
            key="ip_search_text",
        )
    with col_der:
        linea = st.selectbox(
            "Linea AIDU",
            options=["(todas)"] + LINEAS_AIDU_FAST,
            key="ip_filter_linea",
        )

    with st.expander("Filtros avanzados"):
        c1, c2, c3 = st.columns(3)
        with c1:
            tipo_obj = st.selectbox(
                "Tipo objeto",
                options=["(todos)"] + TIPOS_OBJETO,
                key="ip_filter_tipo",
            )
        with c2:
            organismo = st.text_input("Organismo (contiene)", key="ip_filter_org")
        with c3:
            proveedor = st.text_input("Proveedor (contiene)", key="ip_filter_prov")
        c4, c5 = st.columns(2)
        with c4:
            precio_min = st.number_input(
                "Precio unitario minimo (CLP)",
                min_value=0.0, value=0.0, step=1000.0,
                key="ip_filter_pmin",
            )
        with c5:
            precio_max = st.number_input(
                "Precio unitario maximo (CLP, 0 = sin tope)",
                min_value=0.0, value=0.0, step=1000.0,
                key="ip_filter_pmax",
            )
        # S13.4.3: nuevos filtros semanticos
        c6, c7 = st.columns(2)
        with c6:
            solo_granulares = st.checkbox(
                "Solo productos granulares",
                value=True,
                help="Excluye contratos marco, obras, servicios sin grano fisico. "
                     "Recomendado para analisis de precios.",
                key="ip_filter_granular",
            )
        with c7:
            confidence_min_pct = st.slider(
                "Confidence minima (%)",
                min_value=0, max_value=100, value=0, step=10,
                help="Filtra por confidence_score del clasificador semantico. "
                     "0 = sin filtro.",
                key="ip_filter_conf",
            )

    df_filtrado = _aplicar_filtros(
        df_full,
        texto=texto,
        linea=linea,
        tipo_objeto=tipo_obj,
        organismo=organismo,
        proveedor=proveedor,
        precio_min=precio_min if precio_min > 0 else None,
        precio_max=precio_max if precio_max > 0 else None,
        solo_granulares=solo_granulares,
        confidence_min=confidence_min_pct / 100.0,
    )

    # Stats — defensive: Hrana puede devolver numeros como string. Coerce
    # explicitamente a int antes de aplicar format spec ',' o ':d'
    # (evita ValueError: Unknown format code 'd' for object of type 'str').
    stats = _stats_precio(df_filtrado)
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("N muestras", f"{_safe_int(stats['n']):,}")
    c2.metric("Mediana", f"${_safe_int(stats['mediana']):,}" if stats["mediana"] else "—")
    c3.metric("P25", f"${_safe_int(stats['p25']):,}" if stats["p25"] else "—")
    c4.metric("P75", f"${_safe_int(stats['p75']):,}" if stats["p75"] else "—")
    c5.metric("Minimo", f"${_safe_int(stats['minimo']):,}" if stats["minimo"] else "—")
    c6.metric("Maximo", f"${_safe_int(stats['maximo']):,}" if stats["maximo"] else "—")

    # Top proveedores
    st.markdown("##### Top 5 proveedores en este filtro")
    top_prov = _top_proveedores(df_filtrado, n=5)
    st.dataframe(top_prov, use_container_width=True, hide_index=True)

    # Tabla de resultados (limit 500 para no romper Streamlit con N grande)
    # Defensive: len() devuelve int genuino; aun asi pasamos por _safe_int
    # por consistencia con el patron del modulo.
    st.markdown(
        f"##### Resultados ({_safe_int(len(df_filtrado)):,} items, mostrando hasta 500)"
    )
    cols_visibles = [
        "fecha_adjudicacion", "tipo_licitacion", "linea_aidu", "tipo_objeto",
        "producto_descripcion", "cantidad", "unidad_medida",
        "precio_unitario", "monto_total",
        "proveedor_nombre", "organismo_comprador", "n_oferentes",
        # S13.4.3: confidence + metodo + granular para auditoria visual
        "confidence_score", "clasificacion_metodo", "es_producto_granular",
        "codigo_mp", "keywords_matched",
    ]
    cols_validas = [c for c in cols_visibles if c in df_filtrado.columns]
    df_display = df_filtrado[cols_validas].head(500).copy()
    # Format confidence como porcentaje legible (defensive coerce a float)
    if "confidence_score" in df_display.columns:
        df_display["confidence_score"] = df_display["confidence_score"].apply(
            lambda v: f"{int(_safe_float(v) * 100)}%" if v not in (None, "") else "—"
        )
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    # Export Excel
    if not df_filtrado.empty:
        excel_bytes = _df_a_excel_bytes(df_filtrado[cols_validas], sheet_name="buscador")
        st.download_button(
            "⬇️ Exportar a Excel",
            data=excel_bytes,
            file_name=f"inteligencia_precios_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ip_export_buscador",
        )


def _render_tab_top_productos(df_full: pd.DataFrame) -> None:
    st.subheader("Productos mas comprados (90 dias)")
    linea = st.selectbox(
        "Filtrar por linea AIDU",
        options=["(todas)"] + LINEAS_AIDU_FAST,
        key="ip_top_linea",
    )
    df = df_full
    if linea and linea != "(todas)":
        df = df[df["linea_aidu"] == linea]

    ranking = _ranking_productos(df, top_n=50)
    st.markdown(f"##### Ranking top 50 (filtrados: {len(df):,} items)")
    st.dataframe(ranking, use_container_width=True, hide_index=True)

    if not ranking.empty:
        excel_bytes = _df_a_excel_bytes(ranking, sheet_name="top_productos")
        st.download_button(
            "⬇️ Exportar a Excel",
            data=excel_bytes,
            file_name=f"top_productos_{date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="ip_export_top",
        )
