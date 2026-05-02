-- DESC: v14 — Reparadora: garantiza columnas técnicas existen (idempotente)
-- ============================================================
-- AIDU OP · MIGRACIÓN 005 · v14 REPARADORA
-- ============================================================
-- Esta migración es completamente idempotente: usa el patrón de migrator.py
-- que tolera "duplicate column name" como error no-fatal.
-- 
-- Existe porque migraciones previas (003, 004) pueden haber quedado parcialmente
-- aplicadas en producción si executescript abortó a mitad por una columna duplicada.

-- Columnas en aidu_proyectos (todas las que añadimos en 003 y 004)
ALTER TABLE aidu_proyectos ADD COLUMN url_mp TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN fecha_subida_mp TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN url_oferta_subida TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN metros_cuadrados INTEGER;
ALTER TABLE aidu_proyectos ADD COLUMN plazo_dias INTEGER;
ALTER TABLE aidu_proyectos ADD COLUMN n_entregables INTEGER;
ALTER TABLE aidu_proyectos ADD COLUMN tipo_servicio TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN complejidad TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN fecha_inicio_consultas TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN fecha_fin_consultas TEXT;

-- Columnas en mp_licitaciones_adj
ALTER TABLE mp_licitaciones_adj ADD COLUMN metros_cuadrados INTEGER;
ALTER TABLE mp_licitaciones_adj ADD COLUMN plazo_dias INTEGER;
ALTER TABLE mp_licitaciones_adj ADD COLUMN n_entregables INTEGER;
ALTER TABLE mp_licitaciones_adj ADD COLUMN tipo_servicio TEXT;
ALTER TABLE mp_licitaciones_adj ADD COLUMN complejidad TEXT;

-- Tabla consultas (idempotente con IF NOT EXISTS)
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
CREATE INDEX IF NOT EXISTS idx_proy_estado ON aidu_proyectos(estado);
CREATE INDEX IF NOT EXISTS idx_proy_fecha_cierre ON aidu_proyectos(fecha_cierre);

-- Renombrado defensivo de estados (por si alguno quedó con nombres viejos)
UPDATE aidu_proyectos SET estado = 'EN_CARTERA'  WHERE estado = 'PROSPECTO';
UPDATE aidu_proyectos SET estado = 'EN_ESTUDIO'  WHERE estado IN ('ESTUDIO', 'EN_PREPARACION');
UPDATE aidu_proyectos SET estado = 'EN_OFERTA'   WHERE estado = 'LISTO_OFERTAR';
UPDATE aidu_proyectos SET estado = 'LISTO_SUBIR' WHERE estado = 'OFERTADO';
UPDATE aidu_proyectos SET estado = 'ADJUDICADO' WHERE estado = 'ADJUDICADA';
UPDATE aidu_proyectos SET estado = 'PERDIDO'    WHERE estado IN ('RECHAZADA', 'PERDIDA');
