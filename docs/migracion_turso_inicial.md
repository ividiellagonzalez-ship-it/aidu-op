# Migración inicial de datos a Turso (S12.1)

Este documento describe el paso manual que el Director Ejecutivo debe ejecutar
**una sola vez, post-merge a `main`**, para volcar la BD madre actual
(`data_semilla/aidu_op.db`) hacia la base remota Turso `aidu-op-prod`.

Sin este paso, el primer arranque post-deploy crea la replica embebida sobre
una base remota vacía y la app reporta 0 vigentes / 0 adjudicadas. Con este
paso, la base remota queda inicializada con el estado consistente del repo
(13.163 adjudicadas / 4 proyectos / 14 keywords / 48 categorizaciones / etc.)
y el contenedor Streamlit Cloud puede recargarse sin perder datos.

## Pre-requisitos

1. Turso CLI instalado y autenticado (`turso auth login`).
2. La base `aidu-op-prod` ya creada (`turso db create aidu-op-prod`, paso 3
   de la sección 3 del sprint doc).
3. Las credenciales `TURSO_DATABASE_URL` y `TURSO_AUTH_TOKEN` cargadas en
   Streamlit Cloud → App settings → Secrets.
4. Estar parado en la raíz del repo `aidu-op`, en la rama `main` ya con el
   merge de `feature/s12-turso` aplicado.

## Comando único

Genera el dump SQL de la BD semilla y lo aplica contra Turso:

```bash
sqlite3 data_semilla/aidu_op.db .dump | turso db shell aidu-op-prod
```

El dump incluye `CREATE TABLE`, índices, `INSERT` de todas las filas, y la
tabla `_migrations` con el estado de las 7 migraciones aplicadas. La carga
remota toma ~10-20 segundos para los ~180 KB del archivo actual.

## Verificación post-carga

Conectarse a Turso y validar que las tablas y conteos coinciden:

```bash
turso db shell aidu-op-prod
```

Dentro del shell:

```sql
SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;
SELECT COUNT(*) FROM mp_licitaciones_adj;
SELECT COUNT(*) FROM aidu_proyectos;
SELECT COUNT(*) FROM aidu_servicios_keywords;
SELECT filename FROM _migrations ORDER BY id;
```

Resultados esperados según `data_semilla/aidu_op.db` al momento del merge
(verificar antes de correr; el cron diario puede haber agregado filas):

| Tabla | Conteo esperado |
| --- | --- |
| `mp_licitaciones_adj` | 19 (post-rebuild de 13.163 cuando se haga S12.3) |
| `aidu_proyectos` | 4 |
| `aidu_servicios_keywords` | 14 |
| `mp_categorizacion_aidu` | 48 |
| `aidu_parametros` | 7 |
| `_migrations` | 7 |

## Validación end-to-end

1. Forzar reboot del contenedor Streamlit Cloud (App settings → Reboot app).
2. Abrir la app y verificar que el dashboard muestra los conteos esperados,
   no 0 vigentes / 0 adjudicadas.
3. Repetir el reboot — los datos deben persistir entre reboots (este es el
   bug que S12.1 resuelve).

## Si algo falla

- **`turso: command not found`**: instalar la CLI con
  `curl -sSfL https://get.tur.so/install.sh | bash`.
- **`Error: 401 Unauthorized`** al ejecutar `turso db shell`: re-loguearse con
  `turso auth login` o regenerar el token con
  `turso db tokens create aidu-op-prod` y actualizarlo en Streamlit Secrets.
- **Conteos cero post-carga**: revisar que el dump no haya quedado vacío
  (`sqlite3 data_semilla/aidu_op.db .dump | wc -l` debe ser >> 100).
- **App sigue reportando 0 después del reboot**: confirmar en logs de
  Streamlit Cloud que el sync con Turso no está fallando — `migrator.py`
  loguea `❌ Turso no disponible, opero contra SQLite local: ...` cuando cae
  al fallback.

## Reactivación del cron (S12.2)

El workflow `.github/workflows/descarga_mp_diaria.yml` quedó desactivado en
este sprint (renombrado a `.yml.disabled`) para evitar conflicto entre el
commit-back de la BD SQLite a `data_semilla/` y las escrituras a Turso. La
reactivación apuntando directamente a Turso es parte del sprint S12.2.
