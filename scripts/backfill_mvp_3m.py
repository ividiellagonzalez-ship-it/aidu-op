"""
AIDU Op · CLI del backfill MVP S12.3 v2.2
==========================================
Wrapper fino sobre `app.core.backfill_fases_mvp.ejecutar_backfill_mvp`.
Sin lógica de negocio acá — solo parsing de argumentos, defaults
sensatos para el MVP, y mapeo de excepciones a exit codes.

Uso
---
    python -m scripts.backfill_mvp_3m \
        --fecha-desde 2026-02-10 \
        --fecha-hasta 2026-05-10 \
        --regiones II,V,RM,VI,X \
        --tipos CA,L1,LE

    python -m scripts.backfill_mvp_3m --dry-run

    python -m scripts.backfill_mvp_3m --fases cabecera,vigentes

Diseño futuro
-------------
Este mismo script debe correr S12.3.1 (expansión a 6m) y S12.3.2
(expansión a 12m) sin modificación. Solo cambia `--fecha-desde`:

    # S12.3.1 (6 meses):
    python -m scripts.backfill_mvp_3m --fecha-desde 2025-11-10

    # S12.3.2 (12 meses):
    python -m scripts.backfill_mvp_3m --fecha-desde 2025-05-10

Idempotencia garantizada vía `INSERT OR IGNORE` en el path HTTP:
re-ejecutar el mismo período NO duplica filas.

Exit codes (alineados con S12.2.1):
    0 = backfill completo, todas las fases solicitadas ejecutadas.
    1 = error API ChileCompra (MercadoPublicoAPIError, rate limit, etc.).
    2 = error en Turso (TursoUnavailableError tras reintentos). Sin
        fallback a SQLite. Datos en memoria descartados.
    3 = error inesperado (con traceback al stderr).
"""
from __future__ import annotations

import argparse
import logging
import sys
import traceback
from datetime import date, datetime, timedelta
from typing import List

from app.core.backfill_fases_mvp import (
    BackfillMvpError, FASES_DEFAULT, ejecutar_backfill_mvp,
)
from app.core.descarga_diaria import MercadoPublicoAPIError
from app.db.exceptions import TursoUnavailableError


# Defaults del MVP (S12.3 v2.2):
# - Ventana 3 meses: hoy - 90 días → hoy.
# - 5 regiones target del sprint: II, V, RM, VI, X.
# - 3 tipos: CA (= AGIL), L1, LE (< 1000 UTM).
# - 6 fases canónicas.
# Diseño futuro: todos parametrizables vía CLI. Nada hardcoded a "3 meses".
_DEFAULT_DIAS_ATRAS = 90
_DEFAULT_REGIONES = "II,V,RM,VI,X"
_DEFAULT_TIPOS = "CA,L1,LE"


def _parse_fecha(s: str) -> date:
    """Parse YYYY-MM-DD a date. Levanta ValueError con mensaje claro."""
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"Fecha inválida {s!r}: esperaba YYYY-MM-DD ({e})"
        )


