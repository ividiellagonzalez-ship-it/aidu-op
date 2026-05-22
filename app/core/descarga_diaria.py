"""
AIDU Op · Job de Descarga Diaria MP
=====================================
Descarga licitaciones vigentes desde Mercado Público.
Diseñado para correr en GitHub Actions cron (7am Chile).

Uso:
    python -m app.core.descarga_diaria

    # O programáticamente:
    from app.core.descarga_diaria import ejecutar_descarga
    resultado = ejecutar_descarga(dias_atras=2)

Persistencia (S12.2.2)
----------------------
El job tiene dos paths según haya credenciales Turso configuradas:

  1. **Modo Turso (producción)**: escribe vía
     `app.db.turso_http_client.execute_pipeline` directamente al
     endpoint HTTP `/v2/pipeline` de Turso. Bypass del cliente libsql
     "embedded replica" cuyo handshake falla determinísticamente
     contra Turso hosteado en AWS (`Invalid header bit 123`,
     bug arquitectónico documentado en `tursodatabase/libsql-laravel#2`).
     Inserciones en batches de hasta 50 por pipeline para amortizar
     RTT HTTP, escribe `mp_ingesta_log` con stats al final.

  2. **Modo SQLite (dev / CI / tests)**: cuando NO hay credenciales
     Turso, usa `app.db.migrator.get_connection()` con SQLite local.
     Path original pre-S12.2.2, mantenido para no romper desarrollo
     local ni el suite de tests que monkeypatchea `get_connection`.

La selección automática vive en `ejecutar_descarga` (chequeo de
`turso_http_client.is_configured()`).
"""
import logging
import json
import os
import time
from datetime import date, timedelta
from typing import Dict, Iterable, List, Optional, Tuple

from app.api.mercadopublico import MercadoPublicoClient
from app.db.migrator import get_connection
from app.db.exceptions import TursoUnavailableError
from app.db import turso_http_client
from app.db._hrana_types import arg_for_value
from app.core.ingesta import _calcular_match_aidu

logger = logging.getLogger(__name__)

# Tamaño de batch para los pipelines HTTP a Turso. 50 statements por
# request es el mismo número validado en producción por
# `docs/migracion_inicial_turso.py` durante S12.1.5. Suficientemente
# grande para amortizar el RTT HTTP, suficientemente chico para no
# acercarse al límite de payload (~1 MB) que enforce Turso.
_TURSO_BATCH_SIZE = 50

# Columnas en orden para INSERT en mp_licitaciones_vigentes. Se mantiene
# como constante de módulo para que tests y helpers puedan compartir el
# layout sin parser SQL.
_VIGENTES_COLS = (
    "codigo_externo", "nombre", "descripcion", "organismo", "organismo_codigo",
    "region", "comuna", "tipo", "fecha_publicacion", "fecha_cierre",
    "monto_referencial", "moneda", "estado", "url_mp_canonica", "raw_json",
)


class MercadoPublicoAPIError(Exception):
    """
    Falla atribuible a la API de Mercado Público (rate limit, downtime,
    ticket inválido, schema inesperado en la respuesta). Mapea a exit 1
    en el CLI. Distinta de TursoUnavailableError (BD/Turso → exit 2) y
    de excepciones inesperadas (→ exit 3).
    """


