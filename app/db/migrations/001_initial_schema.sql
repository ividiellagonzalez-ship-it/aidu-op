-- DESC: Esquema inicial AIDU Op v1.0.0 - Cartera, histórico MP, aprendizaje
-- ============================================================
-- AIDU OP · MIGRACIÓN 001 · ESQUEMA INICIAL
-- ============================================================

-- ============ HISTÓRICO MERCADO PÚBLICO ============
-- Datos crudos de licitaciones adjudicadas descargadas del API.
-- Esta tabla NO se modifica por el usuario — es el "lago de datos".

CREATE TABLE IF NOT EXISTS mp_licitaciones_adj (
    codigo_externo TEXT PRIMARY KEY,           -- Ej: "2641-122-LE26"
    nombre TEXT NOT NULL,
    descripcion TEXT,
    organismo TEXT,
    organismo_codigo TEXT,
    region TEXT,
    comuna TEXT,
    tipo TEXT,                                  -- L1, LE, LP
    fecha_publicacion TEXT,
    fecha_cierre TEXT,
    fecha_adjudicacion TEXT,
    monto_referencial INTEGER,
    monto_adjudicado INTEGER,
    moneda TEXT DEFAULT 'CLP',
    n_oferentes INTEGER,
    proveedor_adjudicado TEXT,
    proveedor_rut TEXT,
    estado TEXT,
    pondera_precio_pct INTEGER,                 -- Extraído del campo evaluación
    raw_json TEXT,                              -- JSON completo del API por si necesitamos más campos
    fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_mp_organismo ON mp_licitaciones_adj(organismo);
CREATE INDEX IF NOT EXISTS idx_mp_region ON mp_licitaciones_adj(region);
CREATE INDEX IF NOT EXISTS idx_mp_fecha_adj ON mp_licitaciones_adj(fecha_adjudicacion);
CREATE INDEX IF NOT EXISTS idx_mp_tipo ON mp_licitaciones_adj(tipo);
CREATE INDEX IF NOT EXISTS idx_mp_proveedor_rut ON mp_licitaciones_adj(proveedor_rut);


-- ============ ÍTEMS DE LICITACIONES ============
-- Una licitación tiene N items con códigos UNSPSC.
-- Útil para matching más fino por categoría real adjudicada.

CREATE TABLE IF NOT EXISTS mp_licitacion_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_externo TEXT NOT NULL,
    item_numero INTEGER,
    nombre_producto TEXT,
    codigo_unspsc TEXT,
    cantidad REAL,
    unidad TEXT,
    monto_unitario INTEGER,
    monto_linea INTEGER,
    FOREIGN KEY (codigo_externo) REFERENCES mp_licitaciones_adj(codigo_externo)
);

CREATE INDEX IF NOT EXISTS idx_items_unspsc ON mp_licitacion_items(codigo_unspsc);
CREATE INDEX IF NOT EXISTS idx_items_codigo ON mp_licitacion_items(codigo_externo);


-- ============ CATEGORIZACIÓN AIDU ============
-- Mapeo entre licitaciones y categorías AIDU (CE-01, IA-02, etc.).
-- Una licitación puede caer en múltiples categorías (peso de match).

CREATE TABLE IF NOT EXISTS mp_categorizacion_aidu (
    codigo_externo TEXT NOT NULL,
    cod_servicio_aidu TEXT NOT NULL,            -- CE-01, GP-04, IA-02, etc.
    confianza REAL NOT NULL,                    -- 0.0 a 1.0
    metodo TEXT,                                -- 'keywords', 'unspsc', 'manual', 'claude'
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (codigo_externo, cod_servicio_aidu),
    FOREIGN KEY (codigo_externo) REFERENCES mp_licitaciones_adj(codigo_externo)
);

CREATE INDEX IF NOT EXISTS idx_cat_servicio ON mp_categorizacion_aidu(cod_servicio_aidu);


-- ============ KEYWORDS POR CATEGORÍA AIDU ============
-- Para matching TF-IDF / búsqueda. Editable por el usuario.

CREATE TABLE IF NOT EXISTS aidu_servicios_keywords (
    cod_servicio TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    keywords TEXT NOT NULL,                     -- separados por coma
    keywords_excluyentes TEXT,                  -- palabras que excluyen el match
    unspsc_codigos TEXT,                        -- códigos UNSPSC asociados
    hh_estimado_ignacio INTEGER NOT NULL,
    hh_estimado_jorella INTEGER NOT NULL,
    hh_real_promedio REAL,                      -- se actualiza con los cierres
    n_cierres INTEGER DEFAULT 0,
    desviacion_pct REAL,                        -- (real - estimado) / estimado * 100
    fecha_calibracion TEXT
);


