# Changelog AIDU Op

Registro cronológico de sprints técnicos desde S12. Para sprints previos
ver `docs/sprints/` (notas individuales por sprint) y el log de git.

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