def ejecutar_descarga(dias_atras: int = 2, ticket: Optional[str] = None) -> Dict:
    """
    Descarga licitaciones VIGENTES (publicadas) de los últimos N días.

    Cubre AMBOS endpoints de Mercado Público en una sola corrida:
    - Endpoint principal: tipos L1/LE/LP/LR/LS/LQ/CO (oferta pública estándar).
    - Endpoint AGIL: Compras Ágiles <100 UTM (`tipo='AGIL'`). Es el MVP
      comercial de AIDU — requerimiento explícito de S12.2 que no estaba
      cubierto antes (las llamadas a listar_agiles_recientes vivían solo en
      descarga_historica.py para back-fills manuales).

    El persistidor común (mp_licitaciones_vigentes) acepta los AGIL tal cual
    porque listar_agiles_por_fecha ya normaliza al formato {CodigoExterno,
    Nombre, ..., Tipo: 'AGIL', Comprador: {...}}.

    S12.2.2: la persistencia tiene dos paths. Si hay credenciales Turso,
    el job escribe vía HTTP `/v2/pipeline` (`turso_http_client`),
    bypaseando el cliente libsql para evitar el bug
    `Invalid header bit 123` en AWS-hosted Turso. Sin credenciales,
    cae al path SQLite local (modo dev/CI/tests).

    Returns:
        Dict con stats: nuevas, actualizadas, fallidas, total_descargado,
        categorizadas_aidu, agiles_descargadas (subconjunto de total_descargado).
    """
    cliente = MercadoPublicoClient(ticket=ticket)

    # Endpoint principal: si falla, el cron no tiene nada útil que hacer.
    # Convertimos a MercadoPublicoAPIError tipada para que el CLI mapee a
    # exit 1 sin recurrir a heurística por substring (S12.2.1).
    try:
        licitaciones_principales = cliente.descargar_vigentes_recientes(dias_atras=dias_atras)
    except Exception as e:
        raise MercadoPublicoAPIError(
            f"API Mercado Público falló en endpoint principal: {e}"
        ) from e

    try:
        agiles = cliente.listar_agiles_recientes(dias_atras=dias_atras)
    except Exception as e:
        # Endpoint AGIL caído no debe abortar el cron — el principal ya bajó.
        logger.warning(f"⚠️  AGIL falló, continúo con principales: {e}")
        agiles = []
    # Side-fix S13.0 hallazgo A: capturar estado del endpoint AGIL para
    # persistir en mp_ingesta_log.agil_endpoint_estado. Permite distinguir
    # '0 nuevas legitimas' de '0 nuevas porque endpoint cayo'.
    # Ver docs/sprints/AIDU_Op_S13_1_Restaurar_Compras_Agiles.md.
    # Usamos literal 'no_consultado' (no la constante de MercadoPublicoClient)
    # porque los tests mockean MercadoPublicoClient con clases fake.
    agil_endpoint_estado = getattr(cliente, "last_agil_status", "no_consultado")

    licitaciones_raw = list(licitaciones_principales) + list(agiles)
    n_agiles = len(agiles)

    if not licitaciones_raw:
        logger.warning("Sin licitaciones nuevas descargadas (ni principales ni AGIL)")
        return {
            "nuevas": 0, "actualizadas": 0, "fallidas": 0,
            "total_descargado": 0, "categorizadas_aidu": 0,
            "agiles_descargadas": 0,
        }

    # Diagnóstico S12.2.2.1: log el resultado del dispatcher para correlacionar
    # con runs en producción cuando hay dudas sobre por qué se eligió un path.
    # No revela valores de secrets — solo si la env var está seteada o no.
    # Agregado tras Run #6 que aparentó tomar el path libsql con el código de
    # S12.2.2 ya mergeado (commit 32a2691). Si el próximo run con este logging
    # muestra `turso_http=False` y `EMPTY`, la causa es ausencia de secrets en
    # GitHub Actions; si muestra `turso_http=True` pero igual entró a libsql,
    # hay un bug de raíz distinto que investigar.
    turso_active = turso_http_client.is_configured()
    logger.info(
        f"📍 Path dispatcher: turso_http={turso_active}; "
        f"env TURSO_DATABASE_URL={'set' if os.environ.get('TURSO_DATABASE_URL') else 'EMPTY'}; "
        f"env TURSO_AUTH_TOKEN={'set' if os.environ.get('TURSO_AUTH_TOKEN') else 'EMPTY'}"
    )

    if turso_http_client.is_configured():
        resultado = _ejecutar_via_http(
            licitaciones_raw, n_agiles, dias_atras,
            agil_endpoint_estado=agil_endpoint_estado,
        )
    else:
        resultado = _ejecutar_via_sqlite(licitaciones_raw, n_agiles)

    logger.info(f"✅ Descarga completada: {resultado}")
    return resultado


# ============================================================
# Path 1: Turso HTTP /v2/pipeline (S12.2.2, productivo)
# ============================================================

