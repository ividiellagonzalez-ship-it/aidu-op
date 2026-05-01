"""
AIDU Op · Seed de datos demo
=============================
Llena la BD con datos simulados realistas para validar la UI
sin tener que esperar el backfill 24m del API real.

Usar:
    python -m app.cli seed-demo

Borra los datos demo después con:
    python -m app.cli seed-demo --clean
"""
import logging
from datetime import date, timedelta
import random

from app.db.migrator import get_connection
from app.core.ingesta import upsert_licitacion, ingestar_lote

logger = logging.getLogger(__name__)


# Catálogo de licitaciones simuladas realistas
LICITACIONES_DEMO = [
    # ============ CE-02 Cálculo Estructural ============
    {"CodigoExterno": "2641-89-LE25", "Nombre": "Cálculo estructural ampliación sala cuna La Compañía",
     "Descripcion": "Servicio de cálculo y memoria estructural para ampliación. Planos estructurales, memoria sismorresistente, especificaciones técnicas.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Graneros", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 6500000, "Adjudicacion": {"MontoAdjudicado": 5750000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "2641-156-L125", "Nombre": "Cálculo estructural sede vecinal Las Mercedes",
     "Descripcion": "Cálculo estructural y memoria de cálculo sismorresistente para sede vecinal. Hormigón armado, planos.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Graneros", "RegionUnidad": "O'Higgins"},
     "Tipo": "L1", "MontoEstimado": 5800000, "Adjudicacion": {"MontoAdjudicado": 5100000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "3000-234-LE25", "Nombre": "Cálculo y planos estructurales Casa de Acogida",
     "Descripcion": "Cálculo estructural completo, planos, memoria sismorresistente en hormigón armado.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Machalí", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 7200000, "Adjudicacion": {"MontoAdjudicado": 6800000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "5500-78-L125", "Nombre": "Memoria de cálculo estructural ampliación posta rural",
     "Descripcion": "Memoria de cálculo estructural sismorresistente para ampliación posta rural en hormigón armado.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Olivar", "RegionUnidad": "O'Higgins"},
     "Tipo": "L1", "MontoEstimado": 4900000, "Adjudicacion": {"MontoAdjudicado": 4350000}, "Estado": "Adjudicada"},

    # ============ CE-01 Diagnóstico Estructural ============
    {"CodigoExterno": "3000-145-LE25", "Nombre": "Diagnóstico estructural edificio consistorial",
     "Descripcion": "Diagnóstico estructural integral, inspección visual, evaluación de patologías post-sismo, ensayos no destructivos, informe técnico.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Machalí", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 8500000, "Adjudicacion": {"MontoAdjudicado": 7820000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "3000-234-L125", "Nombre": "Inspección y diagnóstico estructural edificio municipal",
     "Descripcion": "Inspección estructural y evaluación de daños sismo. Diagnóstico técnico de patologías.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Rancagua", "RegionUnidad": "O'Higgins"},
     "Tipo": "L1", "MontoEstimado": 9200000, "Adjudicacion": {"MontoAdjudicado": 7820000}, "Estado": "Adjudicada"},

    # ============ GP-04 Levantamiento Procesos ============
    {"CodigoExterno": "3500-67-LE25", "Nombre": "Levantamiento y rediseño procesos operacionales DOM",
     "Descripcion": "Consultoría BPM para levantamiento, mapeo y rediseño de procesos operacionales en Dirección de Obras Municipales. Manual procedimientos.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Doñihue", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 7200000, "Adjudicacion": {"MontoAdjudicado": 6480000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "8800-189-LE25", "Nombre": "Mapeo de procesos administrativos municipales",
     "Descripcion": "Levantamiento y mapeo de procesos. Rediseño operacional, BPM, manual de procedimientos administrativos.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Olivar", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 6800000, "Adjudicacion": {"MontoAdjudicado": 5780000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "5500-234-L125", "Nombre": "Consultoría rediseño procesos GORE",
     "Descripcion": "Levantamiento, mapeo y rediseño de procesos operacionales del Gobierno Regional. BPM completo.",
     "Comprador": {"NombreOrganismo": "Gobierno Regional O'Higgins", "RegionUnidad": "O'Higgins"},
     "Tipo": "L1", "MontoEstimado": 9500000, "Adjudicacion": {"MontoAdjudicado": 7600000}, "Estado": "Adjudicada"},

    # ============ IA-02 Análisis Datos / Dashboards ============
    {"CodigoExterno": "1057-156-LE25", "Nombre": "Implementación dashboard analítico de gestión municipal",
     "Descripcion": "Desarrollo dashboard digital con análisis de datos, KPIs municipales, visualización Power BI. Integración sistemas existentes, reportería.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Rancagua", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 22000000, "Adjudicacion": {"MontoAdjudicado": 17600000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "5500-345-LE25", "Nombre": "Plataforma BI para Gobierno Regional",
     "Descripcion": "Análisis de datos, dashboard Power BI, visualización de indicadores, reportería automática.",
     "Comprador": {"NombreOrganismo": "Gobierno Regional Maule", "RegionUnidad": "Maule"},
     "Tipo": "LE", "MontoEstimado": 28000000, "Adjudicacion": {"MontoAdjudicado": 22400000}, "Estado": "Adjudicada"},

    # ============ CE-05 Peritaje ============
    {"CodigoExterno": "3000-289-L125", "Nombre": "Peritaje estructural edificios post-sismo",
     "Descripcion": "Peritaje estructural, inspección de daños sismo, informe técnico de patologías y recomendaciones.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Machalí", "RegionUnidad": "O'Higgins"},
     "Tipo": "L1", "MontoEstimado": 5500000, "Adjudicacion": {"MontoAdjudicado": 5500000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "5500-145-LE25", "Nombre": "Peritaje y evaluación estructural edificio antiguo",
     "Descripcion": "Peritaje estructural, evaluación daños, inspección, informe judicial.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Olivar", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 4800000, "Adjudicacion": {"MontoAdjudicado": 4560000}, "Estado": "Adjudicada"},

    # ============ CE-06 Apoyo SECPLAN ============
    {"CodigoExterno": "3994-78-LE25", "Nombre": "Apoyo SECPLAN: revisión bases técnicas obras",
     "Descripcion": "Apoyo técnico SECPLAN: revisión de bases técnicas, cubicaciones, especificaciones técnicas para proyectos municipales.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Olivar", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 3800000, "Adjudicacion": {"MontoAdjudicado": 3420000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "8800-67-L125", "Nombre": "Apoyo SECPLAN cubicación y especificaciones",
     "Descripcion": "Apoyo técnico SECPLAN, cubicación y especificaciones técnicas para sede vecinal.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Doñihue", "RegionUnidad": "O'Higgins"},
     "Tipo": "L1", "MontoEstimado": 4200000, "Adjudicacion": {"MontoAdjudicado": 3780000}, "Estado": "Adjudicada"},

    # ============ GP-05 Diseño KPIs ============
    {"CodigoExterno": "2800-234-LE25", "Nombre": "Diseño KPIs y tablero de control SECPLAN",
     "Descripcion": "Diseño de indicadores KPI, tablero de control, dashboard de gestión, medición de rendimiento.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Rengo", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 6800000, "Adjudicacion": {"MontoAdjudicado": 6120000}, "Estado": "Adjudicada"},

    # ============ IA-01 Transformación Digital ============
    {"CodigoExterno": "4521-189-LE25", "Nombre": "Asesoría transformación digital con inteligencia artificial",
     "Descripcion": "Asesoría en transformación digital, automatización de procesos administrativos con inteligencia artificial.",
     "Comprador": {"NombreOrganismo": "Gobierno Regional O'Higgins", "RegionUnidad": "O'Higgins"},
     "Tipo": "LE", "MontoEstimado": 45000000, "Adjudicacion": {"MontoAdjudicado": 38250000}, "Estado": "Adjudicada"},

    # === Licitaciones que NO matchean perfil AIDU (control) ===
    {"CodigoExterno": "9999-001-L125", "Nombre": "Suministro cemento Portland obras viales",
     "Descripcion": "Compra de 50 toneladas de cemento Portland tipo I para reparación de pavimentos.",
     "Comprador": {"NombreOrganismo": "Vialidad Región O'Higgins", "RegionUnidad": "O'Higgins"},
     "Tipo": "L1", "MontoEstimado": 2000000, "Adjudicacion": {"MontoAdjudicado": 1800000}, "Estado": "Adjudicada"},
    {"CodigoExterno": "9999-002-L125", "Nombre": "Servicio de aseo y mantención edificio",
     "Descripcion": "Servicio mensual de aseo y mantención de edificio municipal.",
     "Comprador": {"NombreOrganismo": "I. Municipalidad de Rancagua", "RegionUnidad": "O'Higgins"},
     "Tipo": "L1", "MontoEstimado": 8000000, "Adjudicacion": {"MontoAdjudicado": 7500000}, "Estado": "Adjudicada"},
]


# Cartera demo de proyectos en distintos estados
CARTERA_DEMO = [
    {
        "codigo_externo": "3000-547-LE26",
        "nombre": "Diagnóstico estructural Centro Comunitario Machalí",
        "descripcion": "Diagnóstico estructural en sitio. Visita técnica, ensayos no destructivos, informe técnico final.",
        "organismo": "I. Municipalidad de Machalí",
        "region": "O'Higgins",
        "monto_referencial": 8500000,
        "fecha_cierre": (date.today() + timedelta(days=12)).isoformat(),
        "cod_servicio_aidu": "CE-01",
        "estado": "PROSPECTO",
        "hh_ignacio_estimado": 40,
        "hh_jorella_estimado": 8,
    },
    {
        "codigo_externo": "2641-122-L126",
        "nombre": "Cálculo estructural ampliación sala cuna La Compañía",
        "descripcion": "Cálculo y memoria estructural. Planos, memoria sismorresistente.",
        "organismo": "I. Municipalidad de Graneros",
        "region": "O'Higgins",
        "monto_referencial": 6200000,
        "fecha_cierre": (date.today() + timedelta(days=18)).isoformat(),
        "cod_servicio_aidu": "CE-02",
        "estado": "ESTUDIO",
        "hh_ignacio_estimado": 90,
        "hh_jorella_estimado": 10,
    },
    {
        "codigo_externo": "3500-89-LE26",
        "nombre": "Levantamiento y rediseño procesos operacionales DOM",
        "descripcion": "Consultoría para levantamiento BPM. Manual de procedimientos.",
        "organismo": "I. Municipalidad de Doñihue",
        "region": "O'Higgins",
        "monto_referencial": 7500000,
        "fecha_cierre": (date.today() + timedelta(days=14)).isoformat(),
        "cod_servicio_aidu": "GP-04",
        "estado": "EN_PREPARACION",
        "hh_ignacio_estimado": 60,
        "hh_jorella_estimado": 50,
    },
    {
        "codigo_externo": "3994-89-L126",
        "nombre": "Apoyo técnico SECPLAN: revisión bases sede vecinal",
        "descripcion": "Apoyo SECPLAN: revisión bases técnicas, cubicaciones.",
        "organismo": "I. Municipalidad de Olivar",
        "region": "O'Higgins",
        "monto_referencial": 3800000,
        "fecha_cierre": (date.today() + timedelta(days=8)).isoformat(),
        "cod_servicio_aidu": "CE-06",
        "estado": "LISTO_OFERTAR",
        "hh_ignacio_estimado": 20,
        "hh_jorella_estimado": 15,
        "escenario_elegido": "competitivo",
        "precio_ofertado": 3420000,
    },
]


def seed_demo(con_cartera: bool = True):
    """Carga datos demo en la BD"""
    print(f"📥 Cargando {len(LICITACIONES_DEMO)} licitaciones simuladas...")
    stats = ingestar_lote(LICITACIONES_DEMO, fecha=date.today())
    print(f"   ✅ Nuevas: {stats['nuevas']} · Actualizadas: {stats['actualizadas']}")

    if con_cartera:
        print(f"\n📂 Cargando {len(CARTERA_DEMO)} proyectos en cartera...")
        conn = get_connection()
        try:
            for p in CARTERA_DEMO:
                conn.execute("""
                    INSERT OR REPLACE INTO aidu_proyectos (
                        codigo_externo, nombre, descripcion, organismo, region,
                        monto_referencial, fecha_cierre, cod_servicio_aidu, estado,
                        hh_ignacio_estimado, hh_jorella_estimado,
                        escenario_elegido, precio_ofertado
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    p["codigo_externo"], p["nombre"], p["descripcion"],
                    p["organismo"], p["region"], p["monto_referencial"],
                    p["fecha_cierre"], p["cod_servicio_aidu"], p["estado"],
                    p["hh_ignacio_estimado"], p["hh_jorella_estimado"],
                    p.get("escenario_elegido"), p.get("precio_ofertado")
                ))
            conn.commit()
            print(f"   ✅ Cartera cargada")
        finally:
            conn.close()

    print("\n🎯 Demo listo. Ahora puedes lanzar la UI:")
    print("   streamlit run app/ui/streamlit_app.py")


def clean_demo():
    """Limpia los datos demo. Borra primero categorizaciones y proyectos, luego licitaciones."""
    conn = get_connection()
    try:
        # 1. Eliminar categorizaciones primero (FK)
        n_cat = conn.execute("""
            DELETE FROM mp_categorizacion_aidu
            WHERE codigo_externo IN (
                SELECT codigo_externo FROM mp_licitaciones_adj
                WHERE raw_json LIKE '%"_demo": true%' OR codigo_externo LIKE '%-LE25' OR codigo_externo LIKE '%-L125'
            )
        """).rowcount
        n_proy = conn.execute("DELETE FROM aidu_proyectos WHERE codigo_externo LIKE '%-LE26' OR codigo_externo LIKE '%-L126'").rowcount
        n_lic = conn.execute("DELETE FROM mp_licitaciones_adj WHERE codigo_externo LIKE '%-LE25' OR codigo_externo LIKE '%-L125'").rowcount
        conn.commit()
        print(f"🧹 Eliminados: {n_lic} licitaciones, {n_cat} categorizaciones, {n_proy} proyectos")
    finally:
        conn.close()
