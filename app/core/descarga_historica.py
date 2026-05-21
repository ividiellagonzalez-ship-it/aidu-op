"""
AIDU Op · Descarga histórica masiva
====================================
Permite descargar el histórico de Mercado Público de forma retroactiva,
con control de progreso y posibilidad de pausar/reanudar.

Estrategia:
- Descarga día a día desde fecha_inicio hasta fecha_fin
- Cada día consulta licitaciones publicadas Y adjudicadas (vía cliente API)
- Guarda en BD local de forma incremental (resilient: si se cae, retoma)
- Reporta progreso vía callback (para UI con barra de progreso)
"""
from __future__ import annotations
from typing import Callable, Dict, List, Optional
from datetime import date, timedelta
import logging
import json
from app.api.mercadopublico import MercadoPublicoClient
from app.db.migrator import get_connection

logger = logging.getLogger(__name__)


# S12.3 v2.2 — Tamaño de batch para pipelines HTTP. Mismo número validado
# en `app/core/descarga_diaria._batch_insert_vigentes` (S12.2.2) y en
# `docs/migracion_inicial_turso.py` (S12.1.5).
_HTTP_BATCH_SIZE = 50

# Columnas en orden para los INSERTs vía HTTP. Se define como módulo para
# que el path HTTP y los tests puedan compartir el layout sin parsear SQL.
_COLS_VIGENTES = (
    "codigo_externo", "nombre", "descripcion", "organismo", "organismo_codigo",
    "region", "comuna", "tipo", "fecha_publicacion", "fecha_cierre",
    "monto_referencial", "moneda", "estado", "url_mp_canonica", "raw_json",
    "hash_raw_json", "fuente",
)
_COLS_ADJ = (
    "codigo_externo", "nombre", "descripcion", "organismo", "organismo_codigo",
    "region", "comuna", "tipo", "fecha_publicacion", "fecha_cierre",
    "fecha_adjudicacion", "monto_referencial", "monto_adjudicado", "moneda",
    "n_oferentes", "proveedor_adjudicado", "proveedor_rut", "estado",
    "pondera_precio_pct", "raw_json", "hash_raw_json", "fuente",
)


def _registrar_dia_descargado(fecha: date, n_vigentes: int, n_adj: int):
    """Marca un día como ya descargado para no repetir trabajo."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mp_descargas_diarias (
                fecha TEXT PRIMARY KEY,
                n_vigentes INTEGER DEFAULT 0,
                n_adjudicadas INTEGER DEFAULT 0,
                fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.execute("""
            INSERT OR REPLACE INTO mp_descargas_diarias 
            (fecha, n_vigentes, n_adjudicadas, fecha_descarga)
            VALUES (?, ?, ?, datetime('now', 'localtime'))
        """, (fecha.isoformat(), n_vigentes, n_adj))
        conn.commit()
    finally:
        conn.close()


def dias_ya_descargados() -> set:
    """Retorna conjunto de fechas (str ISO) ya descargadas."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mp_descargas_diarias (
                fecha TEXT PRIMARY KEY,
                n_vigentes INTEGER DEFAULT 0,
                n_adjudicadas INTEGER DEFAULT 0,
                fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        rows = conn.execute(
            "SELECT fecha FROM mp_descargas_diarias"
        ).fetchall()
        return {r["fecha"] for r in rows}
    finally:
        conn.close()


def _parse_fecha(s):
    """Parser fechas tolerante."""
    if not s:
        return None
    s = str(s).strip()
    if "T" in s:
        s = s.split("T")[0]
    return s[:10] if len(s) >= 10 else None


