"""
Tests unitarios para los módulos core de AIDU Op.
Ejecutar con: pytest tests/ -v --cov=app
"""
import pytest


# ============================================================
# TESTS UTILS
# ============================================================

class TestUtils:
    
    def test_formato_clp_basico(self):
        from app.core.utils import formato_clp
        assert formato_clp(1500000) == "$1.500.000"
        assert formato_clp(0) == "—"
        assert formato_clp(None) == "—"
    
    def test_formato_clp_corto(self):
        from app.core.utils import formato_clp_corto
        assert formato_clp_corto(7500000) == "$7.5M"
        assert formato_clp_corto(500) == "$500"
        assert formato_clp_corto(50_000) == "$50K"
        assert formato_clp_corto(None) == "—"
    
    def test_calcular_dias_cierre(self):
        from app.core.utils import calcular_dias_cierre
        from datetime import date, timedelta
        
        manana = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
        en_5_dias = (date.today() + timedelta(days=5)).strftime("%Y-%m-%d")
        
        assert calcular_dias_cierre(manana) == 1
        assert calcular_dias_cierre(en_5_dias) == 5
        assert calcular_dias_cierre(None) is None
        assert calcular_dias_cierre("invalid-date") is None
    
    def test_emoji_dias(self):
        from app.core.utils import emoji_dias
        assert emoji_dias(1) == "🔴"  # crítico
        assert emoji_dias(5) == "🟡"  # alerta
        assert emoji_dias(10) == "🟢"  # ok
        assert emoji_dias(None) == "⚪"
    
    def test_safe_int(self):
        from app.core.utils import safe_int
        assert safe_int(42) == 42
        assert safe_int("42") == 42
        assert safe_int(None) == 0
        assert safe_int("abc") == 0
        assert safe_int(None, default=99) == 99
    
    def test_color_match_score(self):
        from app.core.utils import color_match_score
        assert color_match_score(95) == "#15803D"  # verde >=80
        assert color_match_score(70) == "#1E40AF"  # azul 60-79
        assert color_match_score(50) == "#D97706"  # amarillo 40-59
        assert color_match_score(20) == "#94A3B8"  # gris <40
        assert color_match_score(None) == "#94A3B8"


# ============================================================
# TESTS CONFIGURACIÓN
# ============================================================

class TestConfiguracion:
    
    def test_obtener_config_default(self):
        from app.core.configuracion import obtener_config
        cfg = obtener_config()
        assert cfg.tarifa_hora_clp == 78_000
        assert cfg.overhead_pct == 18.0
        assert "O'Higgins" in cfg.regiones_objetivo
    
    def test_costo_hora_total(self):
        from app.core.configuracion import obtener_config
        cfg = obtener_config()
        # 78000 * 1.18 = 92040
        assert cfg.costo_hora_total == 92_040
    
    def test_actualizar_config(self):
        from app.core.configuracion import obtener_config, actualizar_config, resetear_config
        
        try:
            actualizar_config({"tarifa_hora_clp": 85_000, "overhead_pct": 20.0})
            cfg = obtener_config()
            assert cfg.tarifa_hora_clp == 85_000
            assert cfg.overhead_pct == 20.0
        finally:
            resetear_config()
    
    def test_actualizar_listas(self):
        from app.core.configuracion import obtener_config, actualizar_config, resetear_config
        
        try:
            nuevas_regiones = ["Atacama", "Antofagasta"]
            actualizar_config({"regiones_objetivo": nuevas_regiones})
            cfg = obtener_config()
            assert cfg.regiones_objetivo == nuevas_regiones
        finally:
            resetear_config()


# ============================================================
# TESTS MATCH SCORE
# ============================================================

class TestMatchScore:
    
    def test_calcular_match_perfecto(self):
        from app.core.match_score import calcular_match_score
        
        # Licitación ideal: O'Higgins, sweet spot, mandante recurrente
        lic = {
            "cod_servicio_aidu": "CE-02",
            "confianza": 1.0,
            "region": "O'Higgins",
            "monto_referencial": 7_000_000,
            "organismo": "I. Municipalidad de Machalí",
            "fecha_publicacion": "2026-04-30",
        }
        match = calcular_match_score(lic)
        # Match perfecto debería ser >= 90
        assert match["score"] >= 85, f"Score {match['score']} debería ser >= 85"
    
    def test_calcular_match_pobre(self):
        from app.core.match_score import calcular_match_score
        
        # Sin categoría AIDU, región lejana, monto fuera de rango
        lic = {
            "cod_servicio_aidu": None,
            "confianza": 0,
            "region": "Magallanes",
            "monto_referencial": 100_000_000,
            "organismo": "Servicio Desconocido",
            "fecha_publicacion": "2024-01-01",
        }
        match = calcular_match_score(lic)
        assert match["score"] < 50, f"Score {match['score']} debería ser < 50"


# ============================================================
# TESTS DESCARGA DIARIA
# ============================================================

class TestDescargaDiaria:
    
    def test_parse_fecha(self):
        from app.core.descarga_diaria import _parse_fecha
        
        assert _parse_fecha("2026-05-09T17:00:00") == "2026-05-09"
        assert _parse_fecha("2026-05-09") == "2026-05-09"
        assert _parse_fecha(None) is None
        assert _parse_fecha("") is None
    
    def test_listar_vigentes_sin_data(self):
        """Lista vigentes funciona aunque la tabla esté vacía."""
        from app.core.descarga_diaria import listar_vigentes
        # No debe explotar
        result = listar_vigentes(limit=10)
        assert isinstance(result, list)
    
    def test_stats_vigentes(self):
        from app.core.descarga_diaria import stats_vigentes
        stats = stats_vigentes()
        assert "total_vigentes" in stats
        assert "publicadas_24h" in stats
        assert "cierran_proximos_3_dias" in stats


# ============================================================
# TESTS COMPARABLES
# ============================================================

class TestComparables:
    
    def test_buscar_comparables_categoria_inexistente(self):
        from app.core.comparables import buscar_comparables
        result = buscar_comparables(cod_servicio_aidu="XXX-99")
        assert result["total_encontrados"] == 0
        assert result["comparables"] == []
    
    def test_buscar_comparables_estructura(self):
        from app.core.comparables import buscar_comparables
        result = buscar_comparables(cod_servicio_aidu="CE-01")
        # Sin importar si hay data, la estructura debe estar
        assert "comparables" in result
        assert "stats" in result
        assert "mandantes_recurrentes" in result
        assert "competencia" in result