def _ejecutar_via_http(
    licitaciones_raw: List[Dict],
    n_agiles: int,
    dias_atras: int,
    *,
    agil_endpoint_estado: str = "no_consultado",
) -> Dict:
    """
    Persiste licitaciones a Turso vía HTTP `/v2/pipeline`. Estrategia:

      1. Pre-cargar matchers AIDU (1 query para `aidu_servicios_keywords`).
      2. Pre-cargar set de códigos ya existentes (1 query con WHERE IN
         para todos los códigos a la vez — antes hacía N queries).
      3. Loop en memoria: separar inserts vs updates, calcular
         categorización AIDU usando los matchers pre-cargados (sin
         tocar la BD por licitación).
      4. Batch INSERT mp_licitaciones_vigentes (50 por pipeline).
      5. Batch UPDATE mp_licitaciones_vigentes (50 por pipeline).
      6. Batch INSERT OR REPLACE mp_categorizacion_aidu (50 por pipeline).
      7. INSERT en mp_ingesta_log con duración y conteos.

    Las fallas de transporte (HTTP 4xx/5xx, timeout) se mapean a
    `TursoUnavailableError` por `turso_http_client.execute_pipeline`,
    que el `_main` del CLI captura para exit 2.
    """
    inicio = time.time()

    matchers = _cargar_matchers_aidu()  # lista de tuplas (cod_servicio, kw, kw_excl)
    codigos_input = _extraer_codigos_unicos(licitaciones_raw)
    existentes = _bulk_check_existencia(codigos_input)

    # Acumuladores para los batches.
    inserts: List[Tuple] = []          # filas a insertar en mp_licitaciones_vigentes
    updates: List[Tuple] = []          # tuplas para UPDATE
    cat_inserts: List[Tuple[str, str, float]] = []  # (codigo, cod_aidu, confianza)
    fallidas = 0

    for lic in licitaciones_raw:
        try:
            codigo = lic.get("CodigoExterno") or lic.get("codigo_externo")
            if not codigo:
                fallidas += 1
                continue

            datos = _mapear_licitacion(lic, codigo)
            if codigo in existentes:
                updates.append((
                    datos["nombre"], datos["descripcion"], datos["fecha_cierre"],
                    datos["monto_referencial"], datos["url_mp_canonica"],
                    datos["raw_json"], codigo,
                ))
            else:
                inserts.append(tuple(datos[c] for c in _VIGENTES_COLS))
                # Categorización in-memory: las 12 categorías AIDU son
                # estáticas, los matchers se cargaron una sola vez antes
                # del loop. Top 1 (igual que el flujo SQLite original).
                texto = f"{datos['nombre']} {datos['descripcion']}".strip()
                top = _match_aidu_inmemory(texto, matchers, top_n=1)
                for cod_aidu, conf in top:
                    cat_inserts.append((codigo, cod_aidu, conf))
        except Exception as e:
            # Falla por licitación individual: no aborta el batch entero.
            # Las TursoUnavailableError no llegan acá porque las queries
            # van fuera del loop, pero por defensividad re-raise.
            if isinstance(e, TursoUnavailableError):
                raise
            logger.error(f"Error procesando licitación: {e}")
            fallidas += 1

    # Disparo de los batches contra Turso. Cualquier falla de transporte
    # levanta TursoUnavailableError → exit 2 en el CLI.
    _batch_insert_vigentes(inserts)
    _batch_update_vigentes(updates)
    _batch_insert_categorizaciones(cat_inserts)

    duracion = round(time.time() - inicio, 2)
    nuevas = len(inserts)
    actualizadas = len(updates)
    categorizadas = len(cat_inserts)

    # mp_ingesta_log: criterio de éxito #3 del plan S12.2.2. ANTES el cron
    # diario nunca escribía esta tabla (deuda heredada — solo
    # `app.core.ingesta.ingestar_lote` lo hacía y vive en el flujo
    # manual). Acá lo agregamos en el path HTTP para que el dashboard
    # de monitoreo y `app.core.backfill` puedan saber que el cron corrió.
    _insert_ingesta_log(
        n_descargadas=len(licitaciones_raw),
        n_nuevas=nuevas,
        n_actualizadas=actualizadas,
        duracion_s=duracion,
        n_fallidas=fallidas,
        dias_atras=dias_atras,
        agil_endpoint_estado=agil_endpoint_estado,
    )

    return {
        "nuevas": nuevas,
        "actualizadas": actualizadas,
        "fallidas": fallidas,
        "total_descargado": len(licitaciones_raw),
        "categorizadas_aidu": categorizadas,
        "agiles_descargadas": n_agiles,
    }


