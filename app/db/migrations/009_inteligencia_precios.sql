-- DESC: S13 MVP Inteligencia de Mercado · O'Higgins · L1+LE+CO
-- ============================================================
-- AIDU OP · MIGRACION 009 · S13 MVP Inteligencia de Mercado
-- ============================================================
--
-- Soporta sprint S13 (branch feature/s13-inteligencia-mercado-ohiggins):
-- - Tabla plana materializada inteligencia_precios para alimentar el
--   buscador y los rankings de la pantalla Streamlit sin joins.
-- - Tabla organismos_ohiggins_auto para auto-discovery cuando el cron
--   detecta organismos O'Higgins no presentes en config/organismos_ohiggins.csv.
-- - ALTER aidu_servicios_keywords ADD COLUMN tipo: discrimina el catalogo
--   de AIDU Op (servicios CE/GP, tipo='aidu_op') del catalogo de AIDU Fast
--   (productos por linea, tipo='aidu_fast').
-- - ALTER mp_ingesta_log ADD COLUMN agil_endpoint_estado: side-fix del
--   bug silencioso AGIL/CA (hallazgo S13.0, ver docs/sprints/AIDU_Op_S13_1_
--   Restaurar_Compras_Agiles.md). Diferencia '0 nuevas por endpoint caido'
--   de '0 nuevas legitimas'.
-- - Seeds AIDU Fast: 4 rows (FAST-FERRETERIA, FAST-ASEO, FAST-OFICINA,
--   FAST-EQUIPAMIENTO) en aidu_servicios_keywords con tipo='aidu_fast'.
--   Fuente de verdad declarativa: config/keywords_aidu_fast.csv.
--
-- Decisiones del Director (cerradas durante reconnaissance S13):
-- - D1 (lineas Fast vs servicios Op): convivir, eje paralelo via columna 'tipo'.
-- - D2 (keywords en SQL): si, tabla aidu_servicios_keywords con discriminador.
-- - D3 (tabla plana vs view): tabla materializada por performance de filtros
--   en Streamlit.
-- - D4 (modulo nuevo): si, ingesta_inteligencia_precios.py, no toca v2.
-- - D5 (workflow separado): cron incremental aparte del descarga_mp_diaria.
-- - D7 (tipo_objeto): duplicar en inteligencia_precios con heuristica del spec
--   sec 3.3 (NO leer de mp_licitaciones_items.tipo_origen).
--
-- Hallazgos S13.0 que esta migracion atiende:
-- - A: AGIL endpoint devuelve 404 con ticket productivo. CA out-of-scope S13.
--      Side-fix de logging via columna agil_endpoint_estado.
-- - B: listado basico de adjudicadas solo trae 4 campos (sin Region).
--      Filtro O'Higgins requiere unit_code seed + auto-discovery.
--      organismos_ohiggins_auto soporta la parte auto.
-- - C: ~2160 estimados O'Higgins en 90d (5 dias utiles/semana). Capacidad
--      de la tabla y los indices ajustada.


-- ============================================================
-- 1. Tabla principal: inteligencia_precios (plana, sin joins)
-- ============================================================
-- Una fila = un item adjudicado dentro de una licitacion O'Higgins.
-- DEDUPE por (codigo_mp, correlativo_item) via UNIQUE.

