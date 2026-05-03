-- v18 modelo relacional. BD como activo estrategico.

ALTER TABLE mp_licitaciones_vigentes ADD COLUMN hash_raw_json TEXT;
ALTER TABLE mp_licitaciones_vigentes ADD COLUMN fuente TEXT DEFAULT 'api_diaria';
ALTER TABLE mp_licitaciones_vigentes ADD COLUMN version_api TEXT DEFAULT 'v1';

ALTER TABLE mp_licitaciones_adj ADD COLUMN hash_raw_json TEXT;
ALTER TABLE mp_licitaciones_adj ADD COLUMN fuente TEXT DEFAULT 'api_historica';
ALTER TABLE mp_licitaciones_adj ADD COLUMN version_api TEXT DEFAULT 'v1';

CREATE TABLE IF NOT EXISTS mp_proveedores (
    rut TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    n_adjudicaciones INTEGER DEFAULT 0,
    monto_total_adjudicado INTEGER DEFAULT 0,
    primera_adjudicacion TEXT,
    ultima_adjudicacion TEXT,
    regiones_operacion TEXT,
    categorias_aidu_principales TEXT,
    fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_proveedores_nombre ON mp_proveedores(nombre);
CREATE INDEX IF NOT EXISTS idx_proveedores_monto ON mp_proveedores(monto_total_adjudicado DESC);

CREATE TABLE IF NOT EXISTS mp_organismos (
    codigo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    region TEXT,
    comuna TEXT,
    n_licitaciones INTEGER DEFAULT 0,
    monto_total_comprado INTEGER DEFAULT 0,
    ticket_promedio INTEGER DEFAULT 0,
    n_proveedores_distintos INTEGER DEFAULT 0,
    primera_licitacion TEXT,
    ultima_licitacion TEXT,
    proveedor_favorito_rut TEXT,
    proveedor_favorito_n_veces INTEGER DEFAULT 0,
    fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_organismos_nombre ON mp_organismos(nombre);
CREATE INDEX IF NOT EXISTS idx_organismos_region ON mp_organismos(region);
CREATE INDEX IF NOT EXISTS idx_organismos_monto ON mp_organismos(monto_total_comprado DESC);

CREATE TABLE IF NOT EXISTS mp_licitaciones_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_externo TEXT NOT NULL,
    correlativo INTEGER,
    codigo_unspsc TEXT,
    codigo_categoria TEXT,
    categoria_nombre TEXT,
    nombre_producto TEXT NOT NULL,
    descripcion TEXT,
    unidad_medida TEXT,
    cantidad REAL,
    fecha_extraccion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_items_codigo ON mp_licitaciones_items(codigo_externo);
CREATE INDEX IF NOT EXISTS idx_items_unspsc ON mp_licitaciones_items(codigo_unspsc);

CREATE TABLE IF NOT EXISTS mp_adjudicaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_externo TEXT NOT NULL,
    item_correlativo INTEGER,
    rut_proveedor TEXT NOT NULL,
    nombre_proveedor TEXT,
    cantidad_adjudicada REAL,
    monto_unitario INTEGER,
    monto_linea INTEGER,
    fecha_extraccion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_adj_codigo ON mp_adjudicaciones(codigo_externo);
CREATE INDEX IF NOT EXISTS idx_adj_proveedor ON mp_adjudicaciones(rut_proveedor);

CREATE TABLE IF NOT EXISTS mp_fechas_clave (
    codigo_externo TEXT PRIMARY KEY,
    fecha_creacion TEXT,
    fecha_publicacion TEXT,
    fecha_cierre TEXT,
    fecha_inicio_foro TEXT,
    fecha_final_foro TEXT,
    fecha_pub_respuestas TEXT,
    fecha_acto_apertura_tecnica TEXT,
    fecha_acto_apertura_economica TEXT,
    fecha_estimada_adjudicacion TEXT,
    fecha_adjudicacion TEXT,
    fecha_visita_terreno TEXT,
    fecha_entrega_antecedentes TEXT,
    fecha_estimada_firma TEXT,
    fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS mp_historial_cambios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_externo TEXT NOT NULL,
    fecha_cambio TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    campo TEXT NOT NULL,
    valor_anterior TEXT,
    valor_nuevo TEXT,
    hash_anterior TEXT,
    hash_nuevo TEXT,
    fuente_cambio TEXT
);

CREATE INDEX IF NOT EXISTS idx_hist_codigo ON mp_historial_cambios(codigo_externo);
CREATE INDEX IF NOT EXISTS idx_hist_fecha ON mp_historial_cambios(fecha_cambio DESC);
