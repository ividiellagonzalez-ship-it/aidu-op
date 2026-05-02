-- DESC: v7 — Licitaciones vigentes + Config usuario + Cache análisis IA
-- ============================================================
-- AIDU OP · MIGRACIÓN 002 · v7 MVP
-- ============================================================

-- ============ LICITACIONES VIGENTES ============
-- Licitaciones publicadas que aún están abiertas a recibir ofertas.
-- Separada de mp_licitaciones_adj (que es histórico adjudicado).
-- Esta tabla se actualiza diariamente via GitHub Actions cron 7am.

CREATE TABLE IF NOT EXISTS mp_licitaciones_vigentes (
    codigo_externo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    descripcion TEXT,
    organismo TEXT,
    organismo_codigo TEXT,
    region TEXT,
    comuna TEXT,
    tipo TEXT,                                  -- L1, LE, LP
    fecha_publicacion TEXT,
    fecha_cierre TEXT,
    monto_referencial INTEGER,
    moneda TEXT DEFAULT 'CLP',
    estado TEXT DEFAULT 'publicada',
    tiene_bases_descargadas INTEGER DEFAULT 0,  -- 0=no, 1=sí (para v8)
    fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    raw_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_vig_fecha_cierre ON mp_licitaciones_vigentes(fecha_cierre);
CREATE INDEX IF NOT EXISTS idx_vig_region ON mp_licitaciones_vigentes(region);
CREATE INDEX IF NOT EXISTS idx_vig_tipo ON mp_licitaciones_vigentes(tipo);
CREATE INDEX IF NOT EXISTS idx_vig_organismo ON mp_licitaciones_vigentes(organismo);


-- ============ CONFIGURACIÓN DE USUARIO ============
-- Reemplaza todos los hardcoded de tarifa, sweet spot, regiones, etc.
-- Una sola fila por workspace (en fase 1: solo Ignacio).

CREATE TABLE IF NOT EXISTS config_usuario (
    id INTEGER PRIMARY KEY DEFAULT 1,
    
    -- Identidad
    nombre_completo TEXT DEFAULT 'Ignacio Vidiella González',
    rut TEXT DEFAULT '16.402.949-2',
    profesion TEXT DEFAULT 'Ingeniero Civil',
    empresa TEXT DEFAULT 'AIDU Op SpA',
    email_contacto TEXT,
    telefono TEXT,
    
    -- Economía
    tarifa_hora_clp INTEGER DEFAULT 78000,        -- 2 UF/hora
    overhead_pct REAL DEFAULT 18.0,
    margen_objetivo_pct REAL DEFAULT 22.0,
    margen_minimo_pct REAL DEFAULT 12.0,
    
    -- Sweet spot
    sweet_spot_min_clp INTEGER DEFAULT 3000000,
    sweet_spot_max_clp INTEGER DEFAULT 15000000,
    rango_aceptable_min_clp INTEGER DEFAULT 1500000,
    rango_aceptable_max_clp INTEGER DEFAULT 30000000,
    
    -- Filtros
    regiones_objetivo TEXT DEFAULT '["O''Higgins", "Metropolitana", "Maule", "Valparaíso"]',
    categorias_objetivo TEXT DEFAULT '["CE-01", "CE-02", "CE-03", "CE-04", "CE-05", "CE-06", "GP-01", "GP-02", "GP-03", "GP-04", "GP-05"]',
    mandantes_recurrentes TEXT DEFAULT '["I. Municipalidad de Machalí", "I. Municipalidad de Rancagua", "I. Municipalidad de Graneros"]',
    
    -- Pesos match score
    peso_categoria INTEGER DEFAULT 35,
    peso_region INTEGER DEFAULT 20,
    peso_monto INTEGER DEFAULT 20,
    peso_mandante INTEGER DEFAULT 10,
    peso_recencia INTEGER DEFAULT 15,
    
    -- Notificaciones
    email_notificaciones TEXT,
    notif_diario_habilitado INTEGER DEFAULT 1,
    notif_semanal_habilitado INTEGER DEFAULT 1,
    
    -- Storage
    google_drive_folder_id TEXT,
    
    fecha_modificacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Insertar fila default si no existe
INSERT OR IGNORE INTO config_usuario (id) VALUES (1);


-- ============ CACHE ANÁLISIS IA ============
-- Para v8: evitar re-analizar la misma base técnica 2 veces.
-- Hash del PDF como clave.

CREATE TABLE IF NOT EXISTS cache_analisis_ia (
    pdf_hash TEXT PRIMARY KEY,
    licitacion_codigo TEXT,
    tipo_analisis TEXT,                   -- 'bases', 'masivo', 'individual'
    resultado_json TEXT NOT NULL,
    tokens_input INTEGER,
    tokens_output INTEGER,
    costo_usd REAL,
    fecha_analisis TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_cache_licitacion ON cache_analisis_ia(licitacion_codigo);


-- ============ COST TRACKING CLAUDE API ============
-- Para v8: rastrear cuánto cuesta cada proyecto en términos de tokens.

CREATE TABLE IF NOT EXISTS cost_tracking_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER,
    tipo_operacion TEXT,                  -- 'analisis_individual', 'masivo', 'bases', 'reporte_semanal'
    modelo TEXT DEFAULT 'claude-sonnet-4-5',
    tokens_input INTEGER NOT NULL,
    tokens_output INTEGER NOT NULL,
    costo_usd REAL NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_cost_proyecto ON cost_tracking_ia(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_cost_fecha ON cost_tracking_ia(fecha);


-- ============ TRACKING DE TIEMPO REAL ============
-- Para v9: cronómetro embebido para registrar HH reales.

CREATE TABLE IF NOT EXISTS tiempo_dedicado (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    persona TEXT,                         -- 'Ignacio' | 'Jorella'
    fecha TEXT NOT NULL,
    minutos INTEGER NOT NULL,
    descripcion TEXT,
    fecha_registro TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_tiempo_proyecto ON tiempo_dedicado(proyecto_id);
CREATE INDEX IF NOT EXISTS idx_tiempo_fecha ON tiempo_dedicado(fecha);


-- ============ BASES TÉCNICAS (v8) ============
-- Almacenamiento de bases técnicas con texto extraído indexado.

CREATE TABLE IF NOT EXISTS mp_bases_tecnicas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    licitacion_codigo TEXT NOT NULL,
    nombre_archivo TEXT,
    url_original TEXT,
    drive_file_id TEXT,                   -- ID en Google Drive
    pdf_hash TEXT UNIQUE,                 -- SHA256 del contenido
    texto_extraido TEXT,                  -- Para búsqueda full-text
    n_paginas INTEGER,
    es_escaneado INTEGER DEFAULT 0,       -- 0=texto, 1=imagen (necesita OCR)
    tamano_bytes INTEGER,
    fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_bases_licitacion ON mp_bases_tecnicas(licitacion_codigo);
CREATE INDEX IF NOT EXISTS idx_bases_hash ON mp_bases_tecnicas(pdf_hash);
