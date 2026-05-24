# Changelog AIDU Op

Registro cronológico de sprints técnicos desde S12. Para sprints previos
ver `docs/sprints/` (notas individuales por sprint) y el log de git.

## S13.5 — Backfill histórico Febrero 2026 O'Higgins (2026-05-24)

**Branch**: `feature/s13-5-backfill-feb2026`. **Estado**: PR pendiente.
**Duración**: ~45 min Code. **Costo Claude API esperado**: ~$0.70 USD
(cost guard $3.00). **Items estimados**: 150-300.

**Primer sprint** de una serie de 10 sprints encadenados que cubrirán
progresivamente los 10 meses faltantes (feb 2026 → may 2025). La
infraestructura introducida aquí (idempotencia por `codigo_mp` + flag
`usar_semantico` en el ingestor) será reutilizada por **S13.6 hasta
S13.14**. Esos sprints siguientes serán de ~15 min Code cada uno
(básicamente: cambiar fechas en el script + crear workflow temporal).

### Reconnaissance previo: discrepancias con el spec

- **`ingestar_rango()` ya existía**: se llama `ingerir_rango()` en
  `app/core/ingesta_inteligencia_precios.py:466-629`. Spec sec 10 dice
  "reusar, no duplicar" → seguimos esa regla. Solo agregamos params
  nuevos.
- **`region_codigo` NO se puede pasar a la API MP**: el endpoint
  `/licitaciones.json?fecha=DDMMYYYY&estado=adjudicada` no acepta
  filtro por región. Filtrado client-side via `unit_code` CSV +
  `organismos_ohiggins_auto`. Mantenemos la arquitectura existente.
- **Endpoint MP histórico es el MISMO que el diario**: confirmado en
  reconnaissance S13.4.4 (llamadas exitosas a códigos feb 2026 con
  ticket demo).
- **Ingestor actual NO usa Claude durante la ingesta**: solo lexical.
  Los 687 items con `clasificacion_metodo='semantic'` lo son por el
  script post-hoc S13.4.3. Para que el backfill use Claude desde el
  origen hay que threadear `usar_semantico=True` por
  `ingerir_rango()` → `categorizar_item()`.

### Decisiones del Director aprobadas (S13.5 sec 4 + ajustes finos)

- **D1 = (a)**: reusar `ingerir_rango()` agregándole `usar_semantico` kwarg.
- **D2 = (a)**: SELECT bulk al inicio para idempotencia por `codigo_mp`,
  con buffer **±30 días** sobre el rango (cubre licitaciones
  publicadas un mes y adjudicadas el siguiente).
- **D3 = (a)**: workflow temporal dedicado `_chore_backfill_feb2026.yml`.
  Se borra en batch cleanup al final del backfill 12 meses.
- **D4 = (a)**: 1 dispatch único cubre los 28 días de Feb 2026
  (persistencia incremental + cost guard $3 USD protegen).

### Cambios por archivo

- **`app/core/ingesta_inteligencia_precios.py`** (modificado, +120/-3):
  - Constantes nuevas: `COST_INPUT_PER_MTOK=3.0`, `COST_OUTPUT_PER_MTOK=15.0`,
    `PROMPT_TOKENS_AVG=450`, `OUTPUT_TOKENS_AVG=120`. Helper
    `_estimar_costo_claude(n_calls)`.
  - `StatsCorrida` extendido: `n_skip_idempotente`,
    `n_llamadas_semanticas`, `costo_claude_usd`, `aborted_cost_guard`.
  - Helper público `cargar_codigos_existentes(fecha_desde, fecha_hasta,
    buffer_days=30)`: SELECT bulk con buffer ±30 días. Tolera Turso
    no configurado / tabla faltante / query fallida (degrada a no-idempotente,
    no crashea).
  - `ingerir_rango()`: nuevos kwargs `usar_semantico=False`,
    `cost_guard_max_usd=None`, `codigos_existentes_buffer_days=30`,
    `codigos_existentes_override` (testing). Loop:
    1. SKIP `codigo` si está en `codigos_existentes` antes de
       `detalle_licitacion()` → ahorro cuota MP + Claude.
    2. Thread `usar_semantico` a `categorizar_item()`.
    3. Cost guard tras cada flush: proyecta usando proporción de días
       procesados. Si supera tope, persiste pendiente + sale con
       `stats.aborted_cost_guard=True`.

- **`scripts/s13_5_backfill_feb2026.py`** (nuevo, +145, TEMPORAL):
  wrapper que llama `ingerir_rango(date(2026,2,1), date(2026,2,28),
  lote_id='backfill_feb2026', usar_semantico=True,
  cost_guard_max_usd=3.0, ...)`. Pre-checks: Turso + MP_TICKET +
  ANTHROPIC_API_KEY. Reporte final con todas las métricas del Director:
  `n_listados`, `n_filtrados`, `n_skip_idempotente`, `n_procesados`,
  `costo_claude_usd`, `ratio_cobertura` (para alerta temprana de TD-05),
  `tiempo_total`. Exit codes 0/1/3/4.

