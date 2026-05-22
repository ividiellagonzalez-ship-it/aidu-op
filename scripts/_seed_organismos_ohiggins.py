"""S13.0 - Genera la semilla `config/organismos_ohiggins.csv`.

Sampling de 7 dias contra la API de Mercado Publico, pegando detalle
de hasta N adjudicadas por dia para descubrir los unit_codes (primer
segmento del CodigoExterno) de organismos de la Region O'Higgins.

NORMALIZACION
-------------
La API devuelve `Region` con apostrofes no estandar (U+00B4 ACUTE
ACCENT, U+2019 RIGHT SINGLE QUOTATION MARK). `normalizar_region()`
los convierte a ASCII U+0027 antes de comparar.

SALIDA
------
config/organismos_ohiggins.csv (deduplicado por unit_code), columnas:
  unit_code,codigo_organismo,nombre_organismo,region_raw,fecha_descubierto

RESUMABILIDAD
-------------
Persistencia incremental:
  - Cada 50 detalles procesados dentro de un dia.
  - Al final de cada dia.
  - Progreso de `dias_procesados` y `codigos_vistos` en
    `scripts/_seed_progress.json` para soportar reanudacion.

DEUDA TECNICA: este script aplica un wrapper UTF-8 ad-hoc en sys.stdout
para evitar el crash de cp1252 en Windows. El fix canonico es agendado
en docs/tech_debt.md TD-01.
"""
# === Fix A: UTF-8 wrapper en stdout/stderr ===
# Aplicado ANTES de cualquier import que pueda imprimir banners.
import sys
import io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import os
import json
import csv
import time
from pathlib import Path
from datetime import date, timedelta
from typing import Dict, Any, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.mercadopublico import MercadoPublicoClient

ROOT = Path(__file__).resolve().parents[1]
CSV_PATH = ROOT / "config" / "organismos_ohiggins.csv"
PROGRESS_PATH = ROOT / "scripts" / "_seed_progress.json"

DIAS_SAMPLE = 7
HOY = date(2026, 5, 21)
MAX_DETALLES_POR_DIA = 250
SAVE_EVERY_N_DETAILS = 50  # Fix C


def normalizar_region(s: str) -> str:
    """Normaliza apostrofes Unicode no estandar a ASCII U+0027."""
    if not s:
        return ""
    return (
        s.lower()
        .replace("´", "'")  # ACUTE ACCENT
        .replace("’", "'")  # RIGHT SINGLE QUOTATION MARK
        .replace("‘", "'")  # LEFT SINGLE QUOTATION MARK
        .replace("`", "'")
        .strip()
    )


def es_ohiggins(region_raw: str) -> bool:
    n = normalizar_region(region_raw)
    return ("o'higgins" in n) or ("libertador" in n)


def cargar_progreso() -> Dict[str, Any]:
    if PROGRESS_PATH.exists():
        try:
            return json.loads(PROGRESS_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"dias_procesados": [], "codigos_vistos": []}


def guardar_progreso(p: Dict[str, Any]) -> None:
    PROGRESS_PATH.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def cargar_csv_existente() -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    if not CSV_PATH.exists():
        return out
    with CSV_PATH.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uc = row.get("unit_code", "").strip()
            if uc:
                out[uc] = row
    return out


