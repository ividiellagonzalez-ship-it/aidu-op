# Changelog AIDU Op

Registro cronológico de sprints técnicos desde S12. Para sprints previos
ver `docs/sprints/` (notas individuales por sprint) y el log de git.

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
