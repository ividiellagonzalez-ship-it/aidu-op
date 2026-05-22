# Changelog AIDU Op

Registro cronológico de sprints técnicos desde S12. Para sprints previos
ver `docs/sprints/` (notas individuales por sprint) y el log de git.

## S13-fix — Migración Turso explícita + lotes cortos (2026-05)

**Branch**: `fix/s13-migracion-turso-y-lotes-cortos`. **Estado**: PR pendiente.
**Origen**: el primer dispatch de S13 (Lote 1, 22 días) crasheó a los 12m 58s con
`TursoUnavailableError: no such table: inteligencia_precios`. La migración 009
había quedado aplicada solo en SQLite local, NO en Turso productivo.

### Causa raíz

`run_migrations()` aplica DDL idempotente a SQLite local Y a Turso vía
`/v2/pipeline` cuando hay credenciales. Pero **ningún workflow lo invoca
explícitamente**: `descarga_mp_diaria.yml` corre `python -m app.core.descarga_diaria`
directo, asumiendo que el schema ya está aplicado. La asunción se cumplía
históricamente porque Streamlit Cloud cold-start ejecuta `_ensure_migrations_applied()`
y poblaba Turso para las migraciones nuevas. Para los workflows S13, el dispatch
manual del backfill puede correr ANTES de cualquier cold-start del UI → la
migración 009 nunca llegó a Turso.

### Cambios por archivo

- **`.github/workflows/inteligencia_backfill_lote.yml`** (modificado):
  - Step nuevo `Aplicar migraciones a Turso (FIX S13)` antes del pre-flight.
    Llama `run_migrations()` con `TURSO_*` env vars. Idempotente: si ya
    aplicadas, no-op silencioso.
  - Defaults de los inputs actualizados al nuevo Lote 1 (7 días).
  - `timeout-minutes: 350` → `60` (los lotes ahora son chicos).
  - Header doc rewrite con tabla de 12 lotes.

- **`.github/workflows/inteligencia_adjudicadas_diaria.yml`** (modificado):
  - Mismo step de migraciones aplicado al cron diario, por consistencia.
    El CLI ya tiene su propio guard, pero el step explícito acorta el
    blast-radius de fallos silenciosos.

- **`scripts/cargar_inteligencia_ohiggins.py`** (modificado):
  - `_verificar_o_aplicar_migraciones()`: nuevo guard que consulta
    `sqlite_master` en Turso, verifica que existen `inteligencia_precios`
    y `organismos_ohiggins_auto`, intenta `run_migrations()` si faltan,
    y aborta con exit 2 si tras eso siguen faltando.
  - Llamado en `main()` justo después de validar `MP_TICKET`.
  - Soporta el modo `--dry-run`: si todo OK, el dry-run reporta también
    que las tablas críticas están presentes.

- **`docs/changelog.md`** (esta entrada).

### Esquema revisado de lotes: 4×22d → 12×7-8d

Razones para el cambio:
- Si un lote falla, perdemos ~10-15 min en vez de ~3.5h.
- 12 checkpoints naturales de validación operacional.
- Mismo total de trabajo (cuota GH Actions ≤ 14h).
- Recuperación de un lote fallido es trivial (re-dispatch en ~minutos).

Distribución alternada 7/8 días (90 días totales, contiguos, sin gap ni overlap):

| # | Días | Fecha desde | Fecha hasta |
|---|------|-------------|-------------|
| 1  | 7 | 2026-05-15 | 2026-05-21 |
| 2  | 8 | 2026-05-07 | 2026-05-14 |
| 3  | 7 | 2026-04-30 | 2026-05-06 |
| 4  | 8 | 2026-04-22 | 2026-04-29 |
| 5  | 7 | 2026-04-15 | 2026-04-21 |
| 6  | 8 | 2026-04-07 | 2026-04-14 |
| 7  | 7 | 2026-03-31 | 2026-04-06 |
| 8  | 8 | 2026-03-23 | 2026-03-30 |
| 9  | 7 | 2026-03-16 | 2026-03-22 |
| 10 | 8 | 2026-03-08 | 2026-03-15 |
| 11 | 7 | 2026-03-01 | 2026-03-07 |
| 12 | 8 | 2026-02-21 | 2026-02-28 |

**Total: 90 días.** El Director dispara los 12 lotes en serie (mismo día está OK),
validando cada uno antes de pasar al siguiente.

### Re-dispatch del Lote 1 (post-merge de S13-fix)

```bash
gh workflow run inteligencia_backfill_lote.yml \
  --ref main \
  -f lote_id=backfill_1 \
  -f fecha_desde=2026-05-15 \
  -f fecha_hasta=2026-05-21 \
  -f progress_every=100
```

Idempotente: si quedaron filas de un intento previo del Lote 1 con la fecha
range vieja (22d), no hay conflicto — el rango cambió y la UNIQUE en
`(codigo_mp, correlativo_item)` previene duplicados.

---

## S13 — MVP Inteligencia de Mercado · O'Higgins (2026-05)

**Branch**: `feature/s13-inteligencia-mercado-ohiggins`. **Estado**: PR pendiente.
**Cliente del sprint**: AIDU Fast (B2G productos < 1000 UTM).
**Plan**: `Downloads/AIDU_Op_S13_MVP_Inteligencia_Ohiggins.docx` (entrega del Director).
**Sprint paralelo originado**: `docs/sprints/AIDU_Op_S13_1_Restaurar_Compras_Agiles.md`.

### Filosofía

Cerrar la brecha entre infraestructura técnica (S12.x) y negocio. Una sola
pregunta operacional: ¿a qué precio se han adjudicado productos similares
en O'Higgins en los últimos 90 días? Tabla plana materializada, categorización
por keywords simples, sin Claude API en este sprint (el algoritmo avanzado
queda para S14).

### Decisiones del Director (cerradas durante reconnaissance S13)

| ID | Decisión | Aplicada |
|----|----------|----------|
| D1 | Convivencia: nuevo eje `linea_aidu_fast` paralelo a CE/GP servicios. NO reemplaza. | ✓ |
| D2 | Keywords en `aidu_servicios_keywords` con discriminador `tipo='aidu_fast'`. ALTER agrega la columna. | ✓ |
| D3 | Tabla plana materializada `inteligencia_precios` (no view). | ✓ |
| D4 | Módulo nuevo `ingesta_inteligencia_precios.py`. NO toca `inteligencia_precios_v2.py`. | ✓ |
| D5 | Workflow separado `inteligencia_adjudicadas_diaria.yml`. NO suma step al cron principal. | ✓ |
| D6 | Backfill vía GH Actions, **4 lotes de 22 días** (no 3×30 — 3.5h/lote con buffer de 2.5h sobre límite hard de 6h). | ✓ |
| D7 | `tipo_objeto` en `inteligencia_precios` con heurística del spec sec 3.3. NO leer de `mp_licitaciones_items.tipo_origen`. | ✓ |
| OK-A | Aceptar ~36% NULL en `monto_unitario` para L1 (impacto neto ~15% global). | ✓ |
| OK-B | Lotes de 22 días × 4 dispatches manuales (lote 1 = más reciente primero). | ✓ |
| OK-C | Ingestor dedupe **por unit_code, NO por nombre_organismo** (misma comuna tiene múltiples unidades de compra). Comentario explícito en código. | ✓ |
| OK-3 mod | CSV de organismos generado automáticamente vía sampling 7d + auto-discovery por cron (tabla `organismos_ohiggins_auto`). | ✓ |
| OK-4 mod | Spike S13.0a previo determinó **escenario (b)**: AGIL endpoint caído. CA fuera de scope S13, agendado en S13.1. | ✓ |

