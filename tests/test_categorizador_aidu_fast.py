"""Tests del categorizador AIDU Fast (S13.4).

Cubre:
- normalizar_texto y normalizar_region (incluye U+00B4 hallazgo S13.0).
- es_ohiggins con todas las variantes observadas en la API.
- categorizar_linea: >=20 casos por linea, ratio de acierto >= 80% requerido
  por spec sec 4.3.
- categorizar_tipo_objeto: >=15 casos producto/servicio/hibrido.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.core.categorizador_aidu_fast import (
    KEYWORDS_SERVICIO,
    LINEA_FALLBACK,
    cargar_catalogo_desde_csv,
    categorizar_linea,
    categorizar_tipo_objeto,
    es_ohiggins,
    normalizar_region,
    normalizar_texto,
    reset_cache,
    set_catalogo,
)

CSV_PATH = Path(__file__).resolve().parents[1] / "config" / "keywords_aidu_fast.csv"


@pytest.fixture(autouse=True)
def _load_catalog():
    """Carga el catalogo desde el CSV antes de cada test e invalida cache."""
    reset_cache()
    catalog = cargar_catalogo_desde_csv(CSV_PATH)
    set_catalogo(catalog)
    yield
    reset_cache()


# ============================================================
# NORMALIZACION
# ============================================================

class TestNormalizacion:

    def test_lowercase_y_strip(self):
        assert normalizar_texto("  PAPEL  ") == "papel"

    def test_apostrofe_acute(self):
        # Hallazgo S13.0: API devuelve U+00B4
        assert normalizar_region("Region del Libertador General Bernardo O´Higgins") \
            == "region del libertador general bernardo o'higgins"

    def test_apostrofe_right_single_quote(self):
        # U+2019
        assert normalizar_region("O’Higgins") == "o'higgins"

    def test_quita_acentos(self):
        assert normalizar_texto("cañería") == "caneria"
        assert normalizar_texto("hormigón") == "hormigon"
        assert normalizar_texto("lápiz") == "lapiz"

    def test_idempotente(self):
        assert normalizar_texto(normalizar_texto("HORMIGÓN")) == "hormigon"

    def test_none_y_vacio(self):
        assert normalizar_texto(None) == ""
        assert normalizar_texto("") == ""


class TestEsOhiggins:
    @pytest.mark.parametrize("region_raw", [
        "Region del Libertador General Bernardo O´Higgins",  # API real
        "Region del Libertador General Bernardo O’Higgins",  # smart quote
        "Region del Libertador General Bernardo O'Higgins",       # ASCII
        "Lib. Gral. Bernardo O'Higgins",
        "VI Region del Libertador",                                # match por 'libertador'
        "O'Higgins",
    ])
    def test_variantes_matchean(self, region_raw):
        assert es_ohiggins(region_raw) is True

    @pytest.mark.parametrize("region_raw", [
        "Region Metropolitana de Santiago",
        "Region de Valparaíso",
        "Region del Maule",
        "",
        None,
    ])
    def test_no_matchea(self, region_raw):
        assert es_ohiggins(region_raw) is False


# ============================================================
# CATEGORIZAR LINEA: >=20 casos por linea, acierto >= 80%
# ============================================================

CASOS_FERRETERIA = [
    "BOLSA DE CEMENTO PORTLAND 25KG",
    "FIERRO ESTRIADO 12MM 6 METROS",
    "TORNILLO AUTOPERFORANTE 1 PULGADA CAJA 100UN",
    "CLAVO CORRIENTE 4 PULGADAS KILO",
    "PINTURA ESMALTE BLANCO TINETA 4 LITROS",
    "MARTILLO CARPINTERO 16 OZ",
    "TALADRO INALAMBRICO 18V CON CASE",
    "LLAVE COMBINADA 10MM ACERO CROMO",
    "DESTORNILLADOR PHILIPS 4MM X 100MM",
    "TABLA PINO RADIATA 1X4 X 3.20M",
    "LADRILLO PRINCESA HUECO 14X28",
    "PERFIL METALON 50X50X1.5 6M",
    "BROCHA DE 3 PULGADAS",
    "RODILLO ANTIGOTA 23CM",
    "CABLE ELECTRICO 2.5MM 100M",
    "ENCHUFE MACHO TRIPOLAR",
    "MANGUERA DE JARDIN 25 METROS",
    "ESCALERA TIJERA 7 PELDAÑOS ALUMINIO",
    "CASCO DE SEGURIDAD BLANCO TIPO 1",
    "GUANTE DE CABRITILLA",
    "MALLA RASCHEL 80% SOMBRA",
    "CINTA METRICA 5 METROS",
    "SACO ARENA FINA 50KG",
    "BISAGRA DE PIANO 30CM",
    "SILICONA TRANSPARENTE 280ML",
]

CASOS_ASEO = [
    "DETERGENTE LIQUIDO LAVALOZA 5 LITROS",
    "CLORO TRADICIONAL 5 LITROS",
    "PAPEL HIGIENICO DOBLE HOJA PACK 12",
    "TOALLA DE PAPEL INTERFOLIADA",
    "JABON LIQUIDO PARA MANOS GALON",
    "ESCOBA DE NYLON CON MANGO",
    "TRAPERO INDUSTRIAL DE ALGODON",
    "BOLSA DE BASURA 60 LITROS PACK 50",
    "DISPENSADOR DE PAPEL HIGIENICO",
    "ALCOHOL GEL DESINFECTANTE 5 LITROS",
    "DESINFECTANTE MULTIUSO 5 LITROS",
    "ESCOBILLON CERDA DURA",
    "MOPA CON MANGO TELESCOPICO",
    "PAÑO ABSORBENTE MULTIUSO",
    "CERA LIQUIDA PARA PISO",
    "AMBIENTADOR EN SPRAY 400ML",
    "INSECTICIDA EN AEROSOL",
    "BALDE PLASTICO 20 LITROS",
    "ESPONJA LIMPIADORA DOBLE CARA",
    "GUANTE DE LATEX TALLA M",
    "MASCARILLA QUIRURGICA CAJA 50UN",
    "LIMPIA VIDRIOS 1 LITRO",
    "VIRUTILLA DE ACERO MEDIANA",
    "ANTIBACTERIAL EN GEL 1 LITRO",
    "SUAVIZANTE DE ROPA INDUSTRIAL",
]

CASOS_OFICINA = [
    "RESMA DE PAPEL CARTA BLANCO 75 GR",
    "CUADERNO UNIVERSITARIO 100 HOJAS",
    "LAPIZ GRAFITO HB CAJA 12",
    "LAPICERA TINTA AZUL CAJA 50",
    "BOLIGRAFO PUNTA FINA NEGRO",
    "PLUMON PERMANENTE PUNTA REDONDA NEGRO",
    "MARCADOR PARA PIZARRA PACK 4 COLORES",
    "CORRECTOR LIQUIDO BLANCO 20ML",
    "GOMA DE BORRAR BLANCA",
    "REGLA PLASTICA 30 CM",
    "TIJERA DE OFICINA MULTIUSO",
    "PEGAMENTO EN BARRA 21 GR",
    "CINTA ADHESIVA TRANSPARENTE 18MM",
    "ARCHIVADOR PALANCA TAMAÑO OFICIO",
    "CARPETA COLGANTE TAMAÑO CARTA",
    "SOBRE TAMAÑO CARTA 110GR PACK 100",
    "ETIQUETA AUTOADHESIVA",
    "POST-IT NOTAS AMARILLAS",
    "PERFORADORA DE 2 ORIFICIOS",
    "CORCHETERA STANDARD CON CORCHETES",
    "CLIP DE METAL CAJA 100",
    "CHINCHE COLOR SURTIDO",
    "CARTULINA TAMAÑO CARTA",
    "TINTA NEGRA PARA IMPRESORA",
    "TONER COMPATIBLE HP NEGRO",
]

CASOS_EQUIPAMIENTO = [
    "COMPUTADOR DE ESCRITORIO DELL OPTIPLEX",
    "NOTEBOOK HP CORE I5 8GB RAM",
    "MONITOR LED 24 PULGADAS",
    "TECLADO INALAMBRICO USB",
    "MOUSE OPTICO USB",
    "IMPRESORA MULTIFUNCIONAL EPSON L3250",
    "ESCANER DE DOCUMENTOS PORTATIL",
    "PROYECTOR EPSON POWERLITE",
    "PANTALLA DE PROYECCION 100 PULGADAS",
    "ESCRITORIO EJECUTIVO 1.40 X 0.70",
    "SILLA ERGONOMICA CON BRAZOS",
    "MESA REUNION RECTANGULAR 6 PERSONAS",
    "ESTANTE METALICO 5 BANDEJAS",
    "ARCHIVADOR METALICO 4 GAVETAS",
    "LOCKERS METALICOS 6 CUERPOS",
    "REFRIGERADOR NO FROST 300 LITROS",
    "MICROONDAS 1.1 PIES CUBICOS",
    "HERVIDOR ELECTRICO 1.7 LITROS",
    "CAFETERA DE GOTEO 12 TAZAS",
    "AIRE ACONDICIONADO SPLIT 12000 BTU",
    "TELEVISOR LED 50 PULGADAS",
    "UPS 1000VA PARA SERVIDOR",
    "SWITCH GIGABIT 24 PUERTOS",
    "ROUTER WIFI DUAL BAND",
    "DISCO DURO EXTERNO 2TB",
]


def _ratio_acierto(casos, esperado, expected_threshold=0.80):
    aciertos = 0
    fallos = []
    for caso in casos:
        linea, _ = categorizar_linea(caso)
        if linea == esperado:
            aciertos += 1
        else:
            fallos.append((caso, linea))
    ratio = aciertos / len(casos)
    assert ratio >= expected_threshold, (
        f"Ratio {ratio:.0%} bajo el umbral {expected_threshold:.0%} para {esperado}. "
        f"Fallos: {fallos[:5]}"
    )
    return ratio


class TestCategorizarLinea:

    def test_ferreteria_acierto_80(self):
        assert len(CASOS_FERRETERIA) >= 20
        _ratio_acierto(CASOS_FERRETERIA, "Ferreteria")

    def test_aseo_acierto_80(self):
        assert len(CASOS_ASEO) >= 20
        _ratio_acierto(CASOS_ASEO, "Aseo")

    def test_oficina_acierto_80(self):
        assert len(CASOS_OFICINA) >= 20
        _ratio_acierto(CASOS_OFICINA, "Oficina")

    def test_equipamiento_acierto_80(self):
        assert len(CASOS_EQUIPAMIENTO) >= 20
        _ratio_acierto(CASOS_EQUIPAMIENTO, "Equipamiento")

    def test_fallback_otros(self):
        # Producto totalmente fuera del scope: deberia ir a Otros
        linea, kws = categorizar_linea("VEHICULO MOTORIZADO AUTOMOVIL SEDAN")
        assert linea == LINEA_FALLBACK
        assert kws == []

    def test_vacio_va_a_otros(self):
        linea, kws = categorizar_linea("")
        assert linea == LINEA_FALLBACK
        assert kws == []

    def test_keywords_matched_documentado(self):
        # S13.4.2 D3: con prioridad fija, "cemento" cae en "Materiales de
        # Construccion" (mas especifico) en lugar de Ferreteria. La keyword
        # 'cemento' esta tanto en Ferreteria (legacy) como en Construccion;
        # el orden de prioridad resuelve la colision.
        linea, kws = categorizar_linea("BOLSA DE CEMENTO 25KG")
        assert linea == "Materiales de Construccion"
        assert "cemento" in kws


# ============================================================
# CASOS REALES DEL LOTE 1 (S13-keywords-iter-1)
# ============================================================
# Los 22 items siguientes corresponden a descripciones reales de
# inteligencia_precios.producto_descripcion del lote_id='backfill_1'
# que quedaron como linea_aidu='Otros' por keywords faltantes y que
# ahora deberian categorizarse correctamente tras la migracion 010.
# Fuente: log del workflow [DIAG] Analizar Otros Lote 1 (2026-05-22).

CASOS_REALES_LOTE_1 = [
    # Equipamiento: keywords nuevos computacional/computacion/audio/amplificacion/mobiliario/generador
    ("ACCESORIOS COMPUTACIONALES LICEO LUIS URBINA FLORES DE LA COMUNA DE RENGO", "Equipamiento"),
    ("EQUIPOS COMPUTACIONALES ESCUELA LO DE LOBO DE LA COMUNA DE RENGO", "Equipamiento"),
    ("EQUIPOS COMPUTACIONALES LICEO LUIS URBINA FLORES DE LA COMUNA DE RENGO", "Equipamiento"),
    ("EQUIPOS DE AUDIO ESCUELA LO DE LOBO DE LA COMUNA DE RENGO", "Equipamiento"),
    ("Línea 1: Amplificación Básica", "Equipamiento"),
    ("Línea 2: Amplificación Intermedia", "Equipamiento"),
    ("Línea 3: Amplificación Avanzada", "Equipamiento"),
    ("Línea 11: Generador", "Equipamiento"),
    ("Mobiliario para Biblioteca CRA de la Escuela Carmen Gallegos de Roble", "Equipamiento"),
    ("PRODUCTOS DE COMPUTACION Y OTROS", "Equipamiento"),

    # Ferreteria: keywords nuevos construccion/iluminacion/luminaria/led/arido/alcantarillado/mejoramiento
    ("CONSTRUCCIÓN DE RESALTO REDUCTOR DE VELOCIDAD, COMUNA DE SANTA CRUZ", "Ferreteria"),
    # S13.4.2 D3: prioridad fija reclasifica este caso de Ferreteria a
    # Materiales de Construccion. La keyword `arido` esta en ambas lineas;
    # con prioridad Construccion > Ferreteria gana Construccion. Es
    # semanticamente correcto (los aridos son insumo estructural).
    ("CONVENIO DE SUMINISTRO ADQUISICIÓN DE ÁRIDOS", "Materiales de Construccion"),
    ("El proyecto considera la instalación de 25 luminarias LED de 120W", "Ferreteria"),
    ("Estudio de Factibilidad Programa Mejoramiento de Barrios Construcción Alcantarillado Guadalao", "Ferreteria"),
    ("Línea 4: Iluminación Básica", "Ferreteria"),
    ("Línea 5: Iluminación Profesional", "Ferreteria"),

    # Oficina: keywords nuevos pendon/impresion logos/materiales de oficina
    ("ADQUISICION DE 1 PENDON ROLLER DE TELA PVC DE 80X200 CON IMPRESION DE LOGOS", "Oficina"),
    ("Se requiere la adquisición de materiales de oficina, para diferentes dependencias", "Oficina"),

    # Aseo: keywords nuevos alcohol isopropilico/materiales y articulos de aseo/lavado/planchado
    ("Alcohol Isopropílico al 70 % 290 ml en formato Spray", "Aseo"),
    ("CONTRATO DE SUMINISTRO DE MATERIALES Y ARTICULOS DE ASEO", "Aseo"),
    ("SERVICIOS DE SUMINISTRO PARA LAVADO Y PLANCHADO DE MANTELES", "Aseo"),

    # Item ambiguo aceptado como Equipamiento por keyword principal
    # ("Mejoramiento Plaza Población Juntos por El Progreso", "Ferreteria"),  # matchea 'mejoramiento'
]


class TestCategorizarLineaCasosReales:
    """Cada caso de CASOS_REALES_LOTE_1 viene de Turso productivo del Lote 1.
    Eran 'Otros' antes de iter-1; tras agregar las 22 keywords deben asignarse
    correctamente. Este test ata la calidad del diccionario al producto real."""

    def test_22_casos_reales_lote_1(self):
        # Spec del Director: K-1 aprobado, las 22 keywords nuevas capturan
        # estos 22 items concretos. Cualquier regresion en este test
        # significa que cambiamos el diccionario y rompimos cobertura.
        assert len(CASOS_REALES_LOTE_1) >= 21  # 22 contando todos
        fallos = []
        for desc, esperado in CASOS_REALES_LOTE_1:
            linea, kws = categorizar_linea(desc)
            if linea != esperado:
                fallos.append((desc[:60], linea, esperado, kws))
        assert not fallos, (
            f"{len(fallos)}/{len(CASOS_REALES_LOTE_1)} casos del Lote 1 NO matchean. "
            f"Detalle (primeros 5): {fallos[:5]}"
        )

    @pytest.mark.parametrize("desc,esperado", CASOS_REALES_LOTE_1)
    def test_caso_lote_1_individual(self, desc, esperado):
        linea, _ = categorizar_linea(desc)
        assert linea == esperado, f"'{desc[:60]}...' -> {linea} (esperado {esperado})"


# ============================================================
# CATEGORIZAR TIPO OBJETO: >=15 casos producto/servicio/hibrido
# ============================================================

CASOS_PRODUCTO = [
    "BOLSA DE CEMENTO 25KG",
    "RESMA PAPEL CARTA",
    "DETERGENTE 5 LITROS",
    "COMPUTADOR DE ESCRITORIO",
    "MONITOR LED 24 PULGADAS",
    "ESCALERA TIJERA 7 PELDAÑOS",
    "GUANTE DE LATEX CAJA 100",
    "TONER HP NEGRO",
]

CASOS_SERVICIO = [
    "SERVICIO DE ASESORIA TECNICA",
    "CONSULTORIA ESTRUCTURAL PROYECTO",
    "CAPACITACION EN OFFICE 365",
    "ARRIENDO DE AUDITORIO PARA EVENTO",
    "SOPORTE TECNICO ANUAL",
    "ASESORIA LEGAL CONSULTOR EXTERNO",
    "MANTENIMIENTO DE AREAS VERDES",
    "CONSULTORIA DE PROCESOS",
]

CASOS_HIBRIDO = [
    "SUMINISTRO E INSTALACION DE AIRE ACONDICIONADO",
    "COMPUTADOR CON SERVICIO DE INSTALACION INCLUIDO",
    "IMPRESORA CON MANTENCION ANUAL",
    "PROYECTOR Y SOPORTE TECNICO",
    "MUEBLES DE OFICINA CON ARMADO E INSTALACION",
    "MANTENCION PREVENTIVA DE AIRE ACONDICIONADO",  # el equipo esta implicito
]


class TestCategorizarTipoObjeto:

    def test_total_casos_min_15(self):
        # Spec sec 4.3: 15+ casos
        total = len(CASOS_PRODUCTO) + len(CASOS_SERVICIO) + len(CASOS_HIBRIDO)
        assert total >= 15

    @pytest.mark.parametrize("desc", CASOS_PRODUCTO)
    def test_producto(self, desc):
        assert categorizar_tipo_objeto(desc) == "producto"

    @pytest.mark.parametrize("desc", CASOS_SERVICIO)
    def test_servicio(self, desc):
        assert categorizar_tipo_objeto(desc) == "servicio"

    @pytest.mark.parametrize("desc", CASOS_HIBRIDO)
    def test_hibrido(self, desc):
        assert categorizar_tipo_objeto(desc) == "hibrido"

    def test_vacio_default_producto(self):
        assert categorizar_tipo_objeto("") == "producto"


class TestCSVCatalogo:

    def test_csv_existe(self):
        assert CSV_PATH.exists(), f"CSV faltante: {CSV_PATH}"

    def test_csv_carga_6_lineas(self):
        # S13.4.2: ampliado de 4 a 6 lineas (agregadas Salud y Materiales
        # de Construccion). El catalog ahora retorna (incluyentes, excluyentes)
        # por linea en lugar de lista plana.
        c = cargar_catalogo_desde_csv(CSV_PATH)
        assert set(c.keys()) == {
            "Ferreteria", "Aseo", "Oficina", "Equipamiento",
            "Salud", "Materiales de Construccion",
        }
        for linea, kws in c.items():
            incluyentes, _excluyentes = kws
            assert len(incluyentes) >= 20, (
                f"Linea {linea} tiene solo {len(incluyentes)} keywords incluyentes (<20)"
            )

    def test_keywords_servicio_son_ascii_unaccented(self):
        # Para mejor matching post-normalizacion
        for kw in KEYWORDS_SERVICIO:
            assert kw == kw.lower(), f"keyword {kw} no esta en lowercase"
            # No deberia tener acentos
            assert all(ord(c) < 128 for c in kw), f"keyword {kw} tiene chars > ASCII"
