"""TEMPORAL · REPRODUCTOR DE ISSUE S13.1 · NO MERGEAR A MAIN

Spike diagnóstico del endpoint AGIL de Mercado Público.

Este script reproduce el hallazgo que dio origen al sprint independiente
S13.1 ("Restaurar descarga de Compras Ágiles", ver
`docs/sprints/AIDU_Op_S13_1_Restaurar_Compras_Agiles.md`):

  Con ticket productivo, las 5 variantes razonables de URL × 3 formatos
  de fecha devuelven HTTP 404 desde `api.mercadopublico.cl`, mientras
  que el endpoint principal `/licitaciones.json` responde 200 OK con
  el mismo ticket. El cliente actual (`app/api/mercadopublico.py`)
  trata el 404 como warning silencioso, por lo que el cron diario
  reporta "OK · 0 nuevas" en lugar de fallar.

OBJETIVO
========
Mantener un reproductor minimal del bug para:
  - Validar fixes futuros del nuevo endpoint AGIL antes de mergear S13.1.
  - Detectar si MercadoPúblico restablece el endpoint anterior (regreso
    a HTTP 200 sin cambio de URL).

Cuando S13.1 cierre con merge a main, ESTE ARCHIVO Y EL DIRECTORIO
`scripts/diagnostics/` ENTERO se eliminan.

CÓMO USAR
=========
1. MP_TICKET real cargado en ~/AIDU_Op/config/secrets.env.
2. python -m scripts.diagnostics._recon_agil_check
3. Revisar veredicto preliminar (escenarios a/b/c).

Resultado conocido al cierre del spike (2026-05-21):
  - Escenario (b): 15/15 combinaciones HTTP 404. AGIL fuera de S13.

NO PERSISTE nada en BD ni cachea respuestas; solo imprime diagnóstico.
"""
import sys
import os
import io
import json
import time
import requests
from pathlib import Path
from datetime import date, timedelta
from typing import Dict, Any, List, Tuple

# Forzar UTF-8 en stdout/stderr para que los emojis no rompan la consola Windows (cp1252).
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.settings import (
    MP_API_AGIL_BASE,
    MP_API_BASE,
    MP_TICKET_DEMO,
    MP_REQUEST_TIMEOUT,
    get_mp_ticket,
)


FECHAS_TEST = [
    date(2026, 5, 19),   # día reciente (martes)
    date(2026, 5, 5),    # 2 semanas atrás
    date(2026, 4, 14),   # ~5 semanas atrás
]

# Variantes de URL y formato de fecha a probar
URL_VARIANTS = [
    ("AGIL/listar (config actual)", f"{MP_API_AGIL_BASE}/listar"),
    ("APISOCDS/AGIL/listar (literal del cliente)", "https://api.mercadopublico.cl/APISOCDS/AGIL/listar"),
    ("apisocds/agil/listar (lowercase)", "https://api.mercadopublico.cl/apisocds/agil/listar"),
    ("api/AGIL/listar (sin SOCDS)", "https://api.mercadopublico.cl/api/AGIL/listar"),
    ("servicios/v1/publico/AGIL/listar (path v1)", "https://api.mercadopublico.cl/servicios/v1/publico/AGIL/listar"),
]

DATE_FORMATS = [
    ("DD-MM-YYYY", "%d-%m-%Y"),  # formato actual del cliente
    ("DDMMYYYY",   "%d%m%Y"),    # formato del endpoint principal
    ("YYYY-MM-DD", "%Y-%m-%d"),  # ISO
]


def _mask_ticket(t: str) -> str:
    if not t:
        return "<vacio>"
    if len(t) <= 10:
        return f"<short:{len(t)}>"
    return f"{t[:4]}...{t[-4:]}"


def _is_placeholder(t: str) -> bool:
    return (not t) or t.startswith("tu-ticket") or t == MP_TICKET_DEMO


def _probe(url: str, params: Dict[str, Any], timeout: int = 20) -> Tuple[int, str, Dict[str, str]]:
    """Devuelve (status, body_truncated, headers_relevantes)."""
    try:
        resp = requests.get(
            url,
            params=params,
            timeout=timeout,
            headers={
                "User-Agent": "AIDU-Op/1.0 S13-recon (Python; aidu.op@gmail.com)",
                "Accept": "application/json",
            },
        )
        body = resp.text[:400]
        relevant_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() in {"content-type", "x-ratelimit-remaining", "x-ratelimit-limit", "retry-after", "server", "location"}
        }
        return resp.status_code, body, relevant_headers
    except requests.RequestException as e:
        return -1, f"<network error: {type(e).__name__}: {e}>", {}


def _parse_payload(body: str) -> Dict[str, Any]:
    """Intenta parsear body como JSON; reporta tipo y volumen si lo logra."""
    try:
        data = json.loads(body)
    except Exception:
        return {"parsed": False}
    info = {"parsed": True, "type": type(data).__name__}
    if isinstance(data, list):
        info["len"] = len(data)
        if data and isinstance(data[0], dict):
            info["first_keys"] = list(data[0].keys())[:8]
    elif isinstance(data, dict):
        info["top_keys"] = list(data.keys())[:8]
        for cand in ("data", "Listado", "items", "results"):
            v = data.get(cand)
            if isinstance(v, list):
                info[f"{cand}_len"] = len(v)
                if v and isinstance(v[0], dict):
                    info[f"{cand}_first_keys"] = list(v[0].keys())[:8]
                break
    return info