- **`.github/workflows/_chore_backfill_feb2026.yml`** (nuevo, TEMPORAL):
  workflow_dispatch sin inputs. timeout 60min. Env vars TURSO + MP_TICKET
  + ANTHROPIC_API_KEY. Step explícito de `run_migrations()`. Post-step
  de reporte conteo Feb 2026 + total BD.

- **`tests/test_idempotencia_backfill.py`** (nuevo, 11 tests):
  - `TestCargarCodigosExistentes` (4): Turso no configurado / buffer
    aplicado correctamente / devuelve set / query fallida no crashea.
  - `TestSkipIdempotente` (4): SKIP no pega detalle / 0 detalles
    cuando todos existen / cron diario NO precarga el set / backfill
    SÍ lo precarga con `buffer_days=30`.
  - `TestCostGuardBackfill` (3): default StatsCorrida flag False /
    costo lineal en N calls / N=0 → costo=0.

- **`tests/test_backfill_rango_fechas.py`** (nuevo, 10 tests):
  - `TestIteracionRangoFechas` (4): 1 día / rango inclusivo / Feb 2026
    = 28 días / `fecha_desde > fecha_hasta` → ValueError.
  - `TestUsarSemanticoThreadThrough` (2): True propaga / False es default
    y propaga (cron diario sigue lexical).
  - `TestStatsCorridaCamposNuevos` (4): campos nuevos en dataclass /
    costo se calcula al cierre / fallback a 'keyword' no cuenta como
    llamada semántica / método 'semantic' sí cuenta.

- **`docs/tech_debt.md`** (modificado, +TD-05):
  TD-05 — cobertura unit_codes en meses lejanos. Riesgo de cobertura
  baja en sprints S13.7 (dic 2025) hacia atrás por seed CSV no
  actualizado. Mitigación: monitorear `ratio_cobertura` reportado por
  cada script de backfill; si cae bajo 50% del baseline, sugerir
  auto-discovery profundo antes del siguiente mes.

### Idempotencia exacta

Re-dispatchar el workflow N veces converge al mismo estado:
1. Run 1: procesa ~230 items nuevos. Cost ~$0.70.
2. Run 2: SELECT bulk encuentra los 230 + cualquier overlap con BD vieja.
   `n_skip_idempotente` ≈ 230, `n_llamadas_semanticas` = 0, cost = $0.

### Compatibilidad cron diario

`ingerir_rango()` mantiene su signature anterior. Los nuevos kwargs son
opcionales con defaults conservadores:
- `usar_semantico=False`: cron diario sigue lexical, costo Claude $0.
- `cost_guard_max_usd=None`: cron diario sin guard (no aplica).
- `codigos_existentes_*` defaults: cron diario NO precarga el SELECT bulk
  (es un costo Turso innecesario en el path lexical).

Tests existentes pasan sin modificación.

### Fuera de scope (confirmado)

- Otros meses (S13.6 ene 2026 ... S13.14 may 2025): cada uno tendrá
  su propio sprint chico.
- Otras regiones (Antofagasta, Valparaíso, RM, Los Lagos): diferido a
  sprints post-MVP regional.
- Refinamiento TD-04 prompt semántico granular: diferido.
- Re-clasificación de los 687 items existentes: NO se tocan.

## S13.4.4 — Cleanup post-S13.4.3 (2026-05-24)

**Branch**: `feature/s13-4-4-cleanup-cosmetico`. **Estado**: PR pendiente.
**Duración**: 10-15 min Code. **Costo Claude API**: $0.

Sprint correctivo + documentación. Reconnaissance demostró que los dos
hallazgos iniciales del Director (Excel sin columnas nuevas + 85 items
con `precio_unitario NULL`) NO requieren cambios de código: el primero
ya estaba resuelto en `main` desde S13.4.3, el segundo es limitación
estructural del dato MP. Quedó cleanup cosmético + tech debt registrado.

### Hallazgos del reconnaissance

