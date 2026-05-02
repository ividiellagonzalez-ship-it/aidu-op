-- DESC: v13 — Ronda de consultas/respuestas + aspectos técnicos en proyectos
-- ============================================================
-- AIDU OP · MIGRACIÓN 004 · v13 CONSULTAS Y ASPECTOS TÉCNICOS
-- ============================================================

-- 1) Tabla de consultas formales que se publican en MP durante el período de consultas
CREATE TABLE IF NOT EXISTS proy_consultas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    fecha_pregunta TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    fecha_respuesta TEXT,
    pregunta TEXT NOT NULL,
    respuesta TEXT,
    publicada_en_mp INTEGER NOT NULL DEFAULT 0,
    autor TEXT,
    notas_internas TEXT,
    FOREIGN KEY (proyecto_id) REFERENCES aidu_proyectos(id)
);

CREATE INDEX IF NOT EXISTS idx_consultas_proyecto ON proy_consultas(proyecto_id);

-- 2) Aspectos técnicos en proyectos (extraídos automáticamente al pasar a Estudio)
ALTER TABLE aidu_proyectos ADD COLUMN metros_cuadrados INTEGER;
ALTER TABLE aidu_proyectos ADD COLUMN plazo_dias INTEGER;
ALTER TABLE aidu_proyectos ADD COLUMN n_entregables INTEGER;
ALTER TABLE aidu_proyectos ADD COLUMN tipo_servicio TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN complejidad TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN fecha_inicio_consultas TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN fecha_fin_consultas TEXT;

-- 3) Misma extensión en mp_licitaciones_adj (para enriquecer comparables)
ALTER TABLE mp_licitaciones_adj ADD COLUMN metros_cuadrados INTEGER;
ALTER TABLE mp_licitaciones_adj ADD COLUMN plazo_dias INTEGER;
ALTER TABLE mp_licitaciones_adj ADD COLUMN n_entregables INTEGER;
ALTER TABLE mp_licitaciones_adj ADD COLUMN tipo_servicio TEXT;
ALTER TABLE mp_licitaciones_adj ADD COLUMN complejidad TEXT;
