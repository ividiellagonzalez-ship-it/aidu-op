"""
AIDU Op · Cliente API Mercado Público
======================================
Cliente robusto para api.mercadopublico.cl con:
- Rate limiting automático (no quema el ticket)
- Retries con backoff exponencial
- Logging estructurado de cada request
- Cache de respuestas crudas en data/raw/

Endpoints utilizados:
- /licitaciones.json?fecha=DDMMYYYY&estado=adjudicada  → listado por fecha
- /licitaciones.json?codigo=XXXX-X-XX                  → detalle individual
"""
import requests
import time
import json
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import deque

from config.settings import (
    MP_API_BASE, MP_TICKET_DEMO,
    MP_REQUESTS_PER_MINUTE, MP_REQUEST_TIMEOUT,
    MP_MAX_RETRIES, MP_RETRY_BACKOFF, RAW_DIR,
    get_mp_ticket
)

logger = logging.getLogger(__name__)


class MercadoPublicoClient:
    """Cliente con rate limiting interno usando ventana deslizante"""

    def __init__(self, ticket: Optional[str] = None, save_raw: bool = True):
        # Lazy fetch del ticket — funciona en Streamlit Cloud
        self.ticket = ticket or get_mp_ticket() or MP_TICKET_DEMO
        self.save_raw = save_raw
        self._request_times = deque(maxlen=MP_REQUESTS_PER_MINUTE)
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AIDU-Op/1.0 (Python; aidu.op@gmail.com)",
            "Accept": "application/json",
        })

        if self.ticket == MP_TICKET_DEMO:
            logger.warning("⚠️  Usando ticket DEMO público (rate limit reducido)")

    def _wait_for_rate_limit(self):
        """Ventana deslizante: max N requests por minuto"""
        now = time.time()
        # Eliminar requests > 60s
        while self._request_times and now - self._request_times[0] > 60:
            self._request_times.popleft()

        if len(self._request_times) >= MP_REQUESTS_PER_MINUTE:
            oldest = self._request_times[0]
            wait = 60 - (now - oldest) + 0.5
            if wait > 0:
                logger.info(f"⏸️  Rate limit: esperando {wait:.1f}s")
                time.sleep(wait)

        self._request_times.append(time.time())

    def _request(self, params: Dict[str, Any]) -> Optional[Dict]:
        """
        Request con rate limiting + retries.
        Retorna None si falla después de todos los intentos.
        """
        self._wait_for_rate_limit()
        params["ticket"] = self.ticket
        url = f"{MP_API_BASE}/licitaciones.json"

        for intento in range(MP_MAX_RETRIES):
            try:
                resp = self.session.get(url, params=params, timeout=MP_REQUEST_TIMEOUT)

                if resp.status_code == 200:
                    try:
                        return resp.json()
                    except json.JSONDecodeError:
                        logger.error(f"Respuesta no es JSON: {resp.text[:200]}")
                        return None

                elif resp.status_code in (429, 503):
                    # Rate limit del servidor o overload
                    backoff = MP_RETRY_BACKOFF * (2 ** intento)
                    logger.warning(f"⚠️  HTTP {resp.status_code}, backoff {backoff}s")
                    time.sleep(backoff)
                    continue

                elif resp.status_code == 401:
                    logger.error("❌ HTTP 401: ticket inválido o expirado")
                    return None

                else:
                    logger.warning(f"HTTP {resp.status_code} para {params}")
                    return None

            except requests.Timeout:
                logger.warning(f"⏱️  Timeout intento {intento+1}/{MP_MAX_RETRIES}")
                time.sleep(MP_RETRY_BACKOFF)
            except requests.RequestException as e:
                logger.error(f"Error de red: {e}")
                time.sleep(MP_RETRY_BACKOFF)

        logger.error(f"❌ Fallaron {MP_MAX_RETRIES} intentos para {params}")
        return None

    def listar_adjudicadas_por_fecha(self, fecha: date) -> List[Dict]:
        """
        Lista licitaciones adjudicadas en una fecha específica.
        Formato fecha API: DDMMYYYY
        """
        fecha_str = fecha.strftime("%d%m%Y")
        params = {"fecha": fecha_str, "estado": "adjudicada"}

        data = self._request(params)
        if not data:
            return []

        listado = data.get("Listado", [])
        logger.info(f"📅 {fecha} · {len(listado)} adjudicadas")

        # Cache crudo (útil para reproducir/debug)
        if self.save_raw and listado:
            cache_file = RAW_DIR / f"{fecha:%Y%m%d}_adjudicadas.json"
            cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return listado

    def detalle_licitacion(self, codigo: str) -> Optional[Dict]:
        """Detalle completo de una licitación por código"""
        params = {"codigo": codigo}
        data = self._request(params)
        if not data:
            return None

        listado = data.get("Listado", [])
        return listado[0] if listado else None

    def licitaciones_rango_fechas(
        self,
        fecha_inicio: date,
        fecha_fin: date,
        callback_progreso=None
    ) -> int:
        """
        Iterador eficiente para descargar todas las adjudicadas
        en un rango de fechas. Útil para backfill.

        callback_progreso(fecha_actual, total_descargadas) para progreso.

        Retorna total descargado.
        """
        total = 0
        actual = fecha_inicio
        while actual <= fecha_fin:
            licitaciones = self.listar_adjudicadas_por_fecha(actual)
            total += len(licitaciones)

            if callback_progreso:
                callback_progreso(actual, total)

            yield actual, licitaciones
            actual += timedelta(days=1)

        return total