CREATE TABLE IF NOT EXISTS inteligencia_precios (
    id_item              INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_mp            TEXT NOT NULL,
    correlativo_item     INTEGER NOT NULL,
    fecha_adjudicacion   TEXT,                      -- YYYY-MM-DD
    tipo_licitacion      TEXT NOT NULL,             -- L1 | LE | CO  (CA queda fuera S13.0 por hallazgo A)
    organismo_comprador  TEXT,
    unit_code            TEXT,                      -- primer segmento del codigo_externo
    organismo_region     TEXT,                      -- region raw del organismo
    region_entrega       TEXT,                      -- region declarada de entrega (filtro geografico 2)
    producto_descripcion TEXT,                      -- texto libre del item
    unidad_medida        TEXT,
    cantidad             REAL,
    precio_unitario      REAL,                      -- DATO ORO (puede ser NULL en L1 hasta ~36%)
    monto_total          REAL,                      -- precio_unitario * cantidad
    proveedor_nombre     TEXT,
    proveedor_rut        TEXT,
    n_oferentes          INTEGER,
    linea_aidu           TEXT NOT NULL,             -- Ferreteria | Aseo | Oficina | Equipamiento | Otros
    tipo_objeto          TEXT NOT NULL,             -- producto | servicio | hibrido
    keywords_matched     TEXT,                      -- lista coma-separada de keywords que dispararon la linea
    fecha_captura        TEXT NOT NULL DEFAULT (datetime('now')),
    lote_id              TEXT,                      -- 'backfill_1' | 'backfill_2' | ... | 'cron_diario' | 'cron_revision_7d'
    UNIQUE (codigo_mp, correlativo_item)
);

CREATE INDEX IF NOT EXISTS idx_ip_fecha_adj    ON inteligencia_precios(fecha_adjudicacion);
CREATE INDEX IF NOT EXISTS idx_ip_linea        ON inteligencia_precios(linea_aidu);
CREATE INDEX IF NOT EXISTS idx_ip_tipo_objeto  ON inteligencia_precios(tipo_objeto);
CREATE INDEX IF NOT EXISTS idx_ip_organismo    ON inteligencia_precios(organismo_comprador);
CREATE INDEX IF NOT EXISTS idx_ip_proveedor    ON inteligencia_precios(proveedor_rut);
CREATE INDEX IF NOT EXISTS idx_ip_unit_code    ON inteligencia_precios(unit_code);
CREATE INDEX IF NOT EXISTS idx_ip_lote         ON inteligencia_precios(lote_id);


-- ============================================================
-- 2. Tabla de auto-discovery de organismos O'Higgins
-- ============================================================
-- El CSV config/organismos_ohiggins.csv es el seed inicial (41 organismos
-- al cierre de S13.0). El cron diario detecta nuevos unit_codes cuya
-- region matchea O'Higgins/Libertador (con normalizacion U+00B4) y los
-- agrega aca para que el siguiente ciclo de descarga ya los incluya en
-- el filtro pre-detalle. Evita mantencion manual del CSV.

CREATE TABLE IF NOT EXISTS organismos_ohiggins_auto (
    unit_code           TEXT PRIMARY KEY,
    codigo_organismo    TEXT,
    nombre_organismo    TEXT NOT NULL,
    region_raw          TEXT NOT NULL,
    fecha_descubierto   TEXT NOT NULL DEFAULT (date('now')),
    primera_licitacion  TEXT                                -- codigo_externo del descubrimiento
);

CREATE INDEX IF NOT EXISTS idx_org_auto_fecha ON organismos_ohiggins_auto(fecha_descubierto);


-- ============================================================
-- 3. ALTER aidu_servicios_keywords: agregar discriminador tipo
-- ============================================================
-- Default 'aidu_op' preserva semantica de filas existentes (CE-01..06,
-- GP-01..05, IA-01..03, CAP-01). Nuevas filas tipo='aidu_fast'.

ALTER TABLE aidu_servicios_keywords ADD COLUMN tipo TEXT DEFAULT 'aidu_op';

CREATE INDEX IF NOT EXISTS idx_keywords_tipo ON aidu_servicios_keywords(tipo);


-- ============================================================
-- 4. ALTER mp_ingesta_log: agil_endpoint_estado (side-fix S13.0)
-- ============================================================
-- Valores: 'ok' | 'caido_404' | 'error_otro' | 'no_consultado'
-- Default 'ok' preserva semantica de filas previas (asumimos OK retroactivo;
-- no podemos auditar historial de AGIL 404 silencioso, ese es scope de S13.1).

