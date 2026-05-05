# Migración inicial de datos a Turso (S12.1.5)

Este documento describe el paso manual que el Director Ejecutivo debe ejecutar
**una sola vez, post-merge a `main`** del PR `feature/s12-1-5-schema-fix`,
para volcar el schema completo y el estado inicial de datos hacia la BD remota
Turso `aidu-op-prod`.

Reemplaza al procedimiento basado en `turso db shell` de S12.1: en S12.1.5 el
bootstrap se ejecuta por código Python contra el endpoint HTTP `/v2/pipeline`
de Turso, sin depender de la CLI `turso` ni de SQLite client local.

Sin este paso, la BD remota Turso queda con schema vacío. La app aparenta
funcionar pero corre contra el fallback `data_semilla/ → /tmp` y los datos
no persisten entre reboots — el bug que motivó este sprint.

## Pre-requisitos

1. PR `feature/s12-1-5-schema-fix` mergeado en `main` y deploy de Streamlit
   Cloud completado.
2. La base `aidu-op-prod` ya creada en Turso (esto fue paso del sprint S12.1).
3. Credenciales `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN` cargadas en
   Streamlit Cloud → App settings → Secrets.
4. `requirements.txt` instalado en el entorno local desde donde se corre el
   bootstrap (incluye `requests`, dependencia del script).
5. Estar parado en la raíz del repo local `aidu-op`, en la rama `main` ya
   sincronizada (`git pull origin main`).

## Comando único

En PowerShell, en la raíz del repo:

```powershell
$env:TURSO_DATABASE_URL = "libsql://aidu-op-prod-...turso.io"
$env:TURSO_AUTH_TOKEN = "<token desde Streamlit Secrets>"
python docs/migracion_inicial_turso.py
```

(En bash/zsh: usar `export` en lugar de `$env:`.)

El script:
1. Aplica las 7 migraciones de `app/db/migrations/*.sql` directamente a Turso
   (DDL → /v2/pipeline). Idempotente: tolera "already exists".
2. Vuelca todas las filas de `data_semilla/aidu_op.db` a Turso, tabla por
   tabla. Skipea cualquier tabla que ya tenga >0 filas en Turso.
3. Inserta las 12 categorías de `SEED_HOMOLOGACION` (constante en
   `app/core/homologacion.py`) en `aidu_homologacion_categoria`. Esta tabla
   no vive ni en `data_semilla/` ni en las migraciones SQL — ver nota abajo.
4. Verifica los criterios de éxito del sprint (3 conteos esperados) y reporta
   `✨ Bootstrap completado` o sale con código 2 si hay discrepancia.

Tiempo aproximado: 30-90 segundos según latencia a Turso.

## Conteos esperados (criterio #2 del sprint)

| Tabla | Conteo |
| --- | --- |
| `mp_licitaciones_adj` | 19 |
| `aidu_homologacion_categoria` | 12 |
| `aidu_proyectos` | 4 |

Otros conteos que el script también puede generar (no son criterio formal,
solo referencia):

| Tabla | Conteo |
| --- | --- |
| `aidu_servicios_keywords` | 14 |
| `mp_categorizacion_aidu` | 48 |
| `aidu_parametros` | 7 |
| `_migrations` | 7 (una por archivo de migración) |

## Validación end-to-end

1. Después del bootstrap exitoso, abrir Turso Studio y confirmar:
   - 13 tablas listadas (criterio #1).
   - Storage > 200 KB (criterio #3).
   - Activity tab muestra Rows Written > 0.
2. En la app Streamlit, forzar reboot (App settings → Reboot app) y
   verificar que el dashboard muestra los conteos esperados sin warnings
   "no such table".
3. Forzar segundo reboot. Datos siguen ahí (criterio #5) y Turso Activity
   muestra Rows Read > 20 (criterio #6).
4. Abrir Panel ADMIN → Sistema y confirmar que `validate_db()` reporta
   `status='ok'`, `conexion_tipo='turso'`, `criticas_ok=7` (criterio #7).

## Si algo falla

- **`Faltan TURSO_DATABASE_URL o TURSO_AUTH_TOKEN`**: variables de entorno
  no seteadas. Volver al paso "Comando único" y verificar que `$env:`
  realmente las exportó (`echo $env:TURSO_AUTH_TOKEN` debe imprimir el JWT,
  no vacío).
- **`HTTP 401 desde Turso`**: token inválido o expirado. Regenerar con
  `turso db tokens create aidu-op-prod` y actualizarlo en Streamlit Secrets.
- **`Falla en 00X_xxx.sql`** durante apply_migrations: el SQL tiene un
  statement que Turso no acepta y no es "already exists". Ver el `stmt`
  reportado y el `error` arriba.
- **Conteos finales no coinciden**: el script termina con código 2 e imprime
  qué tabla difirió. Verificar `data_semilla/aidu_op.db` localmente
  (`sqlite3 data_semilla/aidu_op.db "SELECT COUNT(*) FROM mp_licitaciones_adj"`).

## Re-ejecutar el bootstrap

El script es idempotente: si necesitás re-correrlo (por ejemplo después de
un cambio en migraciones, o tras dropear tablas en Turso para resetear),
ejecutarlo de nuevo es seguro. Migraciones DDL pasan a "already exists" sin
ruido; tablas con datos existentes se skippean.

## Sobre `aidu_homologacion_categoria`

Las 12 filas de esta tabla viven como constante `SEED_HOMOLOGACION` en
[`app/core/homologacion.py:36`](../app/core/homologacion.py). En la app,
se vuelcan vía `seed_homologacion()` la primera vez que el usuario abre el
panel de homologación. El bootstrap las inserta directamente en Turso para
que la tabla quede inicializada antes del primer arranque post-merge.

Si en el futuro se decide mover este seed al archivo `data_semilla/aidu_op.db`,
el script lo detecta automáticamente: `dump_seed` carga la tabla del seed
y `insert_homologacion` skippea por idempotencia (tabla ya con filas).

## Reactivación del cron (S12.2)

El workflow `.github/workflows/descarga_mp_diaria.yml` permanece desactivado
(`.yml.disabled`) en este sprint. La reactivación apuntando directamente a
Turso es S12.2.
