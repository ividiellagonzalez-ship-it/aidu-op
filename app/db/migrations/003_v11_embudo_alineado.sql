-- DESC: v11 — Alineación de estados al embudo conceptual + tabla licitaciones MP unificada
-- ============================================================
-- AIDU OP · MIGRACIÓN 003 · v11 EMBUDO ALINEADO
-- ============================================================

-- 1) RENOMBRAR ESTADOS para alinearlos con el embudo de 5 etapas
-- PROSPECTO       → EN_CARTERA      (etapa 2)
-- ESTUDIO         → EN_ESTUDIO      (etapa 3)
-- EN_PREPARACION  → EN_ESTUDIO      (consolidación: era duplicado)
-- LISTO_OFERTAR   → EN_OFERTA       (etapa 4)
-- OFERTADO        → LISTO_SUBIR     (etapa 5)
-- ADJUDICADO      = ADJUDICADO      (cerrado +)
-- PERDIDO         = PERDIDO         (cerrado -)
-- DESCARTADO      = DESCARTADO      (sin postular)

UPDATE aidu_proyectos SET estado = 'EN_CARTERA'  WHERE estado = 'PROSPECTO';
UPDATE aidu_proyectos SET estado = 'EN_ESTUDIO'  WHERE estado IN ('ESTUDIO', 'EN_PREPARACION');
UPDATE aidu_proyectos SET estado = 'EN_OFERTA'   WHERE estado = 'LISTO_OFERTAR';
UPDATE aidu_proyectos SET estado = 'LISTO_SUBIR' WHERE estado = 'OFERTADO';

-- 2) Agregar columnas útiles para conexión con MP
ALTER TABLE aidu_proyectos ADD COLUMN url_mp TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN fecha_subida_mp TEXT;
ALTER TABLE aidu_proyectos ADD COLUMN url_oferta_subida TEXT;

-- 3) Tabla licitaciones unificada (vigentes + adjudicadas, una sola fuente de verdad)
-- Permite tratar todas las licitaciones igual, con un campo 'estado_mp'

-- (Mantenemos las tablas existentes para compatibilidad, pero agregamos índice cruzado)

CREATE INDEX IF NOT EXISTS idx_proy_estado ON aidu_proyectos(estado);
CREATE INDEX IF NOT EXISTS idx_proy_fecha_cierre ON aidu_proyectos(fecha_cierre);

-- 4) Llenar url_mp para proyectos existentes
UPDATE aidu_proyectos 
SET url_mp = 'https://www.mercadopublico.cl/Procurement/Modules/RFB/DetailsAcquisition.aspx?qs=jKlGwXEUTC8orKEnYS8B/g==&idlicitacion=' || codigo_externo
WHERE url_mp IS NULL AND codigo_externo IS NOT NULL;
