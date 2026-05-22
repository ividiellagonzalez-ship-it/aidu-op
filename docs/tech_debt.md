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