### Hallazgos del reconnaissance (S13.0)

**Hallazgo A — Endpoint AGIL devuelve HTTP 404.** Spike `scripts/diagnostics/_recon_agil_check.py`
probó 5 variantes de URL × 3 formatos de fecha = 15 combinaciones con ticket
productivo: 15/15 → HTTP 404. Sanity check del endpoint principal con mismo ticket =
HTTP 200 (337 adjudicadas el 2026-05-19). Conclusión: endpoint AGIL fue
eliminado o movido. CA queda fuera de S13; trabajo agendado como sprint
independiente S13.1 (ver `docs/sprints/AIDU_Op_S13_1_Restaurar_Compras_Agiles.md`).
**Side-fix incluido en este PR**: `_request_agil` clasifica HTTP 404 explícitamente
y persiste en `mp_ingesta_log.agil_endpoint_estado` para que el bug deje de ser
silencioso.

**Hallazgo B — Listado básico de `/licitaciones.json?estado=adjudicada` solo trae
4 campos** (CodigoExterno, Nombre, CodigoEstado, FechaCierre). NO trae Region/Tipo.
Para filtrar por O'Higgins hay que pegar `detalle_licitacion()` de cada licitación
nacional: 90 días × 300/día × 25 req/min = ~15 horas como filtro ingenuo.
**Mitigación**: filtro pre-detalle por `unit_code` (primer segmento del
CodigoExterno) usando `config/organismos_ohiggins.csv` (41 organismos al cierre
de S13.0) + auto-discovery en cron diario (25 codigos no-seed/día) que pueblan
`organismos_ohiggins_auto`. Reduce ~27k → ~2k requests para el backfill 90 días.

**Hallazgo C — La API usa U+00B4 (´ ACUTE ACCENT) como apóstrofe en
`Region`**, no U+0027 (') ASCII ni U+2019 (') smart quote. Inspección de
codepoints: `'Region del Libertador General Bernardo O´Higgins'` ← U+00B4.
**Mitigación**: `categorizador_aidu_fast.normalizar_texto` reemplaza U+00B4,
U+2019, U+2018, U+0060 → U+0027 antes de comparar. Aplicado al matcher de
región y a la búsqueda de keywords. Side-fix también para `MP_REGION_TO_CODE`
en `app/core/catalogo_aidu.py` (TODO: este side-fix queda para S13.x; el
matcher actual `filtrar_por_region` usa substring case-insensitive, no exact
match, y por eso no había bloqueado producción).

**Hallazgo lateral — TD-01**: tercera vez que aparece el bug `cp1252
UnicodeEncodeError` en scripts CLI Windows. Agendado en `docs/tech_debt.md`
TD-01: crear `app/utils/console.py` con `setup_utf8_console()` reutilizable.
Out of scope S13.

### Cambios por archivo

- **`app/db/migrations/009_inteligencia_precios.sql`** (nuevo):
  - `CREATE TABLE inteligencia_precios` (22 columnas, UNIQUE en
    `(codigo_mp, correlativo_item)`, 7 índices).
  - `CREATE TABLE organismos_ohiggins_auto` (auto-discovery por cron).
  - `ALTER TABLE aidu_servicios_keywords ADD COLUMN tipo TEXT DEFAULT 'aidu_op'`
    (discrimina filas Op vs Fast).
  - `ALTER TABLE mp_ingesta_log ADD COLUMN agil_endpoint_estado TEXT
    DEFAULT 'ok'` (side-fix hallazgo A).
  - Seeds: 4 filas en `aidu_servicios_keywords` con `tipo='aidu_fast'`
    (FAST-FERRETERIA, FAST-ASEO, FAST-OFICINA, FAST-EQUIPAMIENTO),
    ≥20 keywords cada una.

- **`config/keywords_aidu_fast.csv`** (nuevo, 168 filas):
  source-of-truth declarativa de las keywords (`linea,keyword,activo`).
  Mismas keywords que la migración 009. Si se actualiza el CSV, futura
  migración 010 hará `DELETE+INSERT WHERE tipo='aidu_fast'`.

- **`config/organismos_ohiggins.csv`** (nuevo, 41 filas):
  seed inicial generado por `scripts/_seed_organismos_ohiggins.py` con
  sampling de 7 días × 250 detalles/día. Calidad 100% en los 4 campos.
  Auto-discovery del cron diario lo expandirá durante operación.

- **`app/api/mercadopublico.py`** (modificado, side-fix S13.0 hallazgo A):
  - Constantes `AGIL_OK | AGIL_DOWN_404 | AGIL_ERROR_OTRO | AGIL_NO_CONSULTADO`.
  - Attribute `self.last_agil_status` actualizado en cada exit path de
    `_request_agil`.
  - HTTP 404 ahora marca `AGIL_DOWN_404` con WARNING explícito que
    referencia S13.1 (en vez de WARNING genérico).
  - HTTP 200 con 0 resultados → INFO (no error).
  - HTTP 401/403/5xx/timeout/network → `AGIL_ERROR_OTRO` con ERROR.

- **`app/core/descarga_diaria.py`** (modificado, side-fix S13.0 hallazgo A):
  - Lee `cliente.last_agil_status` post-llamada AGIL.
  - Propaga `agil_endpoint_estado` a `_ejecutar_via_http` y de ahí a
    `_insert_ingesta_log`.
  - `_insert_ingesta_log` agrega el campo al INSERT.

- **`app/core/categorizador_aidu_fast.py`** (nuevo, 230 líneas):
  - `normalizar_texto`, `normalizar_region`, `es_ohiggins`.
  - `categorizar_linea(descripcion)` → `(linea, keywords_matched)`.
    Substring match insensible a acentos. Spec sec 3.2.
  - `categorizar_tipo_objeto(descripcion)` → `'producto'|'servicio'|'hibrido'`.
    Heurística del spec sec 3.3.
  - Cache del catálogo + `reset_cache()` para tests.
  - Carga desde tabla SQL (runtime) o CSV (tests).