def guardar_csv(rows_by_unit: Dict[str, Dict[str, str]]) -> None:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["unit_code", "codigo_organismo", "nombre_organismo", "region_raw", "fecha_descubierto"]
    sorted_rows = sorted(rows_by_unit.values(), key=lambda r: r.get("unit_code", ""))
    with CSV_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in sorted_rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def extraer_entry(det: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(det, dict):
        return None
    if "Listado" in det and isinstance(det["Listado"], list) and det["Listado"]:
        e = det["Listado"][0]
        return e if isinstance(e, dict) else None
    return det


def checkpoint(progreso: Dict[str, Any],
               rows_by_unit: Dict[str, Dict[str, str]],
               codigos_vistos: Set[str],
               dias_done: Set[str]) -> None:
    """Persiste estado intermedio (Fix B + Fix C). ASCII-safe."""
    progreso["dias_procesados"] = sorted(dias_done)
    progreso["codigos_vistos"] = sorted(codigos_vistos)
    guardar_progreso(progreso)
    guardar_csv(rows_by_unit)


def main():
    # Cliente con ticket REAL (desde secrets.env via get_mp_ticket()).
    # NO se pasa ticket explicito: el cliente cae a get_mp_ticket() y luego
    # a MP_TICKET_DEMO solo si la lectura retorna vacio.
    cli = MercadoPublicoClient(save_raw=False)
    if not cli.ticket or cli.ticket.startswith("tu-ticket") or cli.ticket == "F8537A18-6766-4DEF-9E59-426B4FEE2844":
        print("ERROR: MP_TICKET no esta cargado o es DEMO/placeholder.")
        print("       Cargar ticket productivo en ~/AIDU_Op/config/secrets.env.")
        sys.exit(2)
    print(f"Ticket OK (mask={cli.ticket[:4]}...{cli.ticket[-4:]}, len={len(cli.ticket)})")

    progreso = cargar_progreso()
    dias_done: Set[str] = set(progreso.get("dias_procesados", []))
    codigos_vistos: Set[str] = set(progreso.get("codigos_vistos", []))

    rows_by_unit = cargar_csv_existente()
    print(f"CSV inicial: {len(rows_by_unit)} unit_codes")
    print(f"Dias ya procesados: {sorted(dias_done)}")

    dias_a_procesar = [HOY - timedelta(days=i) for i in range(1, DIAS_SAMPLE + 1)]
    print(f"Dias a procesar: {[d.isoformat() for d in dias_a_procesar]}")
    print(f"Persistencia incremental: cada {SAVE_EVERY_N_DETAILS} detalles + al fin de cada dia")
    print()

    t0 = time.time()
    total_ohiggins_dias = 0

    for d in dias_a_procesar:
        d_iso = d.isoformat()
        if d_iso in dias_done:
            print(f"[{d_iso}] ya procesado, skip.")
            continue

        print(f"[{d_iso}] listando adjudicadas...")
        try:
            lst = cli.listar_adjudicadas_por_fecha(d) or []
        except Exception as e:
            print(f"  ERROR listando: {e}")
            continue

        print(f"  N en listado: {len(lst)}. Sampleando hasta {MAX_DETALLES_POR_DIA} detalles.")
        n_ohiggins_dia = 0
        n_procesados = 0

        for lic in lst[:MAX_DETALLES_POR_DIA]:
            codigo = lic.get("CodigoExterno")
            if not codigo or codigo in codigos_vistos:
                continue
            codigos_vistos.add(codigo)
            try:
                det = cli.detalle_licitacion(codigo)
            except Exception as e:
                print(f"  detalle {codigo}: ERROR {e}")
                continue
            entry = extraer_entry(det)
            if not entry:
                continue
            n_procesados += 1
            comp = entry.get("Comprador") or {}
            region_raw = (comp.get("RegionUnidad") or "").strip()

            if es_ohiggins(region_raw):
                unit_code = (codigo.split("-")[0] if isinstance(codigo, str) else "").strip()
                cod_org = (comp.get("CodigoOrganismo") or "").strip()
                nom_org = (comp.get("NombreOrganismo") or "").strip()
                if unit_code and unit_code not in rows_by_unit:
                    rows_by_unit[unit_code] = {
                        "unit_code": unit_code,
                        "codigo_organismo": cod_org,
                        "nombre_organismo": nom_org,
                        "region_raw": region_raw,
                        "fecha_descubierto": HOY.isoformat(),
                    }
                    n_ohiggins_dia += 1
                    # ASCII-only print template; data interpolation goes through UTF-8 wrapper.
                    print(f"    + nuevo: {unit_code} | {nom_org[:60]}")

            # Fix C: checkpoint cada SAVE_EVERY_N_DETAILS detalles
            if n_procesados % SAVE_EVERY_N_DETAILS == 0:
                checkpoint(progreso, rows_by_unit, codigos_vistos, dias_done)
                print(f"    [checkpoint @ {n_procesados} detalles, csv={len(rows_by_unit)} unit_codes]")

        # Fix B: persistir ANTES del print resumen de dia
        dias_done.add(d_iso)
        total_ohiggins_dias += n_ohiggins_dia
        checkpoint(progreso, rows_by_unit, codigos_vistos, dias_done)
        print(f"  [done {d_iso}] procesados={n_procesados}, nuevos en este dia={n_ohiggins_dia}, csv_total={len(rows_by_unit)}")

    elapsed = time.time() - t0
    print()
    print("=" * 60)
    print(f"SAMPLING COMPLETO en {elapsed/60:.1f} min")
    print(f"Total unit_codes unicos en CSV: {len(rows_by_unit)}")
    print(f"Nuevos descubiertos en esta corrida (suma por dia): {total_ohiggins_dias}")
    print(f"CSV: {CSV_PATH}")
    print()
    # Calidad: filas con campos vacios
    sin_nombre = sum(1 for r in rows_by_unit.values() if not r.get("nombre_organismo"))
    sin_region = sum(1 for r in rows_by_unit.values() if not r.get("region_raw"))
    sin_codorg = sum(1 for r in rows_by_unit.values() if not r.get("codigo_organismo"))
    print(f"Calidad CSV:")
    print(f"  sin nombre_organismo: {sin_nombre}")
    print(f"  sin region_raw:       {sin_region}")
    print(f"  sin codigo_organismo: {sin_codorg}  (esperable: el API a veces lo deja vacio)")
    print()
    print("Top organismos (primeros 20 por unit_code):")
    for uc, row in sorted(rows_by_unit.items())[:20]:
        print(f"  {uc:8s}  {row['nombre_organismo'][:60]}")


if __name__ == "__main__":
    main()
