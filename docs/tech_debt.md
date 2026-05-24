# Deuda técnica AIDU Op

Registro abierto de issues de deuda técnica detectados durante sprints.
Cada item es out-of-scope del sprint en el que se descubrió y se agenda
para ejecución futura sin fecha comprometida.

Formato: `TD-NN — Título corto`. Estados: `abierto`, `en curso`, `cerrado`.

---

## TD-01 — Utilidad común UTF-8 stdout wrapper

**Detectado en**: Sprint S13.0 (2026-05-21).
**Estado**: abierto.
**Origen**: `scripts/_seed_organismos_ohiggins.py` crasheó con
`UnicodeEncodeError: 'charmap' codec can't encode character '✓'`
en Windows cp1252. Tercer script en aparecer este bug (los previos:
`_recon_s13_*` durante reconnaissance, `_recon_agil_check.py` durante
spike S13.0a). Cada uno aplica el wrapper ad-hoc en su prólogo, lo
que es duplicación de código y olvidable.

### Alcance

Crear `app/utils/console.py` con función `setup_utf8_console()`:

```python
# app/utils/console.py
import sys
import io

def setup_utf8_console() -> None:
    """Idempotente. Envuelve stdout/stderr en UTF-8 para evitar el
    crash de cp1252 en Windows cuando se imprimen caracteres no-Latin-1.

    Llamar como PRIMERA instruccion del entry point de cualquier
    script CLI. Tambien aplicable a app/cli.py.
    """
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None or getattr(stream, "encoding", "").lower() == "utf-8":
            continue
        try:
            setattr(sys, stream_name, io.TextIOWrapper(
                stream.buffer, encoding="utf-8", errors="replace"
            ))
        except Exception:
            pass
```

### Trabajo asociado

1. Crear `app/utils/__init__.py` y `app/utils/console.py`.
2. Refactor de los call sites ad-hoc:
   - `scripts/diagnostics/_recon_agil_check.py` (líneas iniciales).
   - `scripts/_seed_organismos_ohiggins.py` (líneas 28-36, una vez se
     elimine el script post-S13).
   - `app/cli.py` (revisar si imprime caracteres no ASCII).
   - `scripts/backfill_mvp_3m.py` (revisar).
   - `scripts/cargar_inteligencia_ohiggins.py` (NUEVO en S13 — debe
     usar la utilidad desde el día 1).
3. Test unitario `tests/test_console_utf8.py` que valida el wrapper
   sin romper en sistemas con stdout ya UTF-8 (Linux/macOS).
4. Doc en `docs/changelog.md` bajo el sprint donde se cierre.

### Out of scope explícito

- Cambiar el manejo de encoding en módulos no-CLI (`app/api/`, `app/core/`,
  `app/db/`). El bug solo aparece en entry points que escriben a consola
  Windows.
- Soporte para PowerShell vs cmd.exe (ambos heredan cp1252 por default
  en builds históricos; el wrapper los cubre a ambos).

### Acciones del Director

- [ ] Asignar TD-01 a un sprint futuro (sugerencia: S13.x o S14
      durante la migración de scripts a un patrón unificado).
- [ ] Si se difiere indefinidamente: aceptar que cada nuevo script CLI
      debe replicar el wrapper en su prólogo. Riesgo: la próxima vez
      que un script omita el wrapper crashea en Windows en runtime —
      patrón ya repetido 3 veces.

---

## TD-02 — Unificar 3 callers de Claude API en `app/core/analisis_*.py` al cliente canónico `app/api/claude_client.py`

**Detectado en**: Sprint S13.4.3 reconnaissance (2026-05-25).
**Estado**: abierto.
**Origen**: durante reconnaissance del sprint S13.4.3 se identificó que ya
existían 3 módulos en `app/core/` que llaman directamente a Claude API
duplicando el patrón `anthropic.Anthropic(api_key=...) + client.messages.create()`:

| Archivo | Línea | Modelo hardcoded |
|---|---|---|
| `app/core/analisis_ia.py` | 87 | `claude-sonnet-4-5` |
| `app/core/analisis_bases.py` | 276 | `claude-sonnet-4-5` |
| `app/core/analisis_masivo.py` | 132 | `claude-sonnet-4-5-20250929` |

S13.4.3 introdujo el cliente canónico `app/api/claude_client.py` con
`llamar_claude_json()` + override del modelo vía env var
`CLAUDE_MODEL_CLASIFICADOR`. **El sprint NO refactorizó los 3 callers
existentes** para mantener scope acotado.

### Alcance del refactor

1. En cada uno de los 3 módulos: reemplazar el bloque
   `anthropic.Anthropic(api_key=...) + client.messages.create(model=..., ...)`
   por una llamada al cliente canónico:
   ```python
   from app.api.claude_client import llamar_claude_json, get_client
   # ... o usar get_client() directamente cuando se necesita streaming
   ```