- **`app/core/ingesta_inteligencia_precios.py`** (nuevo, ~450 líneas):
  - `cargar_unit_codes_validos()` = CSV semilla ∪ `organismos_ohiggins_auto`.
  - `_filtrar_listado` → matched + sample_discovery.
  - `expandir_items(detalle)` → lista de items normalizados.
  - `categorizar_item` envuelve el categorizador.
  - `persistir_lote` con batches de 50 statements vía `turso_http_client.execute_pipeline`,
    `INSERT OR IGNORE` por `UNIQUE (codigo_mp, correlativo_item)`.
  - `persistir_descubrimientos` agrega a `organismos_ohiggins_auto`.
  - `ingerir_rango(fecha_desde, fecha_hasta, lote_id, discovery_sample_size,
    progress_callback, progress_every)` orquesta el pipeline.
  - Stats devueltos en `StatsCorrida` dataclass.

- **`scripts/cargar_inteligencia_ohiggins.py`** (nuevo CLI):
  argparse: `--fecha-desde --fecha-hasta --lote-id --discovery-sample-size
  --progress-every --batch-size --verbose --dry-run`. Imprime `[PROGRESO]`
  cada N detalles con eta calculado por proporción de días procesados.
  Exit codes 0/1/2/3. UTF-8 wrapper aplicado (TD-01 ad-hoc).

- **`.github/workflows/inteligencia_backfill_lote.yml`** (nuevo):
  `workflow_dispatch` con inputs `lote_id, fecha_desde, fecha_hasta,
  progress_every`. Pre-flight dry-run + ejecución + reporte de conteo
  post-backfill. `timeout-minutes: 350` (10 min buffer sobre límite GH 360).

- **`.github/workflows/inteligencia_adjudicadas_diaria.yml`** (nuevo):
  cron `0 14 * * *` (post descarga principal de 10:00 UTC) + `workflow_dispatch`.
  Ventana hoy-7 .. ayer. `discovery-sample-size 25` para descubrimiento orgánico.

- **`app/ui/inteligencia_mercado.py`** (nuevo, ~280 líneas):
  - Tab "Buscador de precios": text input + filtros (línea AIDU, tipo
    objeto, organismo, proveedor, rango precio) + stats (n, mediana,
    p25/p75, min/max) + top 5 proveedores + tabla resultados (limit 500)
    + export XLSX.
  - Tab "Productos más comprados": ranking top 50 agrupado por
    `producto_descripcion lowercase[:80]`, columnas (producto, monto_total,
    cantidad, frecuencia, top 3 organismos, proveedor dominante), filtro
    línea, export XLSX.
  - Cache `@st.cache_data(ttl=300)`.

- **`app/ui/streamlit_app.py`** (modificado):
  - Nueva opción `"🛒 Inteligencia de Mercado"` en `NAV_OPCIONES`.
  - Tab flag `tab_intel_mercado` + branch `if tab_intel_mercado:`
    que importa y llama `render_inteligencia_mercado()`.

- **`tests/test_categorizador_aidu_fast.py`** (nuevo, 51 tests):
  - 4 lineas × ≥25 casos = ≥100 casos. Acierto ≥80% por línea (spec sec 4.3).
  - tipo_objeto: 22 casos producto/servicio/hibrido (spec exige ≥15).
  - Normalización Unicode (incluye U+00B4 hallazgo C).
  - es_ohiggins con todas las variantes observadas en API.

- **`tests/test_ingesta_inteligencia_precios.py`** (nuevo, 24 tests):
  - `extraer_unit_code` con 6 inputs.
  - `_filtrar_listado` filtro + discovery sampling + dedupe (misma comuna,
    2 unit_codes distintos → ambos pasan).
  - `expandir_items` con shapes reales de la API (1 item, multi-item,
    NULL en MontoUnitario).
  - Idempotencia: SQL emitido es `INSERT OR IGNORE`, UNIQUE en migración,
    `persistir_lote` envia batches correctos (mock execute_pipeline).
  - TIPOS_SCOPE excluye CA (documenta S13.1).

- **`docs/sprints/AIDU_Op_S13_1_Restaurar_Compras_Agiles.md`** (nuevo):
  sprint independiente, BLOQUEADO pendiente investigación nuevo endpoint MP.
  Reproductor: `scripts/diagnostics/_recon_agil_check.py`.

- **`docs/tech_debt.md`** (nuevo): registro plano de deuda técnica. TD-01
  agendado: `app/utils/console.py` con `setup_utf8_console()`.

- **`scripts/diagnostics/_recon_agil_check.py`** (nuevo, NO mergear a main):
  spike S13.0a, queda en feature branch como reproductor del bug S13.1.

- **`scripts/_seed_organismos_ohiggins.py`** (nuevo, NO mergear a main):
  generador del CSV semilla. Usado para producir
  `config/organismos_ohiggins.csv`. UTF-8 wrapper + checkpoint cada 50
  detalles + persist-before-print.

### Criterios técnicos del MVP

| # | Criterio | Validación |
|---|----------|------------|
| 1 | Carga inicial 90d ejecutada sin errores | 4 dispatches `inteligencia_backfill_lote.yml` con exit 0 |
| 2 | `inteligencia_precios` poblada ≥ 2.000 filas | `SELECT COUNT(*) FROM inteligencia_precios` post-lote 4 |
| 3 | Cobertura categorización línea AIDU ≥ 70% no-Otros | `SELECT COUNT(*) WHERE linea_aidu != 'Otros'` / total |
| 4 | Cobertura tipo_objeto 100% asignado | `SELECT COUNT(*) WHERE tipo_objeto IS NULL` = 0 |
| 5 | Pantalla Streamlit funcional | Smoke test manual del Director post-merge |
| 6 | Tab Productos más comprados | Smoke test manual: ranking ordenado descendente por monto_total |
| 7 | Export Excel | Click → archivo .xlsx descarga + abre en Excel |
| 8 | Cron diario `inteligencia_adjudicadas_diaria.yml` | Trigger manual exit 0 |
| 9 | Re-revisión 7 días captura nuevas | `SELECT MAX(fecha_adjudicacion) FROM inteligencia_precios WHERE lote_id='cron_revision_7d'` |
| 10 | Suite tests verde | `pytest tests/` 205/205 PASS (130 previos + 75 nuevos) |

### Re-dispatch policy (cómo re-disparar un lote fallido)

Si un lote del workflow `inteligencia_backfill_lote.yml` falla a mitad:

1. Inspeccionar el último `[PROGRESO]` en el job log para identificar el
   día más reciente procesado y los nuevos en Turso.
2. Volver a disparar el workflow con **los mismos** `lote_id`, `fecha_desde`,
   `fecha_hasta`. La UNIQUE constraint en `(codigo_mp, correlativo_item)`
   + `INSERT OR IGNORE` garantiza idempotencia: no se duplican filas.