-- ============ PROYECTOS DE AIDU (cartera del usuario) ============
-- La vida del proyecto desde que entra a cartera hasta el resultado.

CREATE TABLE IF NOT EXISTS aidu_proyectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_externo TEXT UNIQUE NOT NULL,        -- código MP
    nombre TEXT NOT NULL,
    descripcion TEXT,
    organismo TEXT,
    region TEXT,
    monto_referencial INTEGER,
    fecha_publicacion TEXT,
    fecha_cierre TEXT,
    cod_servicio_aidu TEXT,                     -- categoría AIDU asignada
    estado TEXT NOT NULL DEFAULT 'PROSPECTO',
        -- Estados: PROSPECTO | ESTUDIO | EN_PREPARACION | LISTO_OFERTAR
        --          OFERTADA  | EN_EVALUACION | ADJUDICADA | RECHAZADA
    hh_ignacio_estimado INTEGER,
    hh_jorella_estimado INTEGER,
    hh_ignacio_real INTEGER,                    -- post-cierre
    hh_jorella_real INTEGER,                    -- post-cierre
    escenario_elegido TEXT,                     -- agresivo | competitivo | premium
    precio_ofertado INTEGER,
    margen_pct REAL,
    probabilidad_estimada REAL,
    probabilidad_real REAL,                     -- 1.0 si ganó, 0.0 si perdió (post-resultado)
    proveedor_ganador TEXT,                     -- si perdió, RUT del que ganó
    monto_ganador INTEGER,
    paquete_generado INTEGER DEFAULT 0,         -- 0/1
    paquete_path TEXT,
    fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    fecha_modificacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    notas TEXT
);

CREATE INDEX IF NOT EXISTS idx_proy_estado ON aidu_proyectos(estado);
CREATE INDEX IF NOT EXISTS idx_proy_cierre ON aidu_proyectos(fecha_cierre);
CREATE INDEX IF NOT EXISTS idx_proy_servicio ON aidu_proyectos(cod_servicio_aidu);


-- ============ CHECKLIST DE PROYECTOS ============
CREATE TABLE IF NOT EXISTS aidu_checklist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    grupo TEXT,
    texto TEXT NOT NULL,
    requiere_estado TEXT,                       -- estado mínimo para activarla
    completado INTEGER DEFAULT 0,
    fecha_completado TEXT,
    orden INTEGER,
    FOREIGN KEY (proyecto_id) REFERENCES aidu_proyectos(id) ON DELETE CASCADE
);


-- ============ DOCUMENTOS DEL PROYECTO ============
CREATE TABLE IF NOT EXISTS aidu_documentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    nombre TEXT NOT NULL,
    tipo TEXT,                                   -- bases | borrador | final | anexo
    path_local TEXT,
    tamaño_bytes INTEGER,
    fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (proyecto_id) REFERENCES aidu_proyectos(id) ON DELETE CASCADE
);


-- ============ PROPUESTA TÉCNICA (secciones) ============
CREATE TABLE IF NOT EXISTS aidu_propuesta_secciones (
    proyecto_id INTEGER NOT NULL,
    seccion_id TEXT NOT NULL,
    contenido TEXT,
    fecha_modificacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    PRIMARY KEY (proyecto_id, seccion_id),
    FOREIGN KEY (proyecto_id) REFERENCES aidu_proyectos(id) ON DELETE CASCADE
);


-- ============ COMUNICACIONES Y BITÁCORA ============
CREATE TABLE IF NOT EXISTS aidu_comunicaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    tipo TEXT NOT NULL,                          -- consulta | respuesta | nota
    texto TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (proyecto_id) REFERENCES aidu_proyectos(id) ON DELETE CASCADE
);


-- ============ CHAT IA POR PROYECTO ============
CREATE TABLE IF NOT EXISTS aidu_chat_ia (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL,
    rol TEXT NOT NULL,                           -- user | assistant
    contenido TEXT NOT NULL,
    fecha TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    FOREIGN KEY (proyecto_id) REFERENCES aidu_proyectos(id) ON DELETE CASCADE
);


-- ============ APRENDIZAJE: CALIBRACIÓN TARIFARIO ============
-- Sugerencias del sistema basadas en cierres reales.

CREATE TABLE IF NOT EXISTS aidu_sugerencias_tarifario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cod_servicio TEXT NOT NULL,
    hh_estimado_actual INTEGER,
    hh_real_promedio REAL,
    desviacion_pct REAL,
    n_cierres_base INTEGER,
    sugerencia_hh INTEGER,
    estado TEXT NOT NULL DEFAULT 'PENDIENTE',    -- PENDIENTE | APROBADA | RECHAZADA
    fecha_creacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    fecha_resolucion TEXT
);


