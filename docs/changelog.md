# Changelog AIDU Op

Registro cronológico de sprints técnicos desde S12. Para sprints previos
ver `docs/sprints/` (notas individuales por sprint) y el log de git.

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