3. Verificar post-dispatch:
   ```sql
   SELECT COUNT(*) FROM inteligencia_precios
   WHERE fecha_adjudicacion >= '{fecha_desde}'
     AND fecha_adjudicacion <= '{fecha_hasta}';
   ```
   El conteo debe estabilizarse entre runs sucesivos (lo que entró ya
   no vuelve a entrar).

### Orden de ejecución del backfill (Director)

```
Lote 1: 2026-04-30 → 2026-05-21  (más reciente, descubrir bugs primero)
Lote 2: 2026-04-08 → 2026-04-29
Lote 3: 2026-03-17 → 2026-04-07
Lote 4: 2026-02-22 → 2026-03-16
```

Comando de dispatch (desde UI o `gh` CLI):

```bash
gh workflow run inteligencia_backfill_lote.yml \
  -f lote_id=backfill_1 \
  -f fecha_desde=2026-04-30 \
  -f fecha_hasta=2026-05-21 \
  -f progress_every=100
```

Validar lote 1 con éxito ANTES de disparar lote 2 (regla del Director).

---

## S12.3 v2.2 — Backfill MVP 3m × 5 regiones × CA+L1+LE (2026-05)

**Branch**: `feature/s12-3-v22-mvp-3m`. **Estado**: PR pendiente de merge.
**Plan**: `docs/sprints/AIDU_Op_S12_3_v22_MVP_3m.docx` (copia commiteada).

### Filosofía

MVP de validación: ventana acotada (3 meses, 5 regiones target) para
validar que la herramienta funciona end-to-end ANTES de comprometer
5-9 horas en descargas más amplias (S12.3.1 = 6m, S12.3.2 = 12m).
Mismo principio que S12.1 (migrar Turso antes de poblar) y S12.2
(cron diario antes de backfill).

### Decisiones del Director (cerradas durante reconnaissance)

| ID | Decisión | Aplicada |
|---|---|---|
| D1 | Precios via JOIN con `mp_adjudicaciones.monto_unitario`, NO denormalizar en `mp_licitaciones_items`. | ✓ |
| D2 | `n_oferentes` ya existe en `mp_licitaciones_adj` (mig 001 línea 25). Criterio #6 apunta a esa tabla, NO a `mp_adjudicaciones`. | ✓ |
| D3 | Extender `app/api/mercadopublico.py` con helpers de filtrado, NO crear `ocds_client_extendido.py`. | ✓ |
| D4 | Agregar `tipo + subtipo` a `mp_ingesta_log` para bitácora granular del backfill. | ✓ |
| D5 | Una sola migración 008 atómica con los ALTERs. | ✓ |
| D-arq | Wrapper fino sobre `descarga_historica.py` con refactor mínimo backward-compatible. | ✓ |

### Cambios por archivo

- **`app/db/migrations/008_mvp_3m_backfill.sql`** (nuevo, 3 ALTERs):
  - `mp_licitaciones_items ADD COLUMN tipo_origen TEXT DEFAULT 'producto'`
  - `mp_ingesta_log ADD COLUMN tipo TEXT`
  - `mp_ingesta_log ADD COLUMN subtipo TEXT`

- **`app/db/migrator.py`**: `_auto_reparar_schema` agrega entradas para
  `mp_licitaciones_items.tipo_origen` y `mp_ingesta_log.{tipo,subtipo}`
  como respaldo idempotente (mismo patrón que el resto de la función).

- **`app/api/mercadopublico.py`**: helpers nuevos de filtrado post-fetch
  para que el script de backfill MVP filtre los resultados del endpoint
  v1 sin duplicar lógica:
  - `TIPOS_VALIDOS` (set canónico) + alias `'CA' → 'AGIL'`.
  - `filtrar_por_tipo(licitaciones, tipos)`.
  - `filtrar_por_region(licitaciones, nombres_region)` con match por
    substring case-insensitive (tolera "Región Metropolitana de Santiago"
    vs "Metropolitana").

- **`app/core/descarga_historica.py`** — refactor backward-compatible:
  - `_persistir_licitaciones(..., use_http_client=False)`: nuevo
    parámetro opcional. Default `False` preserva el comportamiento previo
    (path SQLite via `migrator.get_connection()`). `True` dispatcha a
    `_persistir_licitaciones_http`.
  - `_persistir_licitaciones_http(licitaciones_raw, tabla, fuente)`
    **nuevo**: variante batched que escribe vía
    `turso_http_client.execute_pipeline` con batches de 50 statements.
    Incluye enriquecimiento integrado (items + adjudicaciones + organismos)
    en la misma corrida, sin llamar `enriquecer_codigo` por licitación.
    Marca `tipo_origen='servicio'` en items para `Tipo=LE` y `'producto'`
    para CA/AGIL/L1/etc.
  - `descargar_rango(..., use_http_client=False, filtro_tipos=None, filtro_regiones=None, save_raw=True)`:
    parámetros opcionales para filtrado post-fetch y selección de path.
  - **Backward compatibility verificada**: los 2 consumidores existentes
    (`app/ui/dashboard_mercado.py:1031` y `app/core/refresh_cierres.py`)
    no setean los nuevos parámetros y siguen funcionando igual.

- **`app/core/backfill_fases_mvp.py`** (nuevo): orquestador de las 6 fases
  del plan:
  1. Cabecera CA+L1+LE adjudicadas (puebla `mp_licitaciones_adj` + items
     + adjudicaciones + organismos en una pasada).
  2-3. Items producto/servicio (side effect de Fase 1, sólo conteo y bitácora).
  4. Catálogos (recalcula `mp_proveedores` desde `mp_adjudicaciones` vía HTTP).
  5. Resoluciones (conteo de `mp_adjudicaciones`).
  6. Vigentes (puebla `mp_licitaciones_vigentes`).

  Si Fase 1 aborta, fases 2-5 NO ejecutan. Fase 4 puede fallar sin
  bloquear 5/6. Fase 6 corre independiente.
  Diccionario `REGIONES_CODIGO_A_NOMBRE` para resolver
  II/V/RM/VI/X → nombres legibles (substring match).

- **`scripts/backfill_mvp_3m.py`** (nuevo, +carpeta `scripts/`):
  CLI wrapper. `python -m scripts.backfill_mvp_3m --help`. Defaults
  del MVP (hoy - 90 días, 5 regiones, 3 tipos, 6 fases) pero **todo
  parametrizable** — el mismo script corre S12.3.1 (`--fecha-desde
  2025-11-10`) y S12.3.2 (`--fecha-desde 2025-05-10`) sin modificación.
  Exit codes 0/1/2/3 heredados de S12.2.1. `--dry-run` no toca Turso.