def main():
    ticket = get_mp_ticket() or ""
    using_placeholder = _is_placeholder(ticket)

    print("=" * 70)
    print("S13.0 SPIKE — DIAGNÓSTICO ENDPOINT AGIL")
    print("=" * 70)
    print(f"Ticket cargado: {_mask_ticket(ticket)}  (placeholder={using_placeholder})")
    print(f"Fechas a probar: {[d.isoformat() for d in FECHAS_TEST]}")
    print()

    if using_placeholder:
        print("⚠️  El ticket en secrets.env es placeholder o DEMO.")
        print("    Cargar el ticket productivo real antes de correr este spike.")
        print("    El spike puede continuar pero los resultados NO son concluyentes")
        print("    para el escenario (a) vs (b).")
        print()

    # Sanity check: endpoint principal debe responder con el mismo ticket
    print("-" * 70)
    print("[Sanity] Endpoint principal /licitaciones.json con mismo ticket:")
    print("-" * 70)
    sanity_params = {
        "fecha": FECHAS_TEST[0].strftime("%d%m%Y"),
        "estado": "adjudicada",
        "ticket": ticket,
    }
    status, body, headers = _probe(f"{MP_API_BASE}/licitaciones.json", sanity_params)
    payload = _parse_payload(body)
    print(f"  HTTP {status}  headers={headers}")
    print(f"  payload_info={payload}")
    print(f"  body[:200]={body[:200]!r}")
    print()

    # Matriz: URL × formato fecha × fecha. Solo 1 fecha por variante de URL
    # para mantener el volumen razonable; cada URL prueba en la fecha[0].
    # Después, la URL que mejor responda se vuelve a probar con las 3 fechas.
    print("-" * 70)
    print("[Fase 1] Probar variantes de URL (1 fecha por variante)")
    print("-" * 70)

    best: List[Tuple[str, str, str]] = []  # (label, url, fmt_name)
    fecha_eval = FECHAS_TEST[0]

    for url_label, url in URL_VARIANTS:
        print(f"\n  URL: {url_label}")
        print(f"       {url}")
        for fmt_name, fmt_pat in DATE_FORMATS:
            params = {"fecha": fecha_eval.strftime(fmt_pat), "ticket": ticket}
            status, body, headers = _probe(url, params)
            payload = _parse_payload(body)
            verdict = "❓"
            if status == 200 and payload.get("parsed"):
                if payload.get("len", 0) > 0 or any(k.endswith("_len") and payload[k] > 0 for k in payload):
                    verdict = "✅ con data"
                    best.append((url_label, url, fmt_name))
                else:
                    verdict = "🟡 200 vacío"
            elif status == 200:
                verdict = "🟡 200 no-JSON"
            elif status == 404:
                verdict = "❌ 404"
            elif status == 401:
                verdict = "🔒 401 auth"
            elif status == 403:
                verdict = "🔒 403 forbidden"
            elif status == 429:
                verdict = "⏸ 429 rate"
            elif status == 503:
                verdict = "🔧 503 mantenimiento"
            elif status == -1:
                verdict = "💥 network"
            else:
                verdict = f"⚠️ {status}"
            print(f"       fecha={fmt_name:11s} -> HTTP {status:4d}  {verdict}  body[:120]={body[:120]!r}")
            time.sleep(2)  # courtesy delay

    print()
    print("-" * 70)
    print("[Fase 2] Re-probar variantes con respuesta exitosa en 3 fechas")
    print("-" * 70)
    if not best:
        print("  No hubo variante con respuesta ✅ en fase 1. Saltando fase 2.")
    else:
        for url_label, url, fmt_name in best[:2]:  # top 2
            fmt_pat = dict(DATE_FORMATS)[fmt_name]
            print(f"\n  URL exitosa: {url_label}  formato={fmt_name}")
            for d in FECHAS_TEST:
                params = {"fecha": d.strftime(fmt_pat), "ticket": ticket}
                status, body, headers = _probe(url, params)
                payload = _parse_payload(body)
                n = payload.get("len") or next(
                    (v for k, v in payload.items() if k.endswith("_len")), None
                )
                print(f"    {d.isoformat()}  HTTP {status:4d}  n_items={n}  payload={payload}")
                time.sleep(2)

    print()
    print("-" * 70)
    print("[Fase 3] Veredicto preliminar")
    print("-" * 70)
    if using_placeholder:
        print("  ⚠️ Resultado NO concluyente: ticket era placeholder o DEMO.")
        print("     Re-ejecutar con MP_TICKET productivo cargado en secrets.env.")
    elif best:
        labels = sorted({lbl for lbl, _, _ in best})
        print(f"  ✅ Escenario (a) PROBABLE: AGIL responde con ticket productivo.")
        print(f"     URLs que funcionaron: {labels}")
        print(f"     → CA/AGIL entra al scope de S13.")
        print(f"     → Verificar si la URL exitosa coincide con MP_API_AGIL_BASE de settings.py;")
        print(f"       si no, escenario (c): actualizar mercadopublico.py.")
    else:
        print(f"  ❌ Escenario (b) PROBABLE: ninguna combinación URL+formato devolvió data.")
        print(f"     → Bug latente de producción. Reportar como issue independiente.")
        print(f"     → S13 arranca con L1+LE+CO; AGIL/CA queda fuera del MVP.")
    print()


if __name__ == "__main__":
    main()