def _parse_lista(s: str) -> List[str]:
    """Parse 'a,b,c' a ['a','b','c'], strippeando whitespace y vacíos."""
    return [item.strip() for item in s.split(",") if item.strip()]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="backfill_mvp_3m",
        description=(
            "Backfill MVP S12.3 v2.2 — pobla licitaciones MP de los últimos "
            "N días (default 90) contra Turso, filtrado por tipo + región. "
            "Reutilizable para S12.3.1 (6m) y S12.3.2 (12m) sin modificar."
        ),
    )
    hoy = date.today()
    p.add_argument(
        "--fecha-desde", type=_parse_fecha,
        default=hoy - timedelta(days=_DEFAULT_DIAS_ATRAS),
        help=f"Primer día inclusive (YYYY-MM-DD). Default hoy - {_DEFAULT_DIAS_ATRAS}d.",
    )
    p.add_argument(
        "--fecha-hasta", type=_parse_fecha, default=hoy,
        help="Último día inclusive (YYYY-MM-DD). Default hoy.",
    )
    p.add_argument(
        "--regiones", type=_parse_lista, default=_parse_lista(_DEFAULT_REGIONES),
        help=f"Códigos de región separados por coma. Default {_DEFAULT_REGIONES!r}.",
    )
    p.add_argument(
        "--tipos", type=_parse_lista, default=_parse_lista(_DEFAULT_TIPOS),
        help=f"Tipos de licitación separados por coma. Default {_DEFAULT_TIPOS!r}.",
    )
    p.add_argument(
        "--fases", type=_parse_lista, default=list(FASES_DEFAULT),
        help=(
            "Fases a ejecutar (subset de: "
            + ",".join(FASES_DEFAULT)
            + "). Default todas, en orden."
        ),
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="No escribe a Turso. Solo loggea volumen estimado.",
    )
    p.add_argument(
        "--batch-size", type=int, default=50,
        help="Filas por petición HTTP. Default 50 (validado en S12.2.2).",
    )
    p.add_argument(
        "--save-raw", action="store_true",
        help="Guarda JSONs crudos en data/raw/. Default False para no llenar disco.",
    )
    return p


def _main(argv=None) -> int:
    # El cron en GitHub Actions corre Linux con UTF-8 nativo, pero
    # `python -m scripts.backfill_mvp_3m` desde Windows usa cp1252 por
    # default y los emojis de los prints (🚀, 📊) revientan con
    # UnicodeEncodeError. Forzar UTF-8 al stdout es seguro en ambos.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
    )

    if args.fecha_desde > args.fecha_hasta:
        print(
            f"❌ --fecha-desde ({args.fecha_desde}) debe ser ≤ --fecha-hasta "
            f"({args.fecha_hasta}).",
            file=sys.stderr,
        )
        return 3

    print(
        f"🚀 Backfill MVP S12.3 v2.2 — "
        f"{args.fecha_desde} → {args.fecha_hasta} "
        f"({(args.fecha_hasta - args.fecha_desde).days + 1} días), "
        f"regiones={args.regiones}, tipos={args.tipos}, "
        f"fases={args.fases}{', DRY-RUN' if args.dry_run else ''}"
    )

    try:
        resultado = ejecutar_backfill_mvp(
            fecha_desde=args.fecha_desde,
            fecha_hasta=args.fecha_hasta,
            regiones_codigos=args.regiones,
            tipos=args.tipos,
            fases=args.fases,
            dry_run=args.dry_run,
            save_raw=args.save_raw,
        )
    except TursoUnavailableError as exc:
        print(
            f"❌ Turso no disponible tras {exc.intentos} reintentos. "
            f"Abortando sin escribir datos. Último error: {exc.ultimo_error}",
            file=sys.stderr,
        )
        return 2
    except MercadoPublicoAPIError as exc:
        print(f"❌ Falla API Mercado Público: {exc}", file=sys.stderr)
        return 1
    except BackfillMvpError as exc:
        # Falla controlada del orquestador (e.g., Fase 1 abortó). Causa
        # raíz ya fue logueada por la fase; aquí se decide el exit code
        # según el tipo subyacente cuando esté disponible.
        cause = exc.__cause__
        if isinstance(cause, TursoUnavailableError):
            print(f"❌ {exc}", file=sys.stderr)
            return 2
        if isinstance(cause, MercadoPublicoAPIError):
            print(f"❌ {exc}", file=sys.stderr)
            return 1
        print(f"❌ {exc}", file=sys.stderr)
        return 3
    except Exception:
        print("❌ Error inesperado en backfill MVP. Traceback:", file=sys.stderr)
        traceback.print_exc()
        return 3

    print("\n📊 Resultado por fase:")
    for fase, datos in resultado.items():
        print(f"  {fase}: {datos}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