- **`tests/test_backfill_mvp_3m.py`** (nuevo, 26 tests en 6 clases):
  - `TestCLIArgs`: parsing, dry-run, subset de fases.
  - `TestExitCodes`: 4 paths (éxito, API, Turso, inesperado).
  - `TestDispatcherFases`: orden estricto, abort de Fase 1 frena 2-5,
    falla de Fase 4 NO bloquea 5/6.
  - `TestPersistirHTTP`: `tipo_origen` correcto (servicio para LE,
    producto para AGIL/L1), idempotencia con INSERT OR IGNORE,
    bulk-check existencia con WHERE IN, validación de tabla cabecera.
  - `TestRegionesYTipos`: helpers de filtrado y mapping códigos.
  - `TestAntiRegresionSQLite`: el path HTTP del backfill NO llama
    `get_connection()` (refuerza el fix de S12.2.1).

- **`docs/sprints/AIDU_Op_S12_3_v22_MVP_3m.docx`**: copia del plan
  para trazabilidad en el repo.

### Criterios técnicos del MVP (ajustados durante reconnaissance)

| # | Criterio | SQL ajustado |
|---|---|---|
| 1 | Exit 0 | n/a |
| 2 | Items producto con precio | `SELECT COUNT(*) FROM mp_licitaciones_items WHERE tipo_origen='producto' AND codigo_externo IN (SELECT codigo_externo FROM mp_adjudicaciones WHERE monto_unitario > 0) ≥ 4500` |
| 3 | Items servicio | `SELECT COUNT(*) FROM mp_licitaciones_items WHERE tipo_origen='servicio' ≥ 300` |
| 4 | Cabecera | `SELECT COUNT(*) FROM mp_licitaciones_adj WHERE tipo IN ('CA','L1','LE') ≥ 1700` |
| 5 | Catálogos | `SELECT COUNT(DISTINCT rut) FROM mp_proveedores ≥ 800`, `SELECT COUNT(*) FROM mp_organismos ≥ 170` |
| 6 | **Corregido** (`mp_licitaciones_adj`) | `SELECT COUNT(*) FROM mp_licitaciones_adj WHERE n_oferentes IS NOT NULL ≥ 1700` |
| 7 | Vigentes | `SELECT COUNT(*) FROM mp_licitaciones_vigentes WHERE tipo IN ('CA','L1','LE') ≥ 400` |
| 8 | Bitácora | `SELECT COUNT(*) FROM mp_ingesta_log WHERE tipo='backfill_mvp_3m' = 6` |
| 9 | Idempotencia | Re-ejecutar con mismo período NO duplica filas (verificado por `INSERT OR IGNORE`). |
| 10 | Smoke test pricing | JOIN entre `mp_licitaciones_items i` y `mp_adjudicaciones a` por `codigo_externo + correlativo/item_correlativo`. Query exacta queda para validar post-corrida. |
| 11 | Suite tests verde | `pytest tests/ -v`: 130/130 (104 previos + 26 nuevos). |
| 12 | Costo Claude API = $0 | S12.3 v2.2 NO categoriza. Confirmado. |

### Hallazgos del reconnaissance

- **`n_oferentes` ya existe en `mp_licitaciones_adj`** (mig 001 línea 25).
  La decisión D2 inicial (`agregar a mp_adjudicaciones`) habría duplicado
  semánticamente. Reescrito a Opción A (no agregar, criterio #6 apunta
  a la tabla correcta).
- **`precio_unitario` no existe en `mp_licitaciones_items`** y NO se
  agrega (D1 = JOIN con `mp_adjudicaciones.monto_unitario`).
- **`descarga_historica.py` ya cubría 80% del flujo**. Su `_persistir_licitaciones`
  + `enriquecer_codigo` extrae items, adjudicaciones, organismos. Se
  reutilizan los parsers puros (`_extraer_items`, `_extraer_adjudicaciones_de_items`,
  `_extraer_organismo`) sin tocar el path SQLite.
- **FK warning del Run #8 no afecta backfill MVP**. La FK ofensora más
  probable es `mp_categorizacion_aidu.codigo_externo → mp_licitaciones_adj`
  (mig 001 línea 73) — el cron diario inserta categorizaciones de
  licitaciones vigentes (no adjudicadas) que aún no están en la cabecera.
  Sin impacto en las 6 tablas del backfill. Agendado como **S12.3.5**
  pre-S12.4.

### Hallazgos de pasada (deuda visible, fuera de scope)

- **Coexistencia `mp_licitacion_items` (singular, mig 001, con FK) vs
  `mp_licitaciones_items` (plural, mig 006, sin FK)**: la singular es
  dead code (solo aparece en tests de bootstrap topology). Conviene
  drop en sprint de limpieza, no en MVP.
- **`mp_descargas_diarias`** (checkpoint local creado por
  `descarga_historica._registrar_dia_descargado`) NO se popula en path
  HTTP (no tiene sentido en runner efímero). El feature de "saltar días
  ya descargados" queda inactivo en backfill MVP — la idempotencia se
  garantiza con `INSERT OR IGNORE`, que es más simple.
- **Rate limit interno del cliente MP = 30 req/min** (`config/settings.py:144`).
  Conservador para el MVP (~90 requests para 3m × 2 endpoints + agil) →
  ~5 minutos del tiempo real. Ventana 90-180 min está sobrada.
- **`_persistir_licitaciones_http` NO popula `mp_historial_cambios`**.
  En el path SQLite, cada cambio de campo se loguea para auditoría
  granular. En HTTP requeriría SELECT por licitación, inviable. La
  idempotencia se mantiene vía `INSERT OR IGNORE`. Esta diferencia entre
  paths está documentada en el docstring de la función.

### Pasos manuales del Director

**Pre-ejecución (10 min)**:
1. Pull en GitHub Desktop del último commit del PR.
2. Verificar suite de tests verde en CI.
3. Aplicar migración 008 a Turso (corre automática vía sistema de
   migraciones en el próximo `get_connection()` que pase por
   `run_migrations()`, o manualmente con los 3 ALTERs vía SQL Console).
4. Refrescar Turso dashboard: tomar baseline de Storage y Rows Written.

**Ejecución (60-180 min)** — Opción A recomendada por el plan:
```bash
cd /c/Users/ividi/OneDrive/Documents/GitHub/aidu-op
python -m scripts.backfill_mvp_3m \
    --fecha-desde 2026-02-10 \
    --fecha-hasta 2026-05-10 \
    --regiones II,V,RM,VI,X \
    --tipos CA,L1,LE \
    --batch-size 50
```

Asumiendo `TURSO_DATABASE_URL` + `TURSO_AUTH_TOKEN` + `MP_TICKET`
seteadas en el shell. Logs en stdout muestran progreso por fase. Exit
code 0 = todas las fases OK.

**Validación (30 min)** post-corrida: ejecutar las queries del cuadro
"Criterios técnicos del MVP" en Turso SQL Console y confirmar los 12.

**Si exit 2** (Turso down): mensaje claro `Turso no disponible tras N
reintentos`. Inspeccionar `Último error:` para diagnóstico (mismo
playbook que S12.2.2).