def _cargar_matchers_aidu() -> List[Tuple[str, List[str], List[str]]]:
    """
    Una query única a `aidu_servicios_keywords` que devuelve la lista
    `[(cod_servicio, [keywords], [excluyentes])]`. Se llama UNA VEZ
    al inicio del path HTTP en lugar de por licitación, evitando 446
    SELECTs en el caso del Run #3.

    Si la tabla está vacía o falla, devuelve []: la categorización
    quedará en cero (no aborta la descarga).
    """
    try:
        rows = turso_http_client.query_all(
            "SELECT cod_servicio, keywords, keywords_excluyentes "
            "FROM aidu_servicios_keywords"
        )
    except TursoUnavailableError:
        # Si query_all explota como TursoUnavailableError, propagamos:
        # un SELECT que falla es señal de que Turso no está usable
        # para escrituras tampoco.
        raise
    matchers: List[Tuple[str, List[str], List[str]]] = []
    for row in rows:
        cod, kw_str, excl_str = row[0], row[1] or "", row[2] or ""
        kws = [k.strip().lower() for k in kw_str.split(",") if k.strip()]
        excls = [k.strip().lower() for k in excl_str.split(",") if k.strip()]
        matchers.append((cod, kws, excls))
    return matchers


def _extraer_codigos_unicos(licitaciones_raw: Iterable[Dict]) -> List[str]:
    """Set de códigos externos no vacíos para chequear existencia en batch."""
    codigos: set = set()
    for lic in licitaciones_raw:
        c = lic.get("CodigoExterno") or lic.get("codigo_externo")
        if c:
            codigos.add(c)
    return sorted(codigos)


def _bulk_check_existencia(codigos: List[str]) -> set:
    """
    Devuelve el subset de `codigos` que ya están en `mp_licitaciones_vigentes`.
    Usa una sola query con WHERE IN (...). Si la lista es muy larga (>500),
    parte en chunks porque algunos backends limitan la cantidad de
    parámetros por query — Turso/SQLite acepta ~32k parámetros, pero el
    ETL típico del cron son ~500-1000 licitaciones, así que un solo query
    con chunk de 500 cubre cómodamente.
    """
    if not codigos:
        return set()

    existentes: set = set()
    CHUNK = 500
    for i in range(0, len(codigos), CHUNK):
        chunk = codigos[i:i + CHUNK]
        placeholders = ",".join("?" * len(chunk))
        sql = (
            "SELECT codigo_externo FROM mp_licitaciones_vigentes "
            f"WHERE codigo_externo IN ({placeholders})"
        )
        args = [arg_for_value(c) for c in chunk]
        rows = turso_http_client.query_all(sql, args=args)
        for row in rows:
            if row and row[0] is not None:
                existentes.add(row[0])
    return existentes


def _batch_insert_vigentes(inserts: List[Tuple]) -> None:
    """
    Batch INSERT a mp_licitaciones_vigentes en pipelines de hasta 50.
    Cada licitación es un statement Hrana independiente dentro del
    pipeline (Turso ejecuta todos en orden; si uno falla, los previos
    igual quedan committeados — esto es OK, las licitaciones son
    independientes y un INSERT puede fallar por race con otro proceso
    sin invalidar los demás).
    """
    if not inserts:
        return
    col_list = ",".join(_VIGENTES_COLS)
    placeholders = ",".join("?" * len(_VIGENTES_COLS))
    sql = (
        f"INSERT INTO mp_licitaciones_vigentes ({col_list}) "
        f"VALUES ({placeholders})"
    )
    for chunk in _chunked(inserts, _TURSO_BATCH_SIZE):
        statements = [
            {"sql": sql, "args": [arg_for_value(v) for v in row]}
            for row in chunk
        ]
        results = turso_http_client.execute_pipeline(statements)
        _log_errores_payload(results, contexto="INSERT mp_licitaciones_vigentes")