def _registrar_cambio_historial(conn, codigo: str, campo: str, valor_ant, valor_nuevo, hash_ant: str, hash_nuevo: str, fuente_cambio: str):
    """Persiste un cambio detectado en mp_historial_cambios."""
    try:
        conn.execute("""
            INSERT INTO mp_historial_cambios
            (codigo_externo, campo, valor_anterior, valor_nuevo, hash_anterior, hash_nuevo, fuente_cambio)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            codigo, campo,
            str(valor_ant) if valor_ant is not None else None,
            str(valor_nuevo) if valor_nuevo is not None else None,
            hash_ant, hash_nuevo, fuente_cambio
        ))
    except Exception as e:
        logger.warning(f"No se pudo registrar cambio en historial para {codigo}.{campo}: {e}")


def _detectar_cambios(antiguo: dict, nuevo: dict, campos_monitoreados: list) -> list:
    """
    Compara valores antiguo vs nuevo en los campos monitoreados.
    Retorna lista de tuplas (campo, valor_ant, valor_nuevo) para los que cambiaron.
    """
    cambios = []
    for campo in campos_monitoreados:
        val_ant = antiguo.get(campo) if isinstance(antiguo, dict) else getattr(antiguo, campo, None)
        val_nuevo = nuevo.get(campo)
        # Normalizar para comparación: None == "" == 0 son distintos
        if val_ant != val_nuevo:
            # Excepto si ambos son falsy "vacíos" (None, "", 0)
            if (val_ant in (None, "", 0)) and (val_nuevo in (None, "", 0)):
                continue
            cambios.append((campo, val_ant, val_nuevo))
    return cambios


def _persistir_licitaciones(
    licitaciones_raw,
    tabla: str = "mp_licitaciones_vigentes",
    fuente: str = "api_diaria",
    use_http_client: bool = False,
) -> Dict:
    """
    UPSERT con merge inteligente:
    1. Si NO existe → INSERT con hash + fuente
    2. Si SÍ existe:
       - Calcular hash nuevo
       - Si hash difiere → detectar campos cambiados, registrar diff en historial,
         luego UPDATE
       - Si hash igual → skip silencioso (no escribimos nada, no contamos)

    Tras INSERT/UPDATE → llamar enriquecer_codigo() para repoblar tablas relacionales.

    DEFENSIVO: detecta si las columnas v18 (hash_raw_json, fuente) existen en la
    tabla. Si no existen, opera en modo legacy sin romper.

    S12.3 v2.2: el parámetro `use_http_client` controla el transporte de
    escritura. Default False mantiene el comportamiento previo (SQLite local
    vía `migrator.get_connection()`). True dispatcha a un path batched contra
    Turso vía `turso_http_client.execute_pipeline` — necesario para que el
    backfill MVP en GitHub Actions persista a Turso productivo en lugar de
    perder datos en el filesystem efímero del runner (mismo principio que
    S12.2.2 aplicó al cron diario).
    """
    if not licitaciones_raw:
        return {"nuevas": 0, "actualizadas": 0, "sin_cambios": 0, "fallidas": 0, "cambios_detectados": 0}

    if use_http_client:
        # S12.3 v2.2: el path HTTP existe SOLO para el backfill MVP. Los dos
        # consumidores previos (`app/ui/dashboard_mercado.py` y
        # `app/core/refresh_cierres.py`) NO setean este flag y por tanto NO
        # cambian de comportamiento.
        return _persistir_licitaciones_http(licitaciones_raw, tabla, fuente)
    
    # Import lazy para evitar circulares
    try:
        from app.core.enriquecimiento import enriquecer_codigo, _hash_raw
    except ImportError:
        # Si el módulo no existe, modo legacy completo
        enriquecer_codigo = None
        import hashlib
        def _hash_raw(s):
            return hashlib.sha256((s or "").encode()).hexdigest()[:16] if s else ""
    
    nuevas = 0
    actualizadas = 0
    sin_cambios = 0
    fallidas = 0
    cambios_detectados = 0
    
    # Campos cuyo cambio es relevante para auditar
    campos_monitoreados_vigentes = ["nombre", "monto_referencial", "fecha_cierre", "estado"]
    campos_monitoreados_adj = ["nombre", "monto_adjudicado", "fecha_adjudicacion", "n_oferentes", "estado"]
    campos_monitoreados = campos_monitoreados_adj if tabla == "mp_licitaciones_adj" else campos_monitoreados_vigentes
    
    conn = get_connection()
    try:
        # Detectar columnas disponibles en la tabla destino (defensivo)
        cols_existentes = {row[1] for row in conn.execute(f"PRAGMA table_info({tabla})").fetchall()}
        tiene_hash = "hash_raw_json" in cols_existentes
        tiene_fuente = "fuente" in cols_existentes
        tiene_url_canonica = "url_mp_canonica" in cols_existentes
        # Detectar si tabla historial existe
        tiene_historial = bool(conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='mp_historial_cambios'"
        ).fetchone())
        
        for lic in licitaciones_raw:
            try:
                codigo = lic.get("CodigoExterno") or lic.get("codigo_externo")
                if not codigo:
                    fallidas += 1
                    continue
                
                # Calcular hash del raw nuevo (siempre, por si tiene_hash sea True)
                raw_str_nuevo = json.dumps(lic, ensure_ascii=False)
                hash_nuevo = _hash_raw(raw_str_nuevo) if tiene_hash else ""
                
                # ¿Existe?
                if tiene_hash:
                    existe = conn.execute(
                        f"SELECT codigo_externo, hash_raw_json FROM {tabla} WHERE codigo_externo = ?",
                        (codigo,)
                    ).fetchone()
                else:
                    existe = conn.execute(
                        f"SELECT codigo_externo FROM {tabla} WHERE codigo_externo = ?",
                        (codigo,)
                    ).fetchone()
                
                # URL canónica (cuando la API la provee)
                url_canonica = (
                    lic.get("UrlAcceso") or 
                    lic.get("urlAcceso") or 
                    lic.get("url_acceso") or
                    None
                )
                
                comprador = lic.get("Comprador", {}) if isinstance(lic.get("Comprador"), dict) else {}
                adjudicacion = lic.get("Adjudicacion", {}) if isinstance(lic.get("Adjudicacion"), dict) else {}
                
                datos = {
                    "codigo_externo": codigo,
                    "nombre": lic.get("Nombre") or lic.get("nombre", ""),
                    "descripcion": lic.get("Descripcion") or lic.get("descripcion", ""),
                    "organismo": comprador.get("NombreOrganismo") or lic.get("organismo", ""),
                    "organismo_codigo": comprador.get("CodigoOrganismo", ""),
                    "region": lic.get("Region") or comprador.get("RegionUnidad") or "",
                    "comuna": lic.get("Comuna") or comprador.get("ComunaUnidad") or "",
                    "tipo": lic.get("Tipo", ""),
                    "fecha_publicacion": _parse_fecha(lic.get("FechaPublicacion") or lic.get("fecha_publicacion")),
                    "fecha_cierre": _parse_fecha(lic.get("FechaCierre") or lic.get("fecha_cierre")),
                    "monto_referencial": lic.get("MontoEstimado") or lic.get("monto_referencial") or 0,
                    "moneda": lic.get("Moneda", "CLP"),
                    "estado": lic.get("Estado", "publicada").lower() if isinstance(lic.get("Estado"), str) else "publicada",
                    "url_mp_canonica": url_canonica,
                    "raw_json": raw_str_nuevo,
                    "hash_raw_json": hash_nuevo,
                    "fuente": fuente,
                }
                
                if tabla == "mp_licitaciones_adj":
                    datos["fecha_adjudicacion"] = _parse_fecha(adjudicacion.get("Fecha")) or _parse_fecha(lic.get("FechaAdjudicacion"))
                    datos["monto_adjudicado"] = lic.get("MontoAdjudicado") or 0
                    datos["n_oferentes"] = adjudicacion.get("NumeroOferentes") or 0
                    datos["proveedor_adjudicado"] = ""
                    datos["proveedor_rut"] = ""
                    datos["pondera_precio_pct"] = 0
                
                if existe:
                    if tiene_hash:
                        hash_anterior = existe["hash_raw_json"] if existe["hash_raw_json"] else ""
                        # Si hash igual → skip silencioso (idempotencia)
                        if hash_anterior == hash_nuevo and hash_anterior:
                            sin_cambios += 1
                            continue
                        
                        # Hash distinto → detectar diferencias específicas
                        if hash_anterior and tiene_historial:
                            cols_str = ", ".join(campos_monitoreados)
                            row_ant = conn.execute(
                                f"SELECT {cols_str} FROM {tabla} WHERE codigo_externo = ?",
                                (codigo,)
                            ).fetchone()
                            antiguo = dict(row_ant) if row_ant else {}
                            cambios = _detectar_cambios(antiguo, datos, campos_monitoreados)
                            for campo, va, vn in cambios:
                                _registrar_cambio_historial(conn, codigo, campo, va, vn, hash_anterior, hash_nuevo, fuente)
                                cambios_detectados += 1
                    
                    # Construir UPDATE dinámico según columnas disponibles
                    if tabla == "mp_licitaciones_adj":
                        sets = ["nombre=?", "descripcion=?", "monto_adjudicado=?", "fecha_adjudicacion=?", "n_oferentes=?", "raw_json=?"]
                        vals = [datos["nombre"], datos["descripcion"], datos["monto_adjudicado"],
                                datos["fecha_adjudicacion"], datos["n_oferentes"], datos["raw_json"]]
                        if tiene_url_canonica:
                            sets.append("url_mp_canonica=COALESCE(?, url_mp_canonica)")
                            vals.append(datos["url_mp_canonica"])
                        if tiene_hash:
                            sets.append("hash_raw_json=?")
                            vals.append(datos["hash_raw_json"])
                        if tiene_fuente:
                            sets.append("fuente=?")
                            vals.append(datos["fuente"])
                        vals.append(codigo)
                        conn.execute(f"UPDATE {tabla} SET {', '.join(sets)} WHERE codigo_externo=?", vals)
                    else:
                        sets = ["nombre=?", "descripcion=?", "fecha_cierre=?", "monto_referencial=?", "raw_json=?"]
                        vals = [datos["nombre"], datos["descripcion"], datos["fecha_cierre"],
                                datos["monto_referencial"], datos["raw_json"]]
                        if tiene_url_canonica:
                            sets.append("url_mp_canonica=COALESCE(?, url_mp_canonica)")
                            vals.append(datos["url_mp_canonica"])
                        if tiene_hash:
                            sets.append("hash_raw_json=?")
                            vals.append(datos["hash_raw_json"])
                        if tiene_fuente:
                            sets.append("fuente=?")
                            vals.append(datos["fuente"])
                        vals.append(codigo)
                        conn.execute(f"UPDATE {tabla} SET {', '.join(sets)} WHERE codigo_externo=?", vals)
                    actualizadas += 1
                else:
                    # INSERT dinámico según columnas disponibles
                    if tabla == "mp_licitaciones_adj":
                        cols = ["codigo_externo", "nombre", "descripcion", "organismo", "organismo_codigo",
                                "region", "comuna", "tipo", "fecha_publicacion", "fecha_cierre", "fecha_adjudicacion",
                                "monto_referencial", "monto_adjudicado", "moneda", "n_oferentes",
                                "proveedor_adjudicado", "proveedor_rut", "estado", "pondera_precio_pct", "raw_json"]
                        vals = [datos["codigo_externo"], datos["nombre"], datos["descripcion"],
                                datos["organismo"], datos["organismo_codigo"],
                                datos["region"], datos["comuna"], datos["tipo"],
                                datos["fecha_publicacion"], datos["fecha_cierre"], datos["fecha_adjudicacion"],
                                datos["monto_referencial"], datos["monto_adjudicado"], datos["moneda"], datos["n_oferentes"],
                                datos["proveedor_adjudicado"], datos["proveedor_rut"], "Adjudicada", datos["pondera_precio_pct"],
                                datos["raw_json"]]
                    else:
                        cols = ["codigo_externo", "nombre", "descripcion", "organismo", "organismo_codigo",
                                "region", "comuna", "tipo", "fecha_publicacion", "fecha_cierre",
                                "monto_referencial", "moneda", "estado", "raw_json"]
                        vals = [datos["codigo_externo"], datos["nombre"], datos["descripcion"],
                                datos["organismo"], datos["organismo_codigo"],
                                datos["region"], datos["comuna"], datos["tipo"],
                                datos["fecha_publicacion"], datos["fecha_cierre"],
                                datos["monto_referencial"], datos["moneda"], datos["estado"],
                                datos["raw_json"]]
                    
                    # Agregar columnas v18 si existen
                    if tiene_url_canonica:
                        cols.append("url_mp_canonica")
                        vals.append(datos["url_mp_canonica"])
                    if tiene_hash:
                        cols.append("hash_raw_json")
                        vals.append(datos["hash_raw_json"])
                    if tiene_fuente:
                        cols.append("fuente")
                        vals.append(datos["fuente"])
                    
                    placeholders = ", ".join(["?"] * len(vals))
                    cols_str = ", ".join(cols)
                    conn.execute(f"INSERT INTO {tabla} ({cols_str}) VALUES ({placeholders})", vals)
                    nuevas += 1
                
                # Enriquecer (defensivo: solo si está disponible y hay tablas v18)
                if enriquecer_codigo is not None:
                    try:
                        enriquecer_codigo(codigo, conn=conn, fuente_cambio=fuente)
                    except Exception as e:
                        logger.debug(f"Skip enriquecimiento {codigo}: {e}")
            except Exception as e:
                logger.error(f"Error persistiendo {codigo}: {e}")
                fallidas += 1
                continue
        
        conn.commit()
    finally:
        conn.close()
    
    return {
        "nuevas": nuevas, 
        "actualizadas": actualizadas, 
        "sin_cambios": sin_cambios,
        "fallidas": fallidas,
        "cambios_detectados": cambios_detectados,
    }


# ============================================================
# S12.3 v2.2 — Path HTTP /v2/pipeline para backfill MVP
# ============================================================

def _persistir_licitaciones_http(
    licitaciones_raw: List[Dict],
    tabla: str,
    fuente: str,
) -> Dict:
    """
    Variante HTTP de `_persistir_licitaciones` para el backfill MVP S12.3.

    Diferencias con el path SQLite (default):
    - Escribe a Turso vía `turso_http_client.execute_pipeline` en batches
      de _HTTP_BATCH_SIZE statements, no via `migrator.get_connection()`.
    - NO detecta cambios granulares (`mp_historial_cambios` no se popula
      en este path — el MVP no lo necesita y registrar diferencias por
      campo requiere SELECT por licitación contra HTTP, lento e inviable).
    - INSERT OR IGNORE para cabecera (idempotente: re-ejecutar el mismo
      rango NO duplica filas, requisito explícito del MVP). UPDATE solo
      cuando hay diferencia de hash detectada en bulk-check.
    - Enriquecimiento integrado: para cada licitación nueva, extrae items
      (con tipo_origen según `Tipo`), adjudicaciones, organismo. Todo en
      buffers que se vuelcan en batches al final.

    El caller controla qué tabla recibe la inserción (cabecera vigentes
    vs adj). Los buffers de items/adjudicaciones/organismos siempre se
    pueblan independiente de la tabla cabecera (sin duplicación: si una
    licitación ya existe, no se re-enriquece).

    Returns:
        Dict con stats: nuevas, actualizadas, sin_cambios, fallidas,
        items, adjudicaciones, organismos. Mismas keys que el path SQLite
        más los contadores de enriquecimiento (que en el SQLite vienen
        desde `enriquecer_codigo` por separado).
    """
    if not licitaciones_raw:
        return {
            "nuevas": 0, "actualizadas": 0, "sin_cambios": 0, "fallidas": 0,
            "cambios_detectados": 0, "items": 0, "adjudicaciones": 0, "organismos": 0,
        }

    # Imports diferidos para evitar dependencias circulares cuando el
    # módulo se carga sin Turso configurado (dev/CI/tests).
    from app.db import turso_http_client
    from app.db._hrana_types import arg_for_value
    from app.core.enriquecimiento import (
        _extraer_items, _extraer_adjudicaciones_de_items,
        _extraer_organismo, _hash_raw,
    )

    if tabla not in ("mp_licitaciones_vigentes", "mp_licitaciones_adj"):
        raise ValueError(
            f"_persistir_licitaciones_http solo acepta cabeceras "
            f"('mp_licitaciones_vigentes' o 'mp_licitaciones_adj'); recibió {tabla!r}"
        )
    cols = _COLS_VIGENTES if tabla == "mp_licitaciones_vigentes" else _COLS_ADJ

    # 1) Normalizar inputs y filtrar los que no tienen codigo_externo.
    parsed: List[Dict] = []
    fallidas = 0
    for lic in licitaciones_raw:
        codigo = lic.get("CodigoExterno") or lic.get("codigo_externo")
        if not codigo:
            fallidas += 1
            continue
        raw_str = json.dumps(lic, ensure_ascii=False)
        parsed.append({
            "codigo": codigo,
            "raw": lic,
            "raw_str": raw_str,
            "hash": _hash_raw(raw_str),
        })

    if not parsed:
        return {
            "nuevas": 0, "actualizadas": 0, "sin_cambios": 0, "fallidas": fallidas,
            "cambios_detectados": 0, "items": 0, "adjudicaciones": 0, "organismos": 0,
        }

    codigos = [p["codigo"] for p in parsed]

    # 2) Bulk check: códigos ya presentes + su hash. Una sola query con IN.
    existentes_hash: Dict[str, str] = {}
    CHUNK = 500
    for i in range(0, len(codigos), CHUNK):
        ch = codigos[i:i + CHUNK]
        placeholders = ",".join("?" * len(ch))
        sql = (
            f"SELECT codigo_externo, hash_raw_json FROM {tabla} "
            f"WHERE codigo_externo IN ({placeholders})"
        )
        args = [arg_for_value(c) for c in ch]
        rows = turso_http_client.query_all(sql, args=args)
        for row in rows:
            if row and row[0] is not None:
                existentes_hash[row[0]] = (row[1] or "") if len(row) > 1 else ""

    # 3) Separar nuevas / actualizadas / sin_cambios.
    nuevas_rows: List[tuple] = []     # tuplas en orden de `cols`
    update_rows: List[tuple] = []     # (raw_json, hash, codigo) por ahora simple
    nuevas_parsed: List[Dict] = []    # las que necesitan enriquecimiento
    sin_cambios = 0

    for p in parsed:
        codigo = p["codigo"]
        lic = p["raw"]
        comprador = lic.get("Comprador") if isinstance(lic.get("Comprador"), dict) else {}
        adjudicacion = lic.get("Adjudicacion") if isinstance(lic.get("Adjudicacion"), dict) else {}
        url_canonica = (
            lic.get("UrlAcceso") or lic.get("urlAcceso") or lic.get("url_acceso") or None
        )

        datos = {
            "codigo_externo": codigo,
            "nombre": lic.get("Nombre") or lic.get("nombre", ""),
            "descripcion": lic.get("Descripcion") or lic.get("descripcion", ""),
            "organismo": comprador.get("NombreOrganismo") or lic.get("organismo", ""),
            "organismo_codigo": comprador.get("CodigoOrganismo", ""),
            "region": lic.get("Region") or comprador.get("RegionUnidad") or "",
            "comuna": lic.get("Comuna") or comprador.get("ComunaUnidad") or "",
            "tipo": lic.get("Tipo", ""),
            "fecha_publicacion": _parse_fecha(lic.get("FechaPublicacion") or lic.get("fecha_publicacion")),
            "fecha_cierre": _parse_fecha(lic.get("FechaCierre") or lic.get("fecha_cierre")),
            "monto_referencial": lic.get("MontoEstimado") or lic.get("monto_referencial") or 0,
            "moneda": lic.get("Moneda", "CLP"),
            "estado": (
                lic.get("Estado", "publicada").lower()
                if isinstance(lic.get("Estado"), str) else "publicada"
            ),
            "url_mp_canonica": url_canonica,
            "raw_json": p["raw_str"],
            "hash_raw_json": p["hash"],
            "fuente": fuente,
        }
        if tabla == "mp_licitaciones_adj":
            datos["fecha_adjudicacion"] = (
                _parse_fecha(adjudicacion.get("Fecha"))
                or _parse_fecha(lic.get("FechaAdjudicacion"))
            )
            datos["monto_adjudicado"] = lic.get("MontoAdjudicado") or 0
            datos["n_oferentes"] = adjudicacion.get("NumeroOferentes") or 0
            datos["proveedor_adjudicado"] = ""
            datos["proveedor_rut"] = ""
            datos["pondera_precio_pct"] = 0
            datos["estado"] = "Adjudicada"

        if codigo in existentes_hash:
            hash_ant = existentes_hash[codigo]
            if hash_ant and hash_ant == p["hash"]:
                sin_cambios += 1
                continue
            # Hash distinto → UPDATE mínimo del raw_json + hash.
            update_rows.append((p["raw_str"], p["hash"], codigo))
        else:
            nuevas_rows.append(tuple(datos[c] for c in cols))
            nuevas_parsed.append(p)

    # 4) Batch INSERT OR IGNORE de cabecera (idempotente).
    if nuevas_rows:
        col_list = ",".join(cols)
        placeholders = ",".join("?" * len(cols))
        insert_sql = (
            f"INSERT OR IGNORE INTO {tabla} ({col_list}) VALUES ({placeholders})"
        )
        for chunk in _chunked(nuevas_rows, _HTTP_BATCH_SIZE):
            statements = [
                {"sql": insert_sql, "args": [arg_for_value(v) for v in row]}
                for row in chunk
            ]
            results = turso_http_client.execute_pipeline(statements)
            _log_errores_payload(results, contexto=f"INSERT {tabla}")

    # 5) Batch UPDATE del raw_json + hash para las que cambiaron.
    if update_rows:
        update_sql = (
            f"UPDATE {tabla} SET raw_json=?, hash_raw_json=? WHERE codigo_externo=?"
        )
        for chunk in _chunked(update_rows, _HTTP_BATCH_SIZE):
            statements = [
                {"sql": update_sql, "args": [arg_for_value(v) for v in row]}
                for row in chunk
            ]
            results = turso_http_client.execute_pipeline(statements)
            _log_errores_payload(results, contexto=f"UPDATE {tabla}")

    # 6) Enriquecimiento: items, adjudicaciones, organismos. Solo para las
    # licitaciones nuevas (las existentes ya tienen los items vinculados
    # de corridas previas — idempotencia).
    items_rows, adj_rows, orgs_rows = [], [], []
    for p in nuevas_parsed:
        codigo = p["codigo"]
        raw = p["raw"]
        # tipo_origen: LE → servicio; CA/AGIL/L1/y demás → producto.
        tipo_lic = str(raw.get("Tipo") or "").strip().upper()
        tipo_origen = "servicio" if tipo_lic == "LE" else "producto"

        items = _extraer_items(raw, codigo)
        for it in items:
            items_rows.append((
                codigo, it["correlativo"], it["codigo_unspsc"],
                it["codigo_categoria"], it["categoria_nombre"],
                it["nombre_producto"], it["descripcion"],
                it["unidad_medida"], it["cantidad"], tipo_origen,
            ))

        adjs = _extraer_adjudicaciones_de_items(items, codigo)
        for a in adjs:
            adj_rows.append((
                codigo, a["item_correlativo"], a["rut_proveedor"],
                a["nombre_proveedor"], a["cantidad_adjudicada"],
                a["monto_unitario"], a["monto_linea"],
            ))

        org = _extraer_organismo(raw)
        if org:
            orgs_rows.append((
                org["codigo"], org["nombre"], org["region"], org["comuna"],
            ))

    if items_rows:
        sql_items = (
            "INSERT OR IGNORE INTO mp_licitaciones_items "
            "(codigo_externo, correlativo, codigo_unspsc, codigo_categoria, "
            " categoria_nombre, nombre_producto, descripcion, unidad_medida, "
            " cantidad, tipo_origen) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        for chunk in _chunked(items_rows, _HTTP_BATCH_SIZE):
            statements = [
                {"sql": sql_items, "args": [arg_for_value(v) for v in row]}
                for row in chunk
            ]
            results = turso_http_client.execute_pipeline(statements)
            _log_errores_payload(results, contexto="INSERT mp_licitaciones_items")

    if adj_rows:
        sql_adj = (
            "INSERT OR IGNORE INTO mp_adjudicaciones "
            "(codigo_externo, item_correlativo, rut_proveedor, nombre_proveedor, "
            " cantidad_adjudicada, monto_unitario, monto_linea) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        for chunk in _chunked(adj_rows, _HTTP_BATCH_SIZE):
            statements = [
                {"sql": sql_adj, "args": [arg_for_value(v) for v in row]}
                for row in chunk
            ]
            results = turso_http_client.execute_pipeline(statements)
            _log_errores_payload(results, contexto="INSERT mp_adjudicaciones")

    if orgs_rows:
        sql_orgs = (
            "INSERT OR REPLACE INTO mp_organismos "
            "(codigo, nombre, region, comuna) VALUES (?, ?, ?, ?)"
        )
        for chunk in _chunked(orgs_rows, _HTTP_BATCH_SIZE):
            statements = [
                {"sql": sql_orgs, "args": [arg_for_value(v) for v in row]}
                for row in chunk
            ]
            results = turso_http_client.execute_pipeline(statements)
            _log_errores_payload(results, contexto="INSERT mp_organismos")

    return {
        "nuevas": len(nuevas_rows),
        "actualizadas": len(update_rows),
        "sin_cambios": sin_cambios,
        "fallidas": fallidas,
        "cambios_detectados": 0,  # No se trackean granularmente en HTTP path.
        "items": len(items_rows),
        "adjudicaciones": len(adj_rows),
        "organismos": len(orgs_rows),
    }


def _chunked(seq, size: int):
    """Yield chunks consecutivos de longitud ≤ size."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _log_errores_payload(results: List[dict], *, contexto: str) -> None:
    """
    Inspecciona los results de un pipeline y loggea cada `type=error` como
    WARNING. No levanta: con INSERT OR IGNORE, las violaciones de UNIQUE son
    esperables en re-ejecuciones idempotentes. Errores de transporte ya
    tira `execute_pipeline` como TursoUnavailableError.
    """
    for i, res in enumerate(results):
        if res.get("type") == "error":
            err = res.get("error", {}).get("message", "?")
            logger.warning(f"⚠️  {contexto}: result[{i}]: {err}")


def descargar_rango(
    fecha_inicio: date,
    fecha_fin: date,
    incluir_adjudicadas: bool = True,
    incluir_vigentes: bool = True,
    incluir_agiles: bool = True,
    saltar_descargados: bool = True,
    progress_callback: Optional[Callable] = None,
    use_http_client: bool = False,
    filtro_tipos: Optional[List[str]] = None,
    filtro_regiones: Optional[List[str]] = None,
    save_raw: bool = True,
) -> Dict:
    """
    Descarga licitaciones día a día en un rango de fechas.
    
    Args:
        fecha_inicio: primer día (inclusive)
        fecha_fin: último día (inclusive)
        incluir_adjudicadas: descargar licitaciones adjudicadas
        incluir_vigentes: descargar licitaciones vigentes/publicadas
        incluir_agiles: descargar Compras Ágiles (Tipo='AGIL', <100 UTM)
        saltar_descargados: no re-descargar días ya procesados
        progress_callback: función(dia_actual, total, fecha, n_vigentes, n_adj, status)
    
    Returns:
        Dict con resumen
    """
    if fecha_inicio > fecha_fin:
        raise ValueError("fecha_inicio debe ser <= fecha_fin")

    client = MercadoPublicoClient(save_raw=save_raw)

    # Helpers de filtrado post-fetch (S12.3 v2.2). Si las listas son
    # None/vacías, la API devuelve todo (comportamiento previo).
    from app.api.mercadopublico import filtrar_por_tipo, filtrar_por_region

    def _aplicar_filtros(items: List[Dict]) -> List[Dict]:
        if filtro_tipos:
            items = filtrar_por_tipo(items, filtro_tipos)
        if filtro_regiones:
            items = filtrar_por_region(items, filtro_regiones)
        return items

    fechas = []
    cursor = fecha_inicio
    while cursor <= fecha_fin:
        fechas.append(cursor)
        cursor += timedelta(days=1)

    total = len(fechas)
    # En modo HTTP no usamos el registro local `mp_descargas_diarias`
    # (vive en SQLite local; el backfill productivo escribe a Turso).
    descargados_set = (
        dias_ya_descargados()
        if (saltar_descargados and not use_http_client)
        else set()
    )
    
    stats = {
        "total_dias": total,
        "dias_procesados": 0,
        "dias_saltados": 0,
        "dias_con_error": 0,
        "total_vigentes": 0,
        "total_adjudicadas": 0,
        "total_agiles": 0,
    }
    
    for i, fecha in enumerate(fechas, start=1):
        fecha_str = fecha.isoformat()
        
        if saltar_descargados and fecha_str in descargados_set:
            stats["dias_saltados"] += 1
            if progress_callback:
                progress_callback(i, total, fecha, 0, 0, "saltado")
            continue
        
        try:
            n_vig = 0
            n_adj = 0
            n_agil = 0
            
            if incluir_vigentes:
                vigentes = client.listar_vigentes_por_fecha(fecha)
                vigentes = _aplicar_filtros(vigentes)
                if vigentes:
                    res_v = _persistir_licitaciones(
                        vigentes, "mp_licitaciones_vigentes",
                        fuente="api_historica", use_http_client=use_http_client,
                    )
                    n_vig = res_v.get("nuevas", 0) + res_v.get("actualizadas", 0)

            if incluir_adjudicadas:
                adjudicadas = client.listar_adjudicadas_por_fecha(fecha)
                adjudicadas = _aplicar_filtros(adjudicadas)
                if adjudicadas:
                    res_a = _persistir_licitaciones(
                        adjudicadas, "mp_licitaciones_adj",
                        fuente="api_historica", use_http_client=use_http_client,
                    )
                    n_adj = res_a.get("nuevas", 0) + res_a.get("actualizadas", 0)

            # Sprint 11.2: Compras Ágiles
            if incluir_agiles:
                try:
                    agiles = client.listar_agiles_por_fecha(fecha)
                    agiles = _aplicar_filtros(agiles)
                    if agiles:
                        # Las Compras Ágiles vigentes van a la tabla vigentes con tipo='AGIL'
                        # Las cerradas/adjudicadas van a tabla adj
                        agiles_vigentes = [a for a in agiles if str(a.get("Estado", "")).lower() in ("publicada", "vigente", "activa")]
                        agiles_cerradas = [a for a in agiles if a not in agiles_vigentes]

                        if agiles_vigentes:
                            res_av = _persistir_licitaciones(
                                agiles_vigentes, "mp_licitaciones_vigentes",
                                fuente="api_agil", use_http_client=use_http_client,
                            )
                            n_agil += res_av.get("nuevas", 0) + res_av.get("actualizadas", 0)
                        if agiles_cerradas:
                            res_ac = _persistir_licitaciones(
                                agiles_cerradas, "mp_licitaciones_adj",
                                fuente="api_agil", use_http_client=use_http_client,
                            )
                            n_agil += res_ac.get("nuevas", 0) + res_ac.get("actualizadas", 0)
                except Exception as e_agil:
                    logger.warning(f"Error AGIL {fecha}: {e_agil}")

            # `mp_descargas_diarias` solo se popula en modo SQLite local
            # (es una tabla auxiliar de checkpoint para la UI de Streamlit).
            if not use_http_client:
                _registrar_dia_descargado(fecha, n_vig, n_adj)
            
            stats["dias_procesados"] += 1
            stats["total_vigentes"] += n_vig
            stats["total_adjudicadas"] += n_adj
            stats["total_agiles"] += n_agil
            
            if progress_callback:
                progress_callback(i, total, fecha, n_vig, n_adj, f"ok · {n_agil} AGIL" if n_agil else "ok")
        
        except Exception as e:
            logger.error(f"Error descargando {fecha}: {e}")
            stats["dias_con_error"] += 1
            if progress_callback:
                progress_callback(i, total, fecha, 0, 0, f"error: {e}")
    
    return stats


def progreso_descarga_historica() -> Dict:
    """Retorna estado de descarga histórica para mostrar al usuario."""
    conn = get_connection()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mp_descargas_diarias (
                fecha TEXT PRIMARY KEY,
                n_vigentes INTEGER DEFAULT 0,
                n_adjudicadas INTEGER DEFAULT 0,
                fecha_descarga TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        
        row = conn.execute("""
            SELECT 
                COUNT(*) AS n_dias,
                MIN(fecha) AS desde,
                MAX(fecha) AS hasta,
                SUM(n_vigentes) AS total_vig,
                SUM(n_adjudicadas) AS total_adj
            FROM mp_descargas_diarias
        """).fetchone()
        
        return {
            "n_dias_descargados": row["n_dias"] if row else 0,
            "fecha_desde": row["desde"] if row else None,
            "fecha_hasta": row["hasta"] if row else None,
            "total_vigentes_acumulado": row["total_vig"] or 0 if row else 0,
            "total_adjudicadas_acumulado": row["total_adj"] or 0 if row else 0,
        }
    finally:
        conn.close()