**Reutilización en S12.3.1 (6m) y S12.3.2 (12m)**:
```bash
# S12.3.1:
python -m scripts.backfill_mvp_3m --fecha-desde 2025-11-10
# S12.3.2:
python -m scripts.backfill_mvp_3m --fecha-desde 2025-05-10
```
Idempotencia garantiza que re-corrida sobre datos existentes NO
duplica. Solo agrega lo nuevo del rango extendido.

## S12.2.2 — Cron a Turso vía HTTP /v2/pipeline (2026-05)

**Branch**: `feature/s12-2-2-libsql-handshake`. **Estado**: PR pendiente de merge.

### Causa raíz

El Run #4 (id 25615368541), tras mergear S12.2.1, falló determinísticamente
con exit 2 — el comportamiento esperado del fix anterior. La causa raíz
del handshake (`Invalid header bit 123 expected 0 or 1`) quedó sin
resolverse. Investigación durante S12.2.2:

1. **`libsql-experimental` está congelado**: `0.0.55` (jun-2025) es la
   última versión publicada en PyPI. Sin parches posteriores.
2. **El paquete fue renombrado a `libsql`** (`0.1.0` el 2025-06-10,
   activo hasta `0.1.11` el 2025-09-02), pero el bug **no es de versión**
   sino arquitectónico: el modo "Embedded Replica" del cliente libsql
   no funciona contra Turso hosteado en AWS. Evidencia:
   - `tursodatabase/libsql-laravel#2` (closed ene-2025), comment de
     `notrab` (Turso oficial): *"This issue is present to anyone using
     a database on AWS. We'll bring Embedded Replicas to AWS very soon."*
     El reporter confirmó que el mismo código funciona en Fly.io.
   - `tursodatabase/libsql-js#157` (open jul-2025) confirma el bug
     persiste con bit 117.
   - `tursodatabase/go-libsql#52` con bit 115.
   - AIDU está en `aws-us-east-2` → afectado.

El nombre genérico del error ("Invalid header bit N") refleja que el
cliente Rust intenta parsear como protobuf de Hrana lo que el servidor
AWS le devuelve como `application/json` (`content-length: 74` constante
en los logs = un payload JSON de error, no de protocolo).

### Decisión

Plan A (upgrade libsql) **descartado por evidencia documental**: ninguna
versión arregla el bug porque está del lado server. **Plan B**: el cron
escribe vía HTTP `/v2/pipeline` directo, transporte estable y oficial,
ya validado en producción por `docs/migracion_inicial_turso.py` desde
S12.1.5. La app Streamlit puede seguir usando `libsql_experimental` para
reads (no afectados por Embedded Replica — `migrator.get_connection()`
intacto).

### Cambios por archivo

- `app/db/turso_http_client.py` **nuevo** (~190 líneas).
  - `is_configured() -> bool`: True si hay credenciales en env vars o
    `st.secrets`.
  - `execute_pipeline(statements, *, timeout=60.0) -> list[dict]`:
    envía pipeline POST a `/v2/pipeline`, mapea HTTP 4xx/5xx, timeout
    y conexión a `TursoUnavailableError` (mismo tipo que S12.2.1).
    Reintentos con backoff exponencial (1s, 4s, 16s = 21s, igual
    política que `migrator._ensure_turso_replica`).
  - `query_one(sql, args)` / `query_all(sql, args)`: helpers que
    extraen valores del wrapper Hrana `{type, value}`.