-- ============ INTELIGENCIA POR ORGANISMO ============
-- Vista materializada que se actualiza con cada batch de ingesta.

CREATE TABLE IF NOT EXISTS mp_organismos_perfil (
    organismo TEXT PRIMARY KEY,
    region TEXT,
    n_licitaciones_adj INTEGER,
    n_licitaciones_aidu INTEGER,
    monto_total_adj INTEGER,
    monto_promedio_adj INTEGER,
    descuento_promedio_pct REAL,
    descuento_mediana_pct REAL,
    oferentes_promedio REAL,
    proveedores_recurrentes TEXT,                -- JSON array
    pondera_precio_promedio_pct REAL,
    fecha_actualizacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);


-- ============ CONTROL DE INGESTA ============
-- Trazabilidad de qué fechas se han descargado del API.

CREATE TABLE IF NOT EXISTS mp_ingesta_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_consultada TEXT NOT NULL,
    n_licitaciones_descargadas INTEGER,
    n_nuevas INTEGER,
    n_actualizadas INTEGER,
    duracion_segundos REAL,
    estado TEXT,                                 -- OK | ERROR | PARCIAL
    error_msg TEXT,
    fecha_ejecucion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_ingesta_fecha ON mp_ingesta_log(fecha_consultada);


-- ============ PARÁMETROS DEL SISTEMA ============
-- Configuración runtime editable (UF, parámetros AIDU, etc.)

CREATE TABLE IF NOT EXISTS aidu_parametros (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL,
    descripcion TEXT,
    fecha_modificacion TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- Inserts iniciales
INSERT OR IGNORE INTO aidu_parametros (clave, valor, descripcion) VALUES
    ('uf_valor', '39000', 'Valor UF en pesos chilenos'),
    ('tarifa_hora_uf', '2', 'Tarifa por hora profesional en UF'),
    ('overhead_pct', '0.18', 'Overhead operacional en proporción'),
    ('region_base', 'O''Higgins', 'Región base de operación'),
    ('backfill_completado', '0', 'Bandera: backfill 24m completado'),
    ('ultima_ingesta', '', 'Fecha de última ingesta exitosa'),
    ('aprendizaje_min_cierres', '3', 'Mínimo de cierres para sugerir ajuste tarifario');


-- ============ Inserts iniciales: Tarifario AIDU ============
INSERT OR IGNORE INTO aidu_servicios_keywords (cod_servicio, nombre, keywords, hh_estimado_ignacio, hh_estimado_jorella) VALUES
    ('CE-01', 'Diagnóstico estructural', 'diagnóstico,estructural,patología,inspección,evaluación,sismo,grietas,deterioro,edificio', 40, 8),
    ('CE-02', 'Cálculo estructural', 'cálculo,estructural,memoria,planos,hormigón,acero,sismorresistente,fundaciones', 90, 10),
    ('CE-03', 'Asesoría estructural', 'asesoría,estructural,consulta,revisión,validación,técnica', 25, 8),
    ('CE-04', 'Coordinación especialidades', 'coordinación,especialidades,arquitectura,bim,proyectos,multidisciplinario', 60, 30),
    ('CE-05', 'Peritaje estructural', 'peritaje,estructural,daños,sismo,inspección,judicial,informe', 35, 5),
    ('CE-06', 'Apoyo SECPLAN', 'secplan,bases,técnicas,cubicación,especificaciones,municipal', 20, 15),
    ('GP-01', 'Gestión proyectos', 'gestión,proyectos,project,management,pmp,planificación,seguimiento', 80, 40),
    ('GP-02', 'Metodologías ágiles', 'ágil,agile,scrum,kanban,metodología,sprint,facilitación', 50, 30),
    ('GP-04', 'Levantamiento procesos', 'procesos,bpm,levantamiento,mapeo,rediseño,operacional,manual', 60, 50),
    ('GP-05', 'Diseño KPIs', 'kpi,indicadores,tablero,control,dashboard,gestión,medición', 40, 30),
    ('IA-01', 'Transformación digital IA', 'transformación,digital,inteligencia,artificial,automatización,modernización', 100, 50),
    ('IA-02', 'Análisis datos / dashboards', 'análisis,datos,dashboard,bi,visualización,power bi,tableau,reportería', 70, 30),
    ('IA-03', 'Desarrollo software', 'desarrollo,software,aplicación,sistema,programación,python,web', 100, 20),
    ('CAP-01', 'Capacitación digital', 'capacitación,curso,formación,e-learning,training,competencias,digitales', 35, 25);
