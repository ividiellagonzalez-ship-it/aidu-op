"""TEMPORAL - ANALISIS POST-LOTE-1 DE INTELIGENCIA_PRECIOS - NO MERGEAR A MAIN

Extrae las filas con linea_aidu='Otros' del lote_id='backfill_1', analiza
frecuencias de unigramas y bigramas en sus descripciones, y propone
keywords adicionales por linea AIDU ranqueados por impacto estimado
(cuantas filas de 'Otros' capturaria cada nuevo keyword).

Output: stdout estructurado para que Claude pueda parsearlo del log
de GH Actions y assembarlo en un reporte para el Director.

NO modifica nada en Turso ni en el repo. Solo READ + analisis local.
"""
import sys
import io
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

import os
import re
import unicodedata
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db import turso_http_client
from app.core.categorizador_aidu_fast import (
    LINEAS_AIDU_FAST,
    cargar_catalogo_desde_csv,
    normalizar_texto,
)


# Pistas heuristicas: si un keyword candidato matchea estos contextos,
# probablemente pertenece a esa linea. Esto NO modifica el categorizador,
# solo ayuda al script a etiquetar los candidatos.
PISTAS_LINEA = {
    "Ferreteria": {
        "construccion", "obra", "reparacion edificio", "mantencion",
        "metal", "alambre", "fierro", "cemento", "hormigon",
        "electrico", "iluminacion", "luminaria", "ferreteria",
        "pintura", "tubo", "caño",
    },
    "Aseo": {
        "aseo", "limpieza", "higiene", "sanitario", "papel",
        "detergente", "cloro", "desinfectante", "esterilizacion",
        "lavanderia", "sanitizacion",
    },
    "Oficina": {
        "oficina", "papeleria", "escritorio", "papel carta",
        "impresion", "fotocopia", "etiqueta", "libreta", "cuaderno",
        "lapiz", "boligrafo", "carpeta", "archivador papel",
    },
    "Equipamiento": {
        "computador", "notebook", "monitor", "impresora", "mueble",
        "silla", "mesa", "refrigerador", "microondas", "telefono",
        "switch", "router", "audio", "video", "proyector",
        "equipamiento", "equipo", "electrodomestico",
    },
}


STOPWORDS = {
    "de", "la", "el", "y", "o", "a", "en", "para", "con", "por", "del",
    "los", "las", "un", "una", "uno", "se", "su", "sus", "lo", "al",
    "que", "es", "son", "este", "esta", "estos", "estas", "este",
    "ese", "esa", "como", "mas", "menos", "pero", "no", "si", "sin",
    "sobre", "bajo", "ante", "tras", "entre", "hasta", "desde",
    "muy", "ya", "aun", "todo", "todos", "toda", "todas",
    "kg", "kilo", "kilos", "gr", "gramos", "ml", "litro", "litros",
    "lts", "lt", "un", "uds", "unidad", "unidades", "cajas", "caja",
    "pack", "set", "pieza", "piezas", "doc", "docena", "rollo",
    "rollos", "metros", "metro", "mts", "mt", "cm", "mm",
    "tipo", "color", "n", "nro", "num",
}


def normalizar(s: str) -> str:
    return normalizar_texto(s or "")