- `app/core/descarga_diaria.py`:
  - `ejecutar_descarga` ahora bifurca según `is_configured()`:
    - **Modo Turso (productivo)**: `_ejecutar_via_http`.
    - **Modo SQLite (dev/CI/tests)**: `_ejecutar_via_sqlite` (path
      original preservado).
  - `_ejecutar_via_http`:
    - Pre-carga `aidu_servicios_keywords` con 1 SELECT (antes el
      flujo SQLite hacía 1 query por licitación → 446 queries en el
      Run #3 hipotético).
    - Pre-calcula existentes con 1 SELECT batch (`WHERE codigo_externo
      IN (...)`, chunks de 500).
    - Loop en memoria: separa nuevas vs actualizadas, calcula
      categorización AIDU sin tocar BD usando `_match_aidu_inmemory`
      (replica del algoritmo de `app.core.ingesta._calcular_match_aidu`).
    - Batches de 50 statements por pipeline:
      `_batch_insert_vigentes`, `_batch_update_vigentes`,
      `_batch_insert_categorizaciones`.
    - **Escribe `mp_ingesta_log`** al cierre (criterio #3 del plan).
      ANTES el cron diario nunca escribía esta tabla — deuda heredada
      pre-S12.2 que el dashboard de monitoreo y `app.core.backfill`
      necesitaban resuelta.
  - `_match_aidu_inmemory`: nuevo helper, idéntico algoritmo a
    `_calcular_match_aidu` pero sin parámetro `conn`. Recibe matchers
    pre-cargados.
  - `_mapear_licitacion`: extraída como helper (antes estaba inline en
    el loop) para que ambos paths la compartan sin duplicar.
- `tests/test_turso_http_client.py` **nuevo** (~245 líneas, 17 tests).
  - `is_configured` con/sin env vars, con strings vacíos.
  - Endpoint: `libsql://… → https://…/v2/pipeline`, payload incluye
    `{type: close}` implícito.
  - Errores HTTP 500/timeout/ConnectionError → `TursoUnavailableError`
    tras 3 intentos.
  - Backoff exponencial verificado (1.0s, 4.0s, sin sleep al 3°).
  - Recovery en segundo intento (1°: 503, 2°: 200 OK).
  - Helpers `query_one`/`query_all` extraen valores Hrana correctamente,
    propagan errores SQL.
- `tests/test_descarga_diaria_cli.py`:
  - Fixture `_aislar_env_turso` autouse: borra env vars Turso para
    los tests del path SQLite (los previos siguen funcionando con
    `get_connection`).
  - Nueva clase `TestEjecutarViaHTTP` con 7 tests:
    - Path HTTP se selecciona cuando hay credenciales.
    - Códigos existentes van a UPDATE; nuevos van a INSERT.
    - 120 licitaciones → batches `[50, 50, 20]`.
    - `mp_ingesta_log` se escribe (1 fila por corrida).
    - `TursoUnavailableError` durante pipeline propaga sin tragarse.
    - End-to-end vía `_main()`: pipeline falla → exit 2.
    - 1 sola query a `aidu_servicios_keywords` (anti-regresión del
      anti-pattern `1 query por licitación`).
    - Algoritmo in-memory replica casos del canónico (hits, excluyentes,
      texto vacío, sin match).

### Hallazgos de pasada

- **`mp_ingesta_log` no se escribía desde el cron diario** desde antes
  de S12.2. `app/core/ingesta.py` (flujo manual) sí lo hacía. Esto era
  un cuarto bug latente que el plan flagueaba indirectamente como
  criterio de éxito #3 — lo cubrí en este sprint porque era trivial
  (5 líneas) y reportarlo sin arreglar habría hecho fallar la
  verificación post-merge. Sin expansión de scope.
- **El path SQLite quedó preservado intacto** para que dev local sin
  Turso siga funcionando. Esto evita necesidad de un flag `--local` y
  preserva los tests previos de S12.2.1 sin cambios funcionales (solo
  fixture de aislamiento de env).
- **`requirements.txt` sin cambios**. `libsql-experimental==0.0.55`
  queda como está: la app Streamlit lo sigue usando para reads
  (`get_connection`) que no pasan por Embedded Replica. Eliminar la
  dependencia es deuda futura — en cuanto migre `streamlit_app.py` a
  `turso_http_client` el paquete puede salir del manifest.
- **Optimización del flujo**: el path HTTP procesa N licitaciones con
  ~`N/50 + 3` peticiones HTTP (1 SELECT existencia + 1 SELECT keywords
  + N/50 INSERT vigentes + N/50 INSERT categorizaciones + 1 INSERT
  log). Para N=446 son ~21 peticiones, vs el patrón previo (que igual
  habría sido ~446 commits + 446 syncs). El runner tarda menos.

### Pasos manuales post-merge del Director

1. Pull en GitHub Desktop del último commit.
2. Squash and merge `feature/s12-2-2-libsql-handshake` a main.
3. Trigger manual del workflow:
   `Actions → Descarga diaria Mercado Publico a Turso → Run workflow`
   con branch `main` y `dias_atras=2`.
4. Esperar 1-3 minutos.
5. Si el run termina **verde**:
   - Inspeccionar logs: NO debe aparecer `Invalid header bit 123` ni
     mensajes de retry. Sí debe aparecer
     `✅ Descarga completada: {nuevas: ..., actualizadas: ...}`.
   - Turso dashboard: `Rows Written` sube significativamente (>>50
     vs baseline 564).
   - SQL en Turso:
     `SELECT COUNT(*) FROM mp_licitaciones_vigentes WHERE date(fecha_descarga) = date('now');`
     debe ser > 0.
   - SQL en Turso:
     `SELECT * FROM mp_ingesta_log ORDER BY id DESC LIMIT 1;`
     debe tener fila nueva con `n_nuevas > 0`, `estado='OK'`,
     `fecha_ejecucion` de hoy.
   - Reboot Streamlit; tab "🔥 Hoy" muestra licitaciones nuevas.
6. Si el run termina **rojo con exit 2**:
   - El mensaje será `Turso no disponible vía HTTP /v2/pipeline tras
     3 reintentos`. Inspeccionar `Último error:` para diagnosticar:
     - `HTTP 401/403`: token rechazado, regenerar `TURSO_AUTH_TOKEN`.
     - `HTTP 5xx`: Turso server-side, esperar y reintentar.
     - `Timeout`/`ConnectionError`: red del runner, problema esporádico.

## S12.2.1 — Fix crítico: eliminar fallback silencioso a SQLite (2026-05)

**Branch**: `feature/s12-2-1-fix-fallback-turso`. **Estado**: PR pendiente de merge.

### Causa raíz

Validación post-merge de S12.2 reveló que el cron del Run #3 (id
25611217780) terminó verde en 47s pero NO escribió las 446 licitaciones
descargadas a Turso. Los logs muestran la cadena de fallas:

1. `libsql.connect(...).sync()` levanta
   `Invalid header bit 123 expected 0 or 1` durante el handshake con
   Turso (ambiente GitHub Actions; en local funciona).
2. `migrator._ensure_turso_replica()` capturaba esa excepción,
   loggeaba `❌ Turso no disponible, opero contra SQLite local: …`
   y devolvía `False`.
3. `get_connection()` veía `turso_active=False` y abría
   `sqlite3.connect(DB_PATH)` contra el filesystem efímero del runner.
4. El SQLite recién creado NO tenía schema (las migraciones se aplican
   antes contra Turso vía HTTP /v2/pipeline). Cada uno de los 446
   `INSERT INTO mp_licitaciones_vigentes` levantaba
   `no such table: mp_licitaciones_vigentes`.
5. El `try/except Exception` interno por licitación capturaba el error
   como "fallida individual" y seguía. 446 fallidas sin escalar a
   exit 1. El proceso terminó con exit 0.
6. El runner se destruyó. Los datos en `/tmp/aidu_op.db` se perdieron.

Mismo patrón arquitectónico que motivó S12.1 (BD efímera en cold
start), reaparecido en la capa de descarga.

### Fix aplicado

- `app/db/exceptions.py` **nuevo**. Define `TursoUnavailableError` con
  metadata (intentos, último error). Sustituye el fallback silencioso
  con una excepción explícita que el CLI puede mapear a exit 2.
- `app/db/migrator.py` `_ensure_turso_replica` refactorizado:
  - **Sin credenciales** (modo dev/CI/tests): comportamiento intacto,
    devuelve `False` y `get_connection()` usa SQLite local. No es
    un error, es un modo operativo legítimo.
  - **Con credenciales y handshake fallido**: reintenta hasta 3 veces
    con backoff exponencial (1s + 4s + 16s = 21s total). Si los 3
    intentos fallan, **levanta `TursoUnavailableError`** en lugar de
    caer al SQLite local. Agrega tolerancia a fallas transitorias
    sin reintroducir el patrón peligroso.
  - El log incriminatorio `Turso no disponible, opero contra SQLite
    local` queda eliminado del runtime.
- `app/core/descarga_diaria.py`:
  - `MercadoPublicoAPIError` **nuevo** (clase local). Las llamadas al
    cliente MP se envuelven y convierten a este tipo, eliminando la
    necesidad de heurística por substring para distinguir API vs BD.
  - `__main__` extraído a `_main() -> int`, testeable sin subprocess.
  - Captura tipada por exit code:
    - `0` éxito.
    - `1` `MercadoPublicoAPIError` (rate limit, downtime, ticket).
    - `2` `TursoUnavailableError` (handshake, sync, auth Turso).
    - `3` cualquier otra excepción + traceback al stderr.
  - El `try/except` interno por licitación re-raisea
    `TursoUnavailableError` para que NO se contabilice como "falla
    individual" — sin esto, el bug del Run #3 podría reproducirse
    si el sync falla a media corrida.
- `tests/test_descarga_diaria_cli.py` **nuevo**. 6 tests:
  - 4 exit codes (0/1/2/3) con monkeypatch de `ejecutar_descarga`.
  - Anti-regresión: error de la API con substring "auth" sigue siendo
    exit 1, no exit 2 (la heurística previa lo confundía).
  - `TursoUnavailableError` durante el loop de licitaciones propaga al
    caller en lugar de tragarse como falla individual.
- `tests/test_no_sqlite_fallback.py` **nuevo**. 5 tests estructurales:
  - `app/` no contiene la frase prohibida del fallback.
  - `sqlite3.connect` solo aparece en lista blanca (migrator,
    migracion_inicial_turso, tests/).
  - `TursoUnavailableError` importable y con metadata correcta.
  - `_ensure_turso_replica` levanta con credenciales + handshake
    fallido, **devuelve False** sin credenciales.

### Hallazgos de pasada

- El bug `Invalid header bit 123 expected 0 or 1` en
  `libsql_experimental==0.0.55` **no se resuelve en este sprint**.
  Mitigación: backoff de hasta 21s antes de exit 2 — tolera fallas
  transitorias sin caer a SQLite. Si el bug es determinístico contra
  Turso aws-us-east-2, el cron seguirá fallando con exit 2 limpio
  hasta que se diagnostique. Queda agendado como S12.2.2: validar
  versiones nuevas de libsql_experimental, formato de TURSO_AUTH_TOKEN
  inyectado por GitHub Secrets, región Turso.
- `descarga_diaria.py` hace `conn.commit()` dentro del loop por
  licitación. En Turso cada commit dispara un sync. Para 446 inserts
  son 446 syncs HTTP. Optimizable a batch commit cada 50-100 — fuera
  de scope.
- `requirements.txt` no se modificó. `libsql_experimental==0.0.55`
  queda como está; la decisión de actualizar se difiere a S12.2.2.

### Pasos manuales post-merge del Director

1. Pull en GitHub Desktop del último commit del fix.
2. Squash and merge `feature/s12-2-1-fix-fallback-turso` a main.
3. Trigger manual del workflow:
   `Actions → Descarga diaria Mercado Publico a Turso → Run workflow`
   con branch `main` y `dias_atras=2`.
4. Esperar 1-3 minutos.
5. Si el run termina **verde**:
   - Turso dashboard: `Rows Written` debe subir significativamente
     (>>200, en el orden de las licitaciones descargadas).
   - `SELECT COUNT(*) FROM mp_licitaciones_vigentes` debe ser > 0.
   - `SELECT * FROM mp_ingesta_log ORDER BY rowid DESC LIMIT 1` debe
     tener fila nueva con `n_nuevas > 0`.
   - Reboot de Streamlit; tab "🔥 Hoy" muestra licitaciones nuevas.
6. Si el run termina **rojo con exit 2**:
   - Confirmar mensaje claro `Turso no disponible tras N reintentos`.
   - Si la causa sigue siendo `Invalid header bit 123`, escalar
     a S12.2.2 con fix de libsql.
   - Si la causa es otra, revisar logs y reportar.

## S12.2 — Reactivación cron diario contra Turso (2026-05)

**Branch**: `feature/s12-2-cron-turso`. **Estado**: PR pendiente de merge.

### Cambios

- `.github/workflows/descarga_mp_diaria.yml` **nuevo**. Cron 10:00 UTC
  (7 AM Chile en horario de verano), `workflow_dispatch` para trigger
  manual con input `dias_atras`. Sin `contents: write`, sin commit-back.
  Inyecta `TURSO_DATABASE_URL`/`TURSO_AUTH_TOKEN` para que `get_connection()`
  enrute a Turso vía libsql.
- `.github/workflows-legacy/descarga_mp_diaria_v1.yml.txt` **archivado**
  (era `descarga_mp_diaria.yml.disabled`). Patrón legacy commit-back queda
  preservado para historia.
- `app/core/descarga_diaria.py`: `ejecutar_descarga` ahora cubre **AMBOS**
  endpoints de Mercado Público en una sola corrida — el principal
  (L1/LE/LP/LR/LS/LQ/CO) **y** el endpoint AGIL (Compras Ágiles <100 UTM,
  MVP comercial AIDU). Antes solo el principal. Si AGIL cae, el principal
  sigue. Stats incluyen `agiles_descargadas`. Modo CLI (`__main__`) ahora
  diferencia exit codes 0/1/2 por API/BD para diagnóstico operacional.
- `app/db/_hrana_types.py` **nuevo**. Helpers `arg_for_value` y
  `coerce_for_column` extraídos del bootstrap S12.1.5 a un módulo
  compartido. Evita drift entre runtime (`migrator.py`) y bootstrap
  (`docs/migracion_inicial_turso.py`), que tenían las mismas funciones
  duplicadas con un bug str(float) divergente.
- `app/db/migrator.py`: `_query_on_turso` y `_execute_on_turso`
  refactorizados. Ahora ambos pasan por `_hrana_types.arg_for_value`.
  Fix de bug latente: floats en parámetros se serializaban como string,
  Turso responde HTTP 400 'expected f64'. Único call site externo era
  `app/db/health_check.py` (solo passes ints/strings, así que el bug
  nunca se disparó en producción). Bonus: `_execute_on_turso` ahora
  acepta `params` para parametrizar DDL/DML.
- `docs/migracion_inicial_turso.py`: definiciones locales de `_arg`
  y `_coerce` reemplazadas por re-export del módulo compartido. Sin
  cambio funcional.
- `tests/test_hrana_types.py` **nuevo**. Tests unitarios del módulo
  centralizado: tipos, coerción, casos límite (None, bool, blob,
  unknown affinity), regresión del bug str(float).

### Hallazgos de pasada

- `refresh_cierres.yml` todavía tiene `permissions: contents: write` y
  patrón legacy. Modernizar a Turso queda para sprint correctivo.
- Migración 004 y 005 ambas crean `proy_consultas` con `IF NOT EXISTS`
  (idempotente). Limpieza menor pendiente.
- Coexisten en schema `mp_licitacion_items` (singular, mig 001, con FK)
  y `mp_licitaciones_items` (plural, mig 006, sin FK). Probable rename
  a medias — verificar intención.

### Pasos manuales post-merge del Director

1. Verificar GitHub Secrets: `Settings → Secrets and variables → Actions`.
   Confirmar presencia de `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`,
   `MP_TICKET`, `ANTHROPIC_API_KEY`. Agregar los que falten.
2. Mergear PR `feature/s12-2-cron-turso` a main.
3. GitHub web → `Actions` → `Descarga diaria Mercado Publico a Turso`
   → `Run workflow` (trigger manual). Default `dias_atras=2`.
4. Verificar run verde y dashboard Turso con `Rows Written` incremental.
5. Forzar reboot Streamlit; verificar tab "🔥 Hoy" con licitaciones nuevas.
6. Esperar al día siguiente 7 AM Chile y verificar disparo automático.

## S12.1.5 — Bootstrap one-shot a Turso (2026-05)

PRs #2 y #3. Schema completo + datos iniciales propagados a Turso vía
HTTP /v2/pipeline. Fix coerción de tipos REAL. Topo-sort de FKs antes
de los INSERTs masivos (commit `ea65fce`). Detalles en commits.

## S12.1 — Migración a Turso (2026-05)

PR #1. Persistencia BD madre vía libsql-experimental embedded replica.
Fix pérdida de datos en cold start del contenedor Streamlit Cloud.