def _batch_update_vigentes(updates: List[Tuple]) -> None:
    """
    Batch UPDATE a mp_licitaciones_vigentes. Cada update toca solo los
    campos que pueden cambiar entre snapshots: nombre, descripcion,
    fecha_cierre, monto_referencial, url_mp_canonica (con COALESCE para
    no pisar con NULL si la API no la trae), raw_json.
    """
    if not updates:
        return
    sql = (
        "UPDATE mp_licitaciones_vigentes "
        "SET nombre=?, descripcion=?, fecha_cierre=?, monto_referencial=?, "
        "    url_mp_canonica=COALESCE(?, url_mp_canonica), raw_json=? "
        "WHERE codigo_externo=?"
    )
    for chunk in _chunked(updates, _TURSO_BATCH_SIZE):
        statements = [
            {"sql": sql, "args": [arg_for_value(v) for v in row]}
            for row in chunk
        ]
        results = turso_http_client.execute_pipeline(statements)
        _log_errores_payload(results, contexto="UPDATE mp_licitaciones_vigentes")


def _batch_insert_categorizaciones(cat_inserts: List[Tuple[str, str, float]]) -> None:
    """
    Batch INSERT OR REPLACE en mp_categorizacion_aidu. INSERT OR REPLACE
    es lo que usa el flujo SQLite original — preserva idempotencia si
    una licitación se re-procesa en una corrida posterior.
    """
    if not cat_inserts:
        return
    sql = (
        "INSERT OR REPLACE INTO mp_categorizacion_aidu "
        "(codigo_externo, cod_servicio_aidu, confianza) VALUES (?, ?, ?)"
    )
    for chunk in _chunked(cat_inserts, _TURSO_BATCH_SIZE):
        statements = [
            {"sql": sql, "args": [arg_for_value(v) for v in row]}
            for row in chunk
        ]
        results = turso_http_client.execute_pipeline(statements)
        _log_errores_payload(results, contexto="INSERT mp_categorizacion_aidu")


def _insert_ingesta_log(
    *, n_descargadas: int, n_nuevas: int, n_actualizadas: int,
    duracion_s: float, n_fallidas: int, dias_atras: int,
    agil_endpoint_estado: Optional[str] = None,
) -> None:
    """
    Escribe entrada en `mp_ingesta_log`. Schema (mig 001 + mig 008 + mig 009):

        id, fecha_consultada, n_licitaciones_descargadas, n_nuevas,
        n_actualizadas, duracion_segundos, estado, error_msg,
        fecha_ejecucion (default datetime('now', 'localtime')),
        tipo, subtipo (mig 008),
        agil_endpoint_estado (mig 009, side-fix S13.0).

    `fecha_consultada` es la fecha más vieja del rango: hoy - dias_atras.
    `estado` es 'OK' si fallidas == 0, 'PARCIAL' si > 0.
    `agil_endpoint_estado` es uno de:
        'ok' | 'caido_404' | 'error_otro' | 'no_consultado' (default si None).
    """
    fecha_consultada = (date.today() - timedelta(days=dias_atras)).isoformat()
    estado = "OK" if n_fallidas == 0 else "PARCIAL"
    error_msg = None if n_fallidas == 0 else f"{n_fallidas} licitaciones fallidas"
    agil_estado = agil_endpoint_estado or "no_consultado"
    sql = (
        "INSERT INTO mp_ingesta_log "
        "(fecha_consultada, n_licitaciones_descargadas, n_nuevas, "
        " n_actualizadas, duracion_segundos, estado, error_msg, "
        " agil_endpoint_estado) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
    )
    args = [arg_for_value(v) for v in (
        fecha_consultada, n_descargadas, n_nuevas, n_actualizadas,
        duracion_s, estado, error_msg, agil_estado,
    )]
    turso_http_client.execute_pipeline([{"sql": sql, "args": args}])