ALTER TABLE mp_ingesta_log ADD COLUMN agil_endpoint_estado TEXT DEFAULT 'ok';


-- ============================================================
-- 5. Seeds AIDU Fast keywords (4 lineas)
-- ============================================================
-- Fuente de verdad: config/keywords_aidu_fast.csv (linea,keyword,activo).
-- La SQL aca duplica ese contenido para que la migracion sea autocontenida.
-- Updates futuros: modificar el CSV + nueva migracion 010 con DELETE+INSERT
-- (o INSERT OR REPLACE) del tipo='aidu_fast'.
-- Conteo target: >=20 keywords por linea (spec sec 3.1). Realidad: 30-40
-- por linea, ya cubre el threshold con margen.

INSERT OR IGNORE INTO aidu_servicios_keywords
    (cod_servicio, nombre, keywords, hh_estimado_ignacio, hh_estimado_jorella, tipo)
VALUES
    (
        'FAST-FERRETERIA',
        'Ferreteria y Construccion (AIDU Fast)',
        'cemento,hormigon,fierro,acero,perfil,clavo,tornillo,tuerca,perno,alambre,martillo,taladro,sierra,llave,destornillador,pintura,brocha,rodillo,madera,tabla,ladrillo,bloque,fragüe,yeso,malla,cable,enchufe,interruptor,tuberia,fitting,codo,cañeria,valvula,manguera,herramienta,andamio,escalera,casco,guante,bota,cinta metrica,carretilla,saco arena,gravilla,bisagra,candado,silicona,sellador,pegamento construccion',
        0, 0,
        'aidu_fast'
    ),
    (
        'FAST-ASEO',
        'Aseo (AIDU Fast)',
        'detergente,jabon,cloro,desinfectante,limpiador,escobillon,escoba,trapero,mopa,paño,papel higienico,toalla,servilleta,bolsa basura,dispensador,sanitizante,alcohol gel,lavaloza,suavizante,cera,lustramuebles,ambientador,desodorante,insecticida,desratizador,balde,esponja,guante latex,mascarilla,papel toalla,contenedor,pala,sopapo,limpia vidrios,antibacterial,desincrustante,virutilla,detergente liquido,toalla nova,bolsa basura,bolsa basura industrial',
        0, 0,
        'aidu_fast'
    ),
    (
        'FAST-OFICINA',
        'Oficina (AIDU Fast)',
        'papel,resma,hoja,cuaderno,libreta,lapiz,lapicera,boligrafo,plumon,marcador,corrector,goma,sacapunta,regla,tijera,pegamento,cinta adhesiva,archivador,carpeta,separador,folder,sobre,etiqueta,post-it,perforadora,corchetera,corchete,clip,chinche,cartulina,block,agenda,calendario,tinta,toner,cartucho,resaltador,libro acta,papeleria,utiles escritorio',
        0, 0,
        'aidu_fast'
    ),
    (
        'FAST-EQUIPAMIENTO',
        'Equipamiento (AIDU Fast)',
        'computador,notebook,laptop,monitor,teclado,mouse,impresora,escaner,proyector,pantalla,escritorio,silla,mesa,estante,mueble,archivador metalico,lockers,refrigerador,microondas,hervidor,cafetera,ventilador,calefactor,aire acondicionado,televisor,telefono,central telefonica,ups,regulador,switch,router,disco duro,memoria ram,procesador,tablet,kardex,estanteria,mueble oficina',
        0, 0,
        'aidu_fast'
    );


-- ============================================================
-- 6. Seed organismos_ohiggins_auto: vacio (el CSV cubre el inicio)
-- ============================================================
-- Esta tabla arranca vacia. El cron diario la pobla durante operacion
-- normal cuando detecta un unit_code O'Higgins fuera del CSV semilla.
-- El SELECT de organismos validos en el ingestor es:
--   (unit_codes del CSV) UNION (unit_codes de organismos_ohiggins_auto).
