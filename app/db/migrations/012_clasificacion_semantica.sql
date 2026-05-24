-- DESC: S13.4.3 - Clasificacion semantica con Claude API + es_producto_granular
-- ============================================================
-- AIDU OP * MIGRACION 012 * S13.4.3
-- ============================================================
--
-- Tras la validacion visual del Director sobre el Excel de 685 items
-- (24/05/2026), se identifico que el clasificador lexical actual genera
-- ~33% de falsos positivos. Esta migracion agrega 3 columnas para
-- soportar clasificacion semantica con Claude API.
--
-- es_producto_granular es INTEGER. 1 marca producto con precio unitario
-- accionable. 0 marca contrato marco, obra, estudio o servicio sin grano
-- fisico. NULL marca items aun no clasificados semanticamente.
--
-- confidence_score es REAL entre 0.0 y 1.0. NULL si no se uso semantico.
--
-- clasificacion_metodo es TEXT con valores keyword, semantic, o manual.
--
-- + 2 indices para acelerar filtros UI por es_producto_granular y
-- por clasificacion_metodo.
--
-- Idempotente. ALTER TABLE ADD COLUMN es no-op si la columna existe
-- (error tolerado en migrator.py TOLERABLE_ERRORS).
--
-- Nota: comentarios NO contienen punto y coma porque _split_sql_statements
-- del migrator hace split simple por ese caracter y rompe.

ALTER TABLE inteligencia_precios ADD COLUMN es_producto_granular INTEGER;

ALTER TABLE inteligencia_precios ADD COLUMN confidence_score REAL;

ALTER TABLE inteligencia_precios ADD COLUMN clasificacion_metodo TEXT;

CREATE INDEX IF NOT EXISTS idx_ip_granular ON inteligencia_precios(es_producto_granular);

CREATE INDEX IF NOT EXISTS idx_ip_metodo ON inteligencia_precios(clasificacion_metodo);