def tokenize(s: str):
    """Words 3+ chars, stopwords removidas, alphanumeric only."""
    s = normalizar(s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    words = [w for w in s.split() if len(w) >= 3 and w not in STOPWORDS]
    return words


def bigrams(tokens):
    return [f"{tokens[i]} {tokens[i+1]}" for i in range(len(tokens) - 1)]


def cargar_keywords_actuales():
    """Lee los keywords actuales del CSV (la fuente de verdad)."""
    csv_path = Path(__file__).resolve().parents[2] / "config" / "keywords_aidu_fast.csv"
    return cargar_catalogo_desde_csv(csv_path)


def existe_match_actual(descripcion: str, catalogo: dict) -> bool:
    """Verifica si la descripcion matchea algun keyword existente
    (sirve para validar que las filas son genuinamente 'Otros')."""
    texto = normalizar(descripcion)
    for kws in catalogo.values():
        for kw in kws:
            if kw and kw in texto:
                return True
    return False


def pistas_para_termino(termino: str) -> list[str]:
    """Devuelve las lineas en cuyas PISTAS_LINEA aparece el termino."""
    matches = []
    for linea, pistas in PISTAS_LINEA.items():
        for pista in pistas:
            if pista in termino or termino in pista:
                matches.append(linea)
                break
    return matches


def main():
    print("=" * 70)
    print("ANALISIS post-Lote-1: filas con linea_aidu='Otros'")
    print("=" * 70)
    print()

    if not turso_http_client.is_configured():
        print("ERROR: TURSO_DATABASE_URL + TURSO_AUTH_TOKEN no configurados")
        return 1

    # 1. Cargar las 152 filas
    rows = turso_http_client.query_all(
        "SELECT producto_descripcion, organismo_comprador, tipo_objeto, "
        "       precio_unitario, cantidad, unidad_medida "
        "FROM inteligencia_precios "
        "WHERE lote_id = ? AND linea_aidu = 'Otros' "
        "ORDER BY producto_descripcion",
        [{"type": "text", "value": "backfill_1"}],
    )
    print(f"Total filas 'Otros' del Lote 1: {len(rows)}")
    print()

    catalogo = cargar_keywords_actuales()
    print("Keywords actuales por linea:")
    for linea in LINEAS_AIDU_FAST:
        print(f"  {linea}: {len(catalogo.get(linea, []))} keywords")
    print()

    # 2. Mostrar todas las descripciones (para que Claude pueda revisar)
    print("=" * 70)
    print("LISTADO COMPLETO DE DESCRIPCIONES (orden alfabetico)")
    print("=" * 70)
    for i, row in enumerate(rows, start=1):
        desc = (row[0] or "").strip()
        org = (row[1] or "").strip()
        tipo = (row[2] or "").strip()
        pu = row[3]
        qty = row[4]
        um = row[5] or ""
        print(f"  {i:3d}. [{tipo:8s}] [{um:5s}] qty={qty} pu={pu}  | {desc[:120]}")
        if org:
            print(f"       org: {org[:90]}")
    print()

    # 3. Analisis de frecuencias: unigramas y bigramas en las descripciones
    print("=" * 70)
    print("FRECUENCIA DE TERMINOS (unigramas y bigramas)")
    print("=" * 70)
    desc_tokens = []
    desc_bigrams = []
    all_descs = []
    for row in rows:
        desc = (row[0] or "")
        all_descs.append(desc)
        toks = tokenize(desc)
        desc_tokens.append(toks)
        desc_bigrams.append(bigrams(toks))

    unigrams_count = Counter()
    for toks in desc_tokens:
        unigrams_count.update(set(toks))  # set: una vez por descripcion
    bigrams_count = Counter()
    for bgs in desc_bigrams:
        bigrams_count.update(set(bgs))

    print("\nTop 40 unigramas (frecuencia = en cuantas descripciones aparece):")
    for term, n in unigrams_count.most_common(40):
        if n < 3:
            break
        pistas = pistas_para_termino(term)
        pistas_str = f" [pistas: {','.join(pistas)}]" if pistas else ""
        print(f"  {n:3d}  {term}{pistas_str}")

    print("\nTop 30 bigramas (frecuencia = en cuantas descripciones aparece):")
    for term, n in bigrams_count.most_common(30):
        if n < 2:
            break
        pistas = pistas_para_termino(term)
        pistas_str = f" [pistas: {','.join(pistas)}]" if pistas else ""
        print(f"  {n:3d}  {term}{pistas_str}")

    # 4. Para cada linea AIDU, proponer keywords candidatos:
    #    terminos frecuentes en 'Otros' que tienen pistas hacia esa linea
    print()
    print("=" * 70)
    print("CANDIDATOS A KEYWORDS POR LINEA (top 10 por linea)")
    print("=" * 70)
    for linea in LINEAS_AIDU_FAST:
        if linea == "Otros":
            continue
        candidatos = []
        # unigramas con pista a esta linea
        for term, n in unigrams_count.items():
            if n < 2:
                continue
            if linea in pistas_para_termino(term):
                # cuantas descripciones (de 152) matchea
                n_descs = sum(1 for d in all_descs if term in normalizar(d))
                candidatos.append((term, n_descs, "unigrama"))
        # bigramas con pista
        for term, n in bigrams_count.items():
            if n < 2:
                continue
            if linea in pistas_para_termino(term):
                n_descs = sum(1 for d in all_descs if term in normalizar(d))
                candidatos.append((term, n_descs, "bigrama"))

        candidatos.sort(key=lambda x: -x[1])
        print(f"\n{linea}:")
        if not candidatos:
            print("  (sin candidatos con pistas claras)")
            continue
        for term, n_descs, tipo in candidatos[:15]:
            print(f"  {n_descs:3d} desc | {tipo:8s} | {term}")

    # 5. Analisis exploratorio: terminos frecuentes sin pista asignada
    #    (para encontrar oportunidades nuevas no cubiertas por PISTAS_LINEA)
    print()
    print("=" * 70)
    print("TERMINOS FRECUENTES SIN PISTA AUTOMATICA (>= 5 desc)")
    print("Estos son los que Claude debe revisar manualmente y clasificar")
    print("=" * 70)
    huerfanos_unigram = [(t, n) for t, n in unigrams_count.most_common()
                        if not pistas_para_termino(t) and n >= 5]
    huerfanos_bigram = [(t, n) for t, n in bigrams_count.most_common()
                       if not pistas_para_termino(t) and n >= 3]
    print("\nUnigramas:")
    for term, n in huerfanos_unigram[:40]:
        print(f"  {n:3d}  {term}")
    print("\nBigramas:")
    for term, n in huerfanos_bigram[:30]:
        print(f"  {n:3d}  {term}")

    print()
    print("=" * 70)
    print("FIN del analisis")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