2. Definir un parámetro `model: Optional[str] = None` en cada función;
   default a `config.settings.get_modelo_clasificador()` o un nuevo
   `get_modelo_analisis()` por consistencia.
3. Eliminar imports duplicados de `anthropic` que ya no se usen.
4. Tests: verificar que las 3 funciones siguen pasando con el mock
   centralizado en el cliente canónico.

### Riesgo

- `analisis_masivo.py` usa `system` parameter y un `messages.create()`
  con `system=...`. El cliente canónico ya soporta `system=` opcional.
- Algunos callers usan `max_tokens` distintos (1500/4096/2500). Pasarlos
  como argumento explícito al cliente canónico (parámetro existente).

### Out of scope explícito

- Cambiar la lógica de prompts de los 3 módulos (eso es S14 o sprint
  comercial — no técnico).
- Migrar los modelos a uno solo (cada caso de uso puede mantener su
  modelo si hay justificación).

### Acción del Director

- [ ] Asignar TD-02 a un sprint futuro de cleanup técnico.

---

## TD-03 — Formato de `confidence_score` en Excel exportado

**Detectado en**: Sprint S13.4.4 reconnaissance (2026-05-24).
**Estado**: abierto.
**Origen**: side-finding del reconnaissance que demostró que el Excel
descargable YA tiene las 17 columnas (incluyendo `confidence_score`,
`clasificacion_metodo`, `es_producto_granular`). Inconsistencia
cosmética detectada: el DataFrame de la UI muestra confidence como
porcentaje legible (`"85%"`) gracias al transform en
`app/ui/inteligencia_mercado.py:471-474`, pero el Excel exporta el
float crudo (`0.85`) porque usa `df_filtrado[cols_validas]` y no la
copia `df_display`.

### Alcance

Si el Director quiere consistencia visual UI ↔ Excel:

1. En `_render_tab_buscador`, construir un `df_export` separado que
   aplique el mismo formato de `df_display` (porcentaje legible) antes
   del `_df_a_excel_bytes`.
2. O bien, dejar el float crudo y agregar formateo de celda Excel
   (porcentaje vía openpyxl number_format) para que abra como % en
   Excel pero quede number nativo.

### Riesgo

- Opción 1 convierte `confidence_score` en string en el Excel —
  pierde la capacidad de ordenar/filtrar numéricamente en Excel.
- Opción 2 mantiene number nativo pero requiere import de
  openpyxl.styles y un loop por fila → más código.

### Recomendación

Opción 2 (number_format) para no perder filtrabilidad. Pero **NO hay
fix por ahora** — esperando decisión del Director.

### Acción del Director

- [ ] Decidir entre opción 1 (string `"85%"`), opción 2 (formato
      Excel porcentaje) o dejar como está (float crudo).

---

## TD-04 — Falsos positivos `es_producto_granular=True` en descripciones de bloque

**Detectado en**: Sprint S13.4.4 reconnaissance (2026-05-24).
**Estado**: abierto.
**Origen**: side-finding del Director durante auditoría manual del Excel
descargable post-S13.4.3. Aproximadamente 58 items pasan el filtro
`es_producto_granular=True` (lo marca el clasificador semántico) pero
tienen `cantidad=1` y descripciones de tipo "agregado global":

- "Ver listado anexo"
- "Línea 1", "Línea 2", ...
- "Según TDR"
- "Detalle adjunto"

Estos NO son granulares para análisis comercial — son una sola línea
contractual que apunta a múltiples items reales. El prompt del
clasificador semántico (`app/core/clasificador_semantico.py`
`PROMPT_TEMPLATE`) no contiene un anti-patrón explícito para descripciones
que delegan el detalle a un archivo externo.

### Alcance del refinamiento

1. Agregar al `PROMPT_TEMPLATE` una regla negativa explícita:
   > "Si la descripción del producto remite a un archivo/anexo/listado
   > externo sin describir un producto concreto (ej: 'ver listado',
   > 'según TDR', 'anexo N', 'línea N'), marcar
   > `es_producto_granular=false`. La cantidad=1 con monto grande es
   > una señal débil pero no suficiente — debe haber producto descrito."
2. Re-correr el script de reclasificación con `--force` sobre el
   subset de items que matcheen estos patrones de descripción (no todos
   los 687) para minimizar costo.
3. Tests golden en `tests/test_es_producto_granular.py` con los
   casos del Director.

### Riesgo

- Re-clasificar puede tocar items que no son problemáticos. Mitigar:
  filtrar el subset con `WHERE producto_descripcion REGEXP ...` antes
  del script.
- El prompt actualizado debe seguir aceptando productos legítimos con
  descripción corta. Validar con golden tests primero.

### Out of scope explícito

- Cambiar el modelo (`claude-sonnet-4-5` sigue siendo válido).
- Rehacer la migración 012 (las 3 columnas siguen siendo correctas).

### Acción del Director

- [ ] Asignar TD-04 a un sprint futuro (probablemente S14 si el
      análisis comercial Salud lo requiere para limpiar input).

---
