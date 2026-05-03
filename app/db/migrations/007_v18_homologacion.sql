-- v18 sprint 10. Tabla maestra de homologacion AIDU.
-- Permite editar HH, plazo, entregables y aplicabilidad m2 por categoria CE/GP.
-- Tambien tabla aidu_indicadores_extraidos para guardar valores extraidos por licitacion.

CREATE TABLE IF NOT EXISTS aidu_homologacion_categoria (
    cod_servicio_aidu TEXT PRIMARY KEY,
    nombre_servicio TEXT NOT NULL,
    linea TEXT,
    hh_tipicas INTEGER DEFAULT 80,
    plazo_dias_tipico INTEGER DEFAULT 30,
    entregables_tipicos TEXT,
    aplica_m2 INTEGER DEFAULT 0,
    m2_referencia INTEGER DEFAULT 0,
    notas TEXT,
    fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS aidu_indicadores_extraidos (
    codigo_externo TEXT PRIMARY KEY,
    plazo_dias INTEGER,
    plazo_fuente TEXT,
    metros_cuadrados INTEGER,
    m2_fuente TEXT,
    n_entregables INTEGER,
    entregables_lista TEXT,
    entregables_fuente TEXT,
    hh_estimadas_aidu INTEGER,
    hh_fuente TEXT,
    fecha_extraccion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_indicadores_codigo ON aidu_indicadores_extraidos(codigo_externo);
