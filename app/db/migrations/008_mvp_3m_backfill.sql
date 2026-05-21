-- DESC: S12.3 v2.2 - Columnas para backfill MVP CA+L1+LE con bitácora tipada
-- ============================================================
-- AIDU OP · MIGRACIÓN 008 · MVP backfill 3m
-- ============================================================
--
-- Soporta sprint S12.3 v2.2 MVP (commit feature/s12-3-v22-mvp-3m):
-- - Diferencia ítems SKU (producto, CA+L1) de headers de servicio (LE)
--   en la tabla unificada mp_licitaciones_items.
-- - Categoriza entradas en mp_ingesta_log por tipo+subtipo para que el
--   backfill (6 fases) pueda registrar su bitácora granular sin pisar
--   las entradas del cron diario.
--
-- Decisiones del Director (sprint S12.3 v2.2):
-- - D1 (precios): NO se denormaliza precio_unitario en mp_licitaciones_items.
--   El precio vive en mp_adjudicaciones.monto_unitario y se consulta vía JOIN.
-- - D2 (n_oferentes): ya existe en mp_licitaciones_adj (mig 001 línea 25)
--   por lo tanto NO se duplica en mp_adjudicaciones. El criterio #6 del MVP
--   apunta a mp_licitaciones_adj, no a mp_adjudicaciones.
-- - D5: mig única atómica con 3 ALTERs.

ALTER TABLE mp_licitaciones_items ADD COLUMN tipo_origen TEXT DEFAULT 'producto';

ALTER TABLE mp_ingesta_log ADD COLUMN tipo TEXT;

ALTER TABLE mp_ingesta_log ADD COLUMN subtipo TEXT;