def _match_aidu_inmemory(
    texto: str,
    matchers: List[Tuple[str, List[str], List[str]]],
    *,
    top_n: int = 1,
) -> List[Tuple[str, float]]:
    """
    Replica de la lógica de `app.core.ingesta._calcular_match_aidu` SIN
    tocar la BD. Recibe los matchers pre-cargados y devuelve los top N
    matches.

    Idéntico algoritmo: keywords excluyentes → score 0 (skip);
    score = min(1.0, hits / max(3, len(kws) * 0.4)); umbral 0.3.
    """
    texto_lower = texto.lower()
    if not texto_lower.strip():
        return []
    matches: List[Tuple[str, float]] = []
    for cod, kws, excls in matchers:
        if any(ex in texto_lower for ex in excls):
            continue
        hits = sum(1 for kw in kws if kw in texto_lower)
        if hits == 0:
            continue
        score = min(1.0, hits / max(3, len(kws) * 0.4))
        if score >= 0.3:
            matches.append((cod, round(score, 3)))
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:top_n]


def _chunked(seq, size: int):
    """Yield chunks consecutivos de longitud ≤ size."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _log_errores_payload(results: List[dict], *, contexto: str) -> None:
    """
    Inspecciona los results de un pipeline y loggea cada `type=error`
    al nivel WARNING. NO levanta — los errores SQL en INSERT/UPDATE
    pueden ser legítimos (`UNIQUE constraint failed` en una race con
    otro proceso, por ejemplo) y no deben abortar el batch entero.

    Las TursoUnavailableError de transporte ya las tira
    `execute_pipeline`; acá solo llegamos si la respuesta HTTP fue OK.
    """
    for i, res in enumerate(results):
        if res.get("type") == "error":
            err = res.get("error", {}).get("message", "?")
            logger.warning(f"⚠️  {contexto}: result[{i}]: {err}")


def _mapear_licitacion(lic: Dict, codigo: str) -> Dict:
    """
    Normaliza una licitación cruda del API MP al shape de
    `mp_licitaciones_vigentes`. Misma lógica que el flujo SQLite
    original; extraída acá para que ambos paths (HTTP y SQLite) la
    compartan sin duplicar.
    """
    comprador = lic.get("Comprador") if isinstance(lic.get("Comprador"), dict) else {}
    url_canonica_api = (
        lic.get("UrlAcceso")
        or lic.get("urlAcceso")
        or lic.get("url_acceso")
        or None
    )
    return {
        "codigo_externo": codigo,
        "nombre": lic.get("Nombre") or lic.get("nombre", ""),
        "descripcion": lic.get("Descripcion") or lic.get("descripcion", ""),
        "organismo": comprador.get("NombreOrganismo") or lic.get("organismo", ""),
        "organismo_codigo": comprador.get("CodigoOrganismo", ""),
        "region": lic.get("Region") or comprador.get("RegionUnidad") or "",
        "comuna": lic.get("Comuna") or comprador.get("ComunaUnidad") or "",
        "tipo": lic.get("Tipo", ""),
        "fecha_publicacion": _parse_fecha(
            lic.get("FechaPublicacion") or lic.get("fecha_publicacion")
        ),
        "fecha_cierre": _parse_fecha(
            lic.get("FechaCierre") or lic.get("fecha_cierre")
        ),
        "monto_referencial": lic.get("MontoEstimado") or lic.get("monto_referencial") or 0,
        "moneda": lic.get("Moneda", "CLP"),
        "estado": "publicada",
        "url_mp_canonica": url_canonica_api,
        "raw_json": json.dumps(lic, ensure_ascii=False),
    }


# ============================================================
# Path 2: SQLite local (dev / CI / tests, sin Turso)
# ============================================================

def _ejecutar_via_sqlite(licitaciones_raw: List[Dict], n_agiles: int) -> Dict:
    """
    Path original pre-S12.2.2: usa `migrator.get_connection()` que abre
    SQLite local (DB_PATH) cuando NO hay credenciales Turso. Se mantiene
    para que dev/CI/tests no necesiten Turso configurado.

    NO escribe `mp_ingesta_log` en este path para no divergir del
    comportamiento previo que los tests del flujo SQLite verifican.
    """
    nuevas = 0
    actualizadas = 0
    fallidas = 0
    categorizadas = 0

    conn = get_connection()
    try:
        for lic in licitaciones_raw:
            try:
                codigo = lic.get("CodigoExterno") or lic.get("codigo_externo")
                if not codigo:
                    fallidas += 1
                    continue

                existe = conn.execute(
                    "SELECT codigo_externo FROM mp_licitaciones_vigentes WHERE codigo_externo = ?",
                    (codigo,)
                ).fetchone()

                datos = _mapear_licitacion(lic, codigo)

                if existe:
                    conn.execute("""
                        UPDATE mp_licitaciones_vigentes
                        SET nombre=?, descripcion=?, fecha_cierre=?, monto_referencial=?,
                            url_mp_canonica=COALESCE(?, url_mp_canonica), raw_json=?
                        WHERE codigo_externo=?
                    """, (
                        datos["nombre"], datos["descripcion"], datos["fecha_cierre"],
                        datos["monto_referencial"], datos["url_mp_canonica"],
                        datos["raw_json"], codigo,
                    ))
                    actualizadas += 1
                else:
                    conn.execute(
                        "INSERT INTO mp_licitaciones_vigentes ("
                        + ",".join(_VIGENTES_COLS)
                        + ") VALUES (" + ",".join("?" * len(_VIGENTES_COLS)) + ")",
                        tuple(datos[c] for c in _VIGENTES_COLS),
                    )
                    nuevas += 1

                    try:
                        matches = _calcular_match_aidu(
                            {"nombre": datos["nombre"], "descripcion": datos["descripcion"]},
                            conn,
                        )
                        for cod_aidu, confianza in matches[:1]:
                            conn.execute("""
                                INSERT OR REPLACE INTO mp_categorizacion_aidu
                                (codigo_externo, cod_servicio_aidu, confianza)
                                VALUES (?, ?, ?)
                            """, (codigo, cod_aidu, confianza))
                            categorizadas += 1
                    except Exception as e:
                        logger.warning(f"Categorización fallida {codigo}: {e}")

                conn.commit()

            except TursoUnavailableError:
                # Mantener defensividad de S12.2.1: si por alguna razón
                # get_connection llega a propagar TursoUnavailableError
                # (no debería con el chequeo de is_configured arriba,
                # pero defensa en profundidad), abortar.
                raise
            except Exception as e:
                logger.error(f"Error procesando licitación: {e}")
                fallidas += 1
    finally:
        conn.close()

    return {
        "nuevas": nuevas,
        "actualizadas": actualizadas,
        "fallidas": fallidas,
        "total_descargado": len(licitaciones_raw),
        "categorizadas_aidu": categorizadas,
        "agiles_descargadas": n_agiles,
    }


def _parse_fecha(fecha_str) -> Optional[str]:
    """Normaliza fechas del API MP a formato ISO YYYY-MM-DD."""
    if not fecha_str:
        return None
    try:
        # API MP devuelve fechas tipo "2026-05-09T17:00:00"
        if isinstance(fecha_str, str) and "T" in fecha_str:
            return fecha_str.split("T")[0]
        return str(fecha_str)[:10]
    except Exception:
        return None


def listar_vigentes(
    region: Optional[str] = None,
    categoria_aidu: Optional[str] = None,
    dias_max_cierre: Optional[int] = None,
    limit: int = 100,
) -> List[Dict]:
    """
    Lista licitaciones vigentes con filtros.
    Para usar en la UI del tab '🔥 Hoy'.
    """
    conn = get_connection()
    try:
        sql = """
            SELECT 
                v.codigo_externo, v.nombre, v.descripcion,
                v.organismo, v.region, v.comuna,
                v.fecha_publicacion, v.fecha_cierre,
                v.monto_referencial, v.tipo,
                c.cod_servicio_aidu, c.confianza,
                v.fecha_descarga, v.url_mp_canonica,
                CAST(julianday(v.fecha_cierre) - julianday('now') AS INTEGER) as dias_para_cierre
            FROM mp_licitaciones_vigentes v
            LEFT JOIN mp_categorizacion_aidu c ON c.codigo_externo = v.codigo_externo
            WHERE 1=1
        """
        params = []
        
        if region and region != "Todas":
            sql += " AND v.region LIKE ?"
            params.append(f"%{region}%")
        
        if categoria_aidu and categoria_aidu != "Todas":
            sql += " AND c.cod_servicio_aidu = ?"
            params.append(categoria_aidu)
        
        if dias_max_cierre is not None:
            sql += " AND CAST(julianday(v.fecha_cierre) - julianday('now') AS INTEGER) <= ?"
            params.append(dias_max_cierre)
        
        sql += " ORDER BY v.fecha_cierre ASC LIMIT ?"
        params.append(limit)
        
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def stats_vigentes() -> Dict:
    """Stats rápidas para mostrar en el tab Hoy."""
    conn = get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM mp_licitaciones_vigentes").fetchone()[0]
        
        hoy_24h = conn.execute("""
            SELECT COUNT(*) FROM mp_licitaciones_vigentes 
            WHERE fecha_descarga >= datetime('now', '-1 day')
        """).fetchone()[0]
        
        cierran_3d = conn.execute("""
            SELECT COUNT(*) FROM mp_licitaciones_vigentes 
            WHERE CAST(julianday(fecha_cierre) - julianday('now') AS INTEGER) BETWEEN 0 AND 3
        """).fetchone()[0]
        
        con_match_aidu = conn.execute("""
            SELECT COUNT(DISTINCT v.codigo_externo) 
            FROM mp_licitaciones_vigentes v
            INNER JOIN mp_categorizacion_aidu c ON c.codigo_externo = v.codigo_externo
        """).fetchone()[0]
        
        ultima_actualizacion = conn.execute("""
            SELECT MAX(fecha_descarga) FROM mp_licitaciones_vigentes
        """).fetchone()[0]
        
        return {
            "total_vigentes": total,
            "publicadas_24h": hoy_24h,
            "cierran_proximos_3_dias": cierran_3d,
            "con_match_aidu": con_match_aidu,
            "ultima_actualizacion": ultima_actualizacion,
        }
    finally:
        conn.close()


def _main() -> int:
    """
    Punto de entrada del CLI invocado por el cron de GitHub Actions
    (.github/workflows/descarga_mp_diaria.yml).

    Devuelve el exit code en lugar de llamar a sys.exit() para que pueda
    testearse sin subprocess (ver tests/test_descarga_diaria_cli.py).

    Exit codes (S12.2.1, reemplaza la heurística por substring de S12.2):
      0 = éxito (incluye "0 licitaciones nuevas hoy" — no es error).
      1 = error API Mercado Público (rate limit, downtime, ticket inválido,
          schema inesperado). Captura MercadoPublicoAPIError.
      2 = error en BD/Turso (handshake fallido, auth, sync). Captura
          TursoUnavailableError. Reemplaza el fallback silencioso del
          Run #3 que generaba exit 0 con datos perdidos.
      3 = error inesperado (no API, no BD). Imprime traceback completo
          para que el operador lo investigue manualmente.
    """
    import os as _os
    import sys as _sys
    import traceback as _tb

    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    dias = int(_os.environ.get("DIAS_ATRAS", "2"))
    print(f"🚀 Iniciando descarga diaria MP (dias_atras={dias})...")

    try:
        resultado = ejecutar_descarga(dias_atras=dias)
    except TursoUnavailableError as exc:
        # Cubre el escenario del Run #3: handshake con Turso falla y no se
        # puede escribir a la BD productiva. ANTES caía a SQLite local y
        # perdía los datos descargados. AHORA aborta limpio para que el
        # operador investigue (libsql 'Invalid header bit', token, etc.).
        logger.error(
            f"❌ Turso no disponible tras {exc.intentos} reintentos. "
            f"Abortando descarga sin escribir datos. "
            f"Las licitaciones de la API se descartan para evitar "
            f"pérdida silenciosa. Último error: {exc.ultimo_error}"
        )
        return 2
    except MercadoPublicoAPIError as exc:
        logger.error(f"❌ Falla API Mercado Público: {exc}")
        return 1
    except Exception:
        # Cualquier otra excepción: probablemente un bug. Traceback completo
        # al stderr y exit 3 para que el operador lo trate como caso
        # excepcional, no como ruido conocido.
        print("❌ Error inesperado en descarga diaria. Traceback:", file=_sys.stderr)
        _tb.print_exc()
        return 3

    print("\n📊 Resultado:")
    for k, v in resultado.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(_main())