- **Hallazgo Excel — no requiere código**: el handler de `Exportar a
  Excel` en `app/ui/inteligencia_mercado.py` (líneas 459-486) ya incluía
  las 17 columnas (14 originales + `confidence_score`,
  `clasificacion_metodo`, `es_producto_granular`) desde el merge de
  S13.4.3 (PR #18). El Director había descargado un `.xlsx` previo al
  deploy de Streamlit Cloud y vió las 14 columnas antiguas en cache. Tras
  shift+reload + re-download desde la app productiva, las 3 columnas
  nuevas aparecen.

- **Hallazgo Parser NULL — limitación estructural del dato MP, NO bug**:
  inspección manual de 3 códigos del listado del Director vía API MP
  (con ticket demo `F8537A18-6766-4DEF-9E59-426B4FEE2844`) muestra que
  los items con `precio_unitario IS NULL` en BD son items con
  `Adjudicacion: None` en el JSON crudo. Esto es la API señalizando que
  el comprador **declaró desierto ese ítem específico** dentro de una
  licitación parcialmente adjudicada (sin oferentes para ese ítem,
  precio no conveniente, o decisión del comprador).

  | Código | Comprador | Items totales | `Adjudicacion=None` | Con precio OK |
  |---|---|---|---|---|
  | 1627-42-LE26 | Hospital San Fernando | 14 | **10** | 4 |
  | 1627-29-LE26 | Hospital San Fernando | 13 | 2 | 11 |
  | 2107-51-LE26 | Hospital Santa Cruz | 20 | 2 | 18 |
  | **Total muestra** | | **47** | **14 (30%)** | 33 (70%) |

  El parser (`app/core/ingesta_inteligencia_precios.py:272-286`) ya
  maneja `Adjudicacion=None` correctamente: deja `precio_unitario=None`.
  No hay nada que arreglar.

  **Patrones del spec descartados con evidencia**:
  - ❌ Coma decimal (`"7.885,00"`): los precios llegan como float Python
    nativo (`20784.0`, `7885.0`, `46800.0`). No hay strings localizados.
  - ❌ Nodo XML alternativo (`PrecioUnitario` / `Precio` / `ValorUnitario`):
    los 3 son siempre `None`. La API solo expone `MontoUnitario`.
  - ⚠️ Items sin nodo `Adjudicacion`: existe — pero el parser ya lo
    maneja. NO es bug, es la API señalizando ítem desierto.

  **Consecuencia para análisis comercial**: el techo real de cobertura
  de la BD baja del 72% estimado a ~60% items oro (`precio_unitario>1`
  y `cantidad>1`). Los 85 items NULL son ruido inevitable, no
  recuperables vía re-parseo ni vía nueva descarga.

### Cambios por archivo

- **`scripts/s13_4_3_reclasificar_semantico.py`** (modificado, +5/-1):
  fix cosmético línea 342. Coerción `int(r[1])` antes del format spec
  `:5d` porque Turso/Hrana devuelve `COUNT(*)` como string en el
  resumen final del script. Mismo patrón defensivo que
  `_safe_int()` en la UI. El script se mantiene en repo: es reusable
  en Lotes 5-12 del backfill histórico.

- **`.github/workflows/_chore_clasificar_semantico.yml`** (BORRADO):
  workflow temporal que cumplió su función (Run #2 exitoso con 687
  items persistidos via S13.4.3.1 persistencia incremental). Política
  de cleanup: no acumular workflows TEMPORAL en main. Si se re-necesita
  para Lotes 5-12, se re-crea desde el script que sigue versionado.

- **`docs/tech_debt.md`** (modificado, +2 TDs nuevos):
  - **TD-03 — Formato de `confidence_score` en Excel exportado**:
    side-finding del reconnaissance. El DataFrame de UI muestra `"85%"`
    pero el Excel exporta `0.85` (float crudo). Sin fix por ahora — el
    Director decidirá si quiere formato porcentual.
  - **TD-04 — Falsos positivos `es_producto_granular=True` por
    descripciones de bloque**: ~58 items con `cantidad=1` y descripción
    tipo "ver listado anexo", "línea N", "según TDR" pasan el filtro
    granular. El clasificador semántico los marca como granulares pero
    semánticamente son agregados globales. Refinamiento del prompt
    queda pendiente.

### Fuera de scope (confirmado)

- Lotes 5-12 backfill histórico (sprint posterior).
- Refinamiento prompt semántico para TD-04 (sprint posterior).
- Análisis comercial Salud (S14, con el techo real ~60%).
- Cualquier intento de "recuperar" los 85 items NULL: estructuralmente
  imposible.

## S13.4.3.1 — Persistencia incremental + idempotencia + timeout 60min (2026-05-24)

**Branch**: `feature/s13-4-3-1-persistencia-incremental`. **Estado**: mergeado a main.

Fix post-S13.4.3 tras Run #1 del workflow temporal cancelado por timeout
30min a 600/685 items con pérdida estimada $1.89 USD (los UPDATEs se
aplicaban solo al cierre del loop). Cambios mínimos:

- **`scripts/s13_4_3_reclasificar_semantico.py`** (refactor +170/-90):
  flush incremental cada `BATCH_SIZE=50` items en lugar de un solo
  flush al final. Idempotente: el SELECT inicial filtra
  `WHERE clasificacion_metodo IS NULL OR clasificacion_metodo != 'semantic'`,
  re-disparar el workflow continúa donde quedó. Flag `--force` para
  override del filtro. Cost guard flushea pendiente antes de abortar.
- **`.github/workflows/_chore_clasificar_semantico.yml`**: timeout
  30 → 60 min (margen 2x).
- **`tests/test_reclasificacion_persistencia_incremental.py`** (nuevo,
  9 tests): cubre `_leer_pendientes` default/force, `_flush_batch`
  (granular True/False/None codificado a Hrana, cantidad statements,
  SQL correcto).

**Resultado en producción**: Run #2 procesó 687 items en ~9 min
(margen confortable bajo 60min timeout), persistencia visible incluso
si hubiera fallado a mitad.

## S13.4.3 — Clasificador semántico con Claude API + es_producto_granular (2026-05)

**Branch**: `feature/s13-4-3-clasificador-semantico`. **Estado**: PR pendiente.
**Origen**: validación visual del Director (24/05/2026) sobre el Excel de 685
items reveló ~33% de falsos positivos en el clasificador lexical
(insumos médicos en Ferretería/Oficina por keywords ambiguas como
'acero', 'malla', 'válvula', 'lápiz', 'cable').

### Decisiones del Director durante reconnaissance

- **Modelo Claude** = opción **(c)** APROBADA: configurable vía env var
  `CLAUDE_MODEL_CLASIFICADOR` con default `claude-sonnet-4-5`. Override
  sin tocar código.
- **TD-02** AGENDADO: unificar 3 callers existentes de Claude API en
  `app/core/analisis_*.py` al cliente canónico `app/api/claude_client.py`.
  Documentado en `docs/tech_debt.md` TD-02. NO en scope de este sprint.
- **Bug cosmético format spec :d**: aplicar patrón defensivo desde el
  inicio en UI. Coerción explícita vía `_safe_int()` / `_safe_float()`
  antes de cualquier format spec.

### Cambios por archivo

- **`app/db/migrations/012_clasificacion_semantica.sql`** (nuevo, +40):
  3 ALTERs (`es_producto_granular INTEGER`, `confidence_score REAL`,
  `clasificacion_metodo TEXT`) + 2 índices. Idempotente. Nota crítica
  del file: no usar `;` en comments porque el migrator hace split simple.

- **`config/settings.py`** (modificado, +20): nueva función
  `get_modelo_clasificador()` que lee env var `CLAUDE_MODEL_CLASIFICADOR`
  con fallback al `CLAUDE_MODEL` global. Permite override sin redeploy.

- **`app/api/claude_client.py`** (nuevo, +130): cliente canónico con
  `get_client()`, `llamar_claude_json()`, `ClaudeApiUnavailableError`.
  Lazy import de `anthropic` para mantenerlo testeable con mocks. Soporta
  override del modelo vía argumento y del system prompt opcional. README
  inline indica override por env var.

- **`app/core/clasificador_semantico.py`** (nuevo, +175): función pública
  `clasificar_via_claude(descripcion, organismo)`. Prompt template del
  spec sec 4.4. Validación contra `LINEAS_AIDU_FAST_CON_OTROS`. Coerción
  defensiva de tipos (granular como bool/int/string, confidence clamp
  0-1). Descripciones <10 chars no pegan API (ahorro costo).

- **`app/core/ingesta_inteligencia_precios.py`** (modificado, +60/-3):
  `categorizar_item()` ahora acepta `usar_semantico: bool = False`
  (opt-in). En `True` intenta semántico, fallback automático al lexical
  ante `ClaudeApiUnavailableError`. Siempre emite las 3 columnas nuevas
  (granular/confidence/método) para que el INSERT del ingestor no rompa
  por KeyError, aunque el modo lexical las deja en None/0.0/'keyword'.

- **`scripts/s13_4_3_reclasificar_semantico.py`** (nuevo, +220, TEMPORAL):
  one-shot UPDATE en batches de 50. Rate limit 5 req/s, backoff manual,
  fallback lexical en cada item si API falla. Cost guard cada 50 items:
  si proyección supera $5 USD, aborta con exit 4.

- **`.github/workflows/_chore_clasificar_semantico.yml`** (nuevo, TEMPORAL):
  `workflow_dispatch` con input opcional `modelo` para override del
  default. Step pre-flight de migraciones. Cleanup en PR aparte.

- **`app/ui/inteligencia_mercado.py`** (modificado, +75/-12):
  - `_COLS_INTELIGENCIA`: 21 → 24 (agregadas 3 columnas semánticas).
  - SELECT actualizado.
  - `_safe_int()` / `_safe_float()` helpers defensivos para evitar el bug
    `ValueError: Unknown format code 'd' for object of type 'str'`.
  - `_aplicar_filtros()`: nuevos parámetros `solo_granulares` y
    `confidence_min`.
  - Tab buscador: checkbox "Solo productos granulares" (default True),
    slider de confidence mínima (0-100%, default 0).
  - Tabla muestra `confidence_score` formateado como `85%`, `clasificacion_metodo`
    y `es_producto_granular`.

- **`docs/tech_debt.md`** (modificado, +50): nueva entrada TD-02 (unificar
  3 callers Claude API). TD-01 (UTF-8 wrapper) sigue abierto.

- **Tests nuevos** (+30 tests, 3 archivos):
  - `tests/test_clasificador_semantico.py`: parsing, validación de línea,
    coerción de tipos, propagación de errores API.
  - `tests/test_es_producto_granular.py`: 10 casos golden (producto vs
    contrato marco vs obra vs estudio vs servicio).
  - `tests/test_clasificador_fallback.py`: fallback lexical ante fallo
    API + schema de columnas nuevas en cualquier modo.

- **`tests/test_inteligencia_mercado_data.py`** (modificado, +9/-3):
  fixture FILA_SAMPLE ampliado a 24 columnas. Asserts de `len(cols) == 24`.

### Tests
**295/295 verde** (262 previos + 33 nuevos en este sprint).

### Validación local

- Mig 012 aplicada en SQLite local. Verificación: 28 columnas en
  `inteligencia_precios` (25 previas + 3 nuevas).
- pytest 295 ok.
- Smoke del cliente: imports OK, `arg_for_value` shape Hrana validado.

### Próximo paso post-merge

1. Director merge PR.
2. Trigger manual del workflow `[CHORE] Clasificar semantico S13.4.3 (TEMPORAL)`.
   Costo esperado ~$1.64 USD para 685 items.
3. Validar logs: matriz origen→destino + distribución confidence + granulares.
4. Validar visual en
   https://aidu-op-ignacio.streamlit.app/Inteligencia_Mercado con filtro
   "Solo granulares" activo.
5. PR de cleanup chico (borrar workflow temporal + script).
6. Decidir: Lotes 5-12 con clasificador semántico activo, fix parser
   NULL (S13.4.4), o S14 Salud comercial.

---

## S13.4.2-cleanup — Borrado de artefactos temporales del sprint S13.4.2 (2026-05)

**Branch**: `chore/cleanup-s13-4-2-temporal-artifacts`. **Estado**: PR pendiente.
**Tipo**: chore. Sin cambios funcionales.

### Motivación

Tras el merge de S13.4.2 (PR #16) y la ejecución exitosa del workflow temporal
`[CHORE] Reclasificar lineas S13.4.2 (TEMPORAL)`, los siguientes artefactos
cumplieron su función one-shot y se eliminan por política de no acumular
workflows temporales en `main`:

- Reclasificación efectiva confirmada por el Director: **90 items reclasificados
  en Turso productivo** (48 a Salud, 11 a Materiales de Construcción, resto a
  otras líneas vía prioridad fija D3).
- El script y workflow son idempotentes — si se quisiera reusar el patrón en
  el futuro, el commit `722df42` (S13.4.2) contiene la lógica original.

### Cambios

- **BORRADO**: `.github/workflows/_chore_reclasificar_lineas.yml` (50 líneas,
  workflow_dispatch one-shot).
- **BORRADO**: `scripts/s13_4_2_reclasificar_lineas.py` (~150 líneas, lógica de
  UPDATE en batches contra Turso con auditoría).

### Bug cosmético documentado (sin fix en este sprint)

Durante la validación visual del Director en
https://aidu-op-ignacio.streamlit.app/Inteligencia_Mercado, se detectó un
error de formato en la pantalla:

```
ValueError: Unknown format code 'd' for object of type 'str'
```

**Causa probable**: en `app/ui/inteligencia_mercado.py` (o módulos
adyacentes), algún `f"{valor:d}"` o equivalente recibe un `str` en lugar
del `int` esperado. Patrón típico cuando un valor que se asume entero
viene de Turso/Hrana como string serializado, o cuando una métrica con
`int()` falla por valor None que se castea silenciosamente a string.

**Fix sugerido (para sprint posterior)** — el patrón canónico es coercer
explícitamente antes del format spec:

```python
# ANTES (fragil si valor llega como str o None):
f"{valor:d}"
f"{valor:,}"

# DESPUÉS (defensivo):
try:
    n = int(valor) if valor not in (None, "") else 0
except (TypeError, ValueError):
    n = 0
f"{n:d}"  # o f"{n:,}"
```

Donde aparezca el patrón roto, agregar coerción + fallback a 0 (o "—"
para display). Aplica especialmente a `st.metric()` y a cualquier
`f"...{x:d}..."` con valores que pueden venir de SQL/HTTP no tipado.

### Cleanup pendiente (no en este sprint)

- `.github/workflows/_chore_truncate_lote_1.yml` (sprint S13-trunc) sigue
  en `main`. Cumplió su función pero no se borró en su momento. Agendar
  cleanup conjunto cuando el dashboard de Turso permita confirmar que
  `mp_licitaciones_adj` no tiene huecos.

## S13.4.2 — Líneas Salud + Construcción + prioridad fija + excluyentes (2026-05)

**Branch**: `feature/s13-4-2-lineas-salud-construccion`. **Estado**: PR pendiente.
**Origen**: tras descartar S13.4.1 (premisa de bug de parser inexistente), el
diagnóstico de calidad del Lote 1 sobre los 654 items reveló que 270 de los
434 en `linea_aidu='Otros'` son insumos médicos sin clasificar. Sprint de
cosecha rápida: enriquece el diccionario y re-clasifica, sin re-descargar.

### Decisiones del Director (5)

- **D1** APROBADO: CSV + mig 011 con `DELETE + INSERT OR REPLACE` (mismo patrón mig 010).
- **D2** APROBADO: soporte `keywords_excluyentes` activado (columna ya existía desde mig 001 sin uso). CSV ahora tiene columna `excluyente` (0/1).
- **D3** APROBADO: refactor a prioridad fija: Salud > Construcción > Aseo > Oficina > Ferretería > Equipamiento > Otros.
- **D4** APROBADO: las dos `LINEAS_AIDU_FAST` hardcoded del repo se unifican; la UI importa la canónica desde `app.core.categorizador_aidu_fast`.
- **D5** APROBADO con condición: 1 caso del Lote 1 reclasificado (≤3 threshold) — ÁRIDOS pasa de Ferretería → Materiales de Construcción.

### Re-interpretación de criterios cuantitativos (contexto del Director)

El spec asumía "Salud 250-290 items" porque incluía matching por organismo.
Tras rechazar ese path (sec 1.4), los rangos reales esperados:

| Métrica | Spec original | Re-interpretado | Razón |
|---|---|---|---|
| Salud items | 250-290 | **50-130** | Sin matching por organismo |
| Construcción items | 5-15 | 5-15 | Sin cambio |
| Otros residual | <200 | **300-380** | Coherente con remoción de matching por organismo |
| Aseo/Oficina/Equipamiento ±5% | Estricto | **Relajado** | Permite reclasificación correctiva de ~35 items médicos mal clasificados (laparoscópica, hemostático, ECG, brazalete) |

Alarmas (mantienen estricto): producto claramente de Aseo en Salud / Otros < 100 / >3 casos Lote 1 cambian / pytest baja de 245.

### Cambios por archivo

- **`app/db/migrations/011_lineas_salud_construccion.sql`** (nuevo, +5kB):
  - 3 ALTER en `inteligencia_precios`: `linea_aidu_anterior`, `reclasificacion_fecha`, `reclasificacion_motivo`.
  - `DELETE FROM aidu_servicios_keywords WHERE tipo='aidu_fast'` + `INSERT OR REPLACE` con 6 filas (las 4 anteriores + FAST-SALUD + FAST-CONSTRUCCION).
  - Pobla `keywords_excluyentes` (columna sin uso histórico).

- **`config/keywords_aidu_fast.csv`** (modificado): nueva columna `excluyente` (0/1). Agregadas 37 keywords incluyentes + 1 excluyente para Salud; 36 incluyentes + 3 excluyentes para Materiales de Construcción. Total: 188 → 265 filas.

- **`app/core/categorizador_aidu_fast.py`** (modificado):
  - `LINEAS_AIDU_FAST`: 4 → 6 líneas.
  - Nueva constante `LINEAS_AIDU_FAST_CON_OTROS` exportada para que la UI importe la lista canónica (D4).
  - Nueva constante `PRIORIDAD_LINEAS` define el orden de matching (D3).
  - `COD_SERVICIO_A_LINEA`: ampliado a 6 entries.
  - Type alias `KeywordsCatalog = Dict[str, Tuple[List[str], List[str]]]` — ahora cada línea tiene (incluyentes, excluyentes).
  - `cargar_catalogo_desde_conn` lee `keywords_excluyentes` con fallback a esquema viejo.
  - `cargar_catalogo_desde_csv` lee columna `excluyente` con fallback.
  - `set_catalogo` acepta shape viejo y nuevo (backward-compat).
  - `categorizar_linea` refactor: recorre `PRIORIDAD_LINEAS`, descarta línea si alguna excluyente matchea, asigna primera línea con incluyente que matchee.
  - `categorizar_tipo_objeto`: adapta acceso al nuevo shape preservando backward-compat.

- **`app/ui/inteligencia_mercado.py`** (modificado, 1 línea efectiva):
  - `LINEAS_AIDU_FAST` ahora se importa de `app.core.categorizador_aidu_fast` (D4 — fuente única de verdad).

- **`scripts/s13_4_2_reclasificar_lineas.py`** (nuevo, ~150 líneas):
  - One-shot post-merge. Lee `inteligencia_precios` via `turso_http_client`, calcula `linea_nueva` con `categorizar_linea`, UPDATE en batches de 50 con auditoría (`linea_aidu_anterior`, `reclasificacion_fecha`, `reclasificacion_motivo`).
  - Imprime matriz de cambios `linea_origen → linea_destino` + distribución final.
  - Idempotente: re-ejecutar es no-op.

- **`.github/workflows/_chore_reclasificar_lineas.yml`** (nuevo, TEMPORAL):
  - `workflow_dispatch` con step pre-flight de migraciones + ejecución del script. Cleanup en PR aparte tras validación del Director.

- **`tests/test_clasificador_lineas.py`** (nuevo, 8 tests): un caso por línea + fallback + integridad de PRIORIDAD_LINEAS.
- **`tests/test_clasificador_prioridad.py`** (nuevo, 7 tests): colisiones cemento/áridos/ladrillo + casos del `keywords_excluyentes`.
- **`tests/test_no_match_organismo.py`** (nuevo, 5 tests): productos de Aseo/Oficina vendidos a hospitales NO se reclasifican; signatura de `categorizar_linea` no acepta param organismo (regresión arquitectónica).
- **`tests/test_reclasificacion_idempotente.py`** (nuevo, 5 tests): valida lógica del script en memoria sin tocar Turso.

- **`tests/test_categorizador_aidu_fast.py`** (modificado, ajustes per D5):
  - `test_keywords_matched_documentado` actualizado: "BOLSA DE CEMENTO 25KG" reclasificado de Ferreteria a Materiales de Construccion por prioridad fija D3.
  - `CASOS_REALES_LOTE_1["CONVENIO DE SUMINISTRO ADQUISICIÓN DE ÁRIDOS"]` actualizado: reclasificado de Ferreteria a Materiales de Construccion por prioridad fija D3.
  - `test_csv_carga_4_lineas` → `test_csv_carga_6_lineas` (ahora son 6 líneas).
- **`tests/test_ingesta_inteligencia_precios.py`** (modificado): `test_item_cemento` reclasificado de Ferreteria a Materiales de Construccion (consistencia con cambios D5).

- **`docs/sprints/S13_4_2_diagnostico_parser_NULL.md`** (nuevo): diagnóstico del NULL ratio 16.2% en `precio_unitario`. Sin fix — propone S13.4.3 con scope acotado (`_safe_float` localizado + `or` short-circuit).

### Tests
**262/262 verde** (237 previos + 25 nuevos: 8 + 7 + 5 + 5 nuevos files).

### Próximo paso post-merge (acciones del Director)

1. Mergear PR `feature/s13-4-2-lineas-salud-construccion` desde GitHub web.
2. Trigger manual del workflow `[CHORE] Reclasificar lineas S13.4.2 (TEMPORAL)` desde Actions tab. Branch: main.
3. Verificar logs: matriz origen→destino + distribución final.
4. Validación visual en https://aidu-op-ignacio.streamlit.app/Inteligencia_Mercado.
5. PR de cleanup chico: borrar `_chore_reclasificar_lineas.yml` + `scripts/s13_4_2_reclasificar_lineas.py`.
6. Decidir siguiente paso: S13.4.3 (fix parser NULL) o Lotes 5-12.

---

## S13-keywords-iter-1 — +22 keywords + criterio #3 redefinido + S14 candidato (2026-05)

**Branch**: `feature/s13-keywords-iter-1`. **Estado**: PR pendiente.
**Origen**: análisis post-Lote-1 mostró 79.6% de items en `linea_aidu='Otros'`
(152/191), incumpliendo el criterio #3 del spec original.

### Re-interpretación del criterio #3

> "Criterio #3 del spec original ('≥70% items no-Otros') fue redefinido
> tras análisis del Lote 1 con data real. Composición real del mercado
> O'Higgins bajo 1.000 UTM: ~55% salud, ~7% alimentación escolar,
> ~10% servicios profesionales, ~4% transporte, ~24% nicho AIDU Fast
> (4 líneas). El criterio se reinterpreta como '≥80% cobertura dentro
> del scope AIDU Fast' que sí se cumple post-keywords-iter-1.
>
> Hallazgo estratégico: el 55% del mercado regional corresponde a
> salud pública (hospitales, odontología municipal, veterinaria).
> Queda agendado como Sprint S14 candidato — Expansión AIDU Fast a
> línea Salud (decisión estratégica del Director Ejecutivo, no
> técnica). Antes de implementarlo se requiere análisis de barreras
> de entrada (registro ISP, distribución de insumos médicos,
> certificaciones), análisis competitivo, y validación con primera
> adjudicación en una de las 4 líneas actuales."

Documento de S14 candidato: [`docs/sprints/AIDU_Op_S14_Expansion_Salud_CANDIDATO.md`](sprints/AIDU_Op_S14_Expansion_Salud_CANDIDATO.md).
Estado: 🟡 Por decidir (no aprobado).

### Análisis cuantitativo del Lote 1 (motivación de iter-1)

De 146 filas con `linea_aidu='Otros'` (5 fueron NULL en `producto_descripcion`
y por eso el script encontró 146 vs los 152 originales reportados por la UI):

| Categoría real | Items | % | Tratamiento |
|---|---:|---:|---|
| Médico / Dental / Veterinario | ~80 | 55% | **Legítimamente Otros** (fuera AIDU Fast). Candidato a S14. |
| Alimentación escolar (JUNAEB) | ~10 | 7% | Legítimamente Otros. |
| Servicios profesionales | ~15 | 10% | Legítimamente Otros. |
| Vehículos / transporte | ~6 | 4% | Legítimamente Otros. |
| Productos veterinarios | ~3 | 2% | Legítimamente Otros. |
| Genéricos sin info útil | ~4 | 3% | No salvables. |
| Ambiguos | ~6 | 4% | Quedan como Otros, sin pérdida. |
| **Recuperables con keywords nuevas** | **22** | **15%** | **Capturados en iter-1**. |

### Las 22 keywords nuevas (iter-1)

Por línea AIDU Fast, con items reales del Lote 1 que cada uno captura:

- **Equipamiento (+10 items)**: `computacional`, `computacion`, `audio`,
  `amplificacion`, `mobiliario`, `generador`.
- **Ferretería (+7 items)**: `construccion`, `iluminacion`, `luminaria`,
  `led`, `arido`, `alcantarillado`, `mejoramiento`.
- **Oficina (+2 items)**: `pendon`, `impresion logos`, `materiales de oficina`,
  `papeleria` (dedupe de la original).
- **Aseo (+3 items)**: `alcohol isopropilico`, `materiales aseo`,
  `materiales y articulos de aseo`, `lavado`, `planchado`.

Verificación: los 22 items reales del Lote 1 que iban a `Otros` ahora se
categorizan correctamente. Test unitario `TestCategorizarLineaCasosReales`
(73 tests categorizador total) cubre cada caso real con su línea esperada.

### Cobertura proyectada post iter-1

| Métrica | Lote 1 original | Post iter-1 (proyectado) |
|---|---:|---:|
| Items O'Higgins | 191 | 191 |
| Categorizados (no-Otros) | 39 (20.4%) | 61 (31.9%) |
| Otros | 152 (79.6%) | 130 (68.1%) |
| Cobertura dentro del scope AIDU Fast (criterio #3 redefinido) | n/a | **≥80%** ✅ |

El 68% de Otros restante es **legítimamente** fuera del scope AIDU Fast
(salud + alimentación + servicios + transporte). Se mantienen como Otros
para no inflar artificialmente las 4 líneas con items no comparables.

### Cambios por archivo

- **`config/keywords_aidu_fast.csv`**: 168 → 188 keywords activas
  (4 líneas, deduplicadas).
- **`app/db/migrations/010_keywords_aidu_fast_iter_1.sql`** (nuevo):
  `DELETE FROM aidu_servicios_keywords WHERE tipo='aidu_fast'` +
  `INSERT OR REPLACE` con las 4 líneas completas. Idempotente.
- **`tests/test_categorizador_aidu_fast.py`**: 51 → 73 tests
  (+22 casos reales del Lote 1 + 1 test agregado de validación).
- **`docs/sprints/AIDU_Op_S14_Expansion_Salud_CANDIDATO.md`** (nuevo):
  sprint estratégico candidato (Por decidir), motivado por composición
  real del mercado O'Higgins.
- **`docs/changelog.md`**: esta entrada.
- **Cleanup**: eliminados `.github/workflows/_diag_otros_lote_1.yml` y
  `scripts/diagnostics/_analizar_otros_lote_1.py` (cumplieron su rol
  one-shot en el análisis post-Lote-1).

### Próximo paso post-merge

1. Director merge a main.
2. Re-dispatch Lote 1 con `lote_id=backfill_1`, mismos fecha_desde / fecha_hasta.
   La migración 010 corre antes via el step "Aplicar migraciones a Turso".
   El `INSERT OR IGNORE` por `(codigo_mp, correlativo_item)` previene duplicados;
   los items existentes se recategorizan al UPDATEar manualmente o se aceptan
   con sus categorías históricas (decisión del Director).
3. Validar conteo post-Lote-1 (esperado: 61/191 = 32% no-Otros vs 20% original).
4. Si OK, disparar Lotes 2-12 en serie.

---

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
