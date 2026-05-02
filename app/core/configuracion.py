"""
AIDU Op · Configuración de Usuario
====================================
Reemplaza todos los hardcoded de tarifa, sweet spot, regiones, etc.
Lee/escribe la tabla config_usuario.

Uso:
    from app.core.configuracion import obtener_config, actualizar_config
    
    cfg = obtener_config()
    print(cfg.tarifa_hora_clp)
    
    actualizar_config({"tarifa_hora_clp": 80000})
"""
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field, asdict
import json

from app.db.migrator import get_connection


@dataclass
class ConfigUsuario:
    """Configuración del usuario, leída desde la tabla config_usuario."""
    
    # Identidad
    nombre_completo: str = "Ignacio Vidiella González"
    rut: str = "16.402.949-2"
    profesion: str = "Ingeniero Civil"
    empresa: str = "AIDU Op SpA"
    email_contacto: str = ""
    telefono: str = ""
    
    # Economía
    tarifa_hora_clp: int = 78_000
    overhead_pct: float = 18.0
    margen_objetivo_pct: float = 22.0
    margen_minimo_pct: float = 12.0
    
    # Sweet spot
    sweet_spot_min_clp: int = 3_000_000
    sweet_spot_max_clp: int = 15_000_000
    rango_aceptable_min_clp: int = 1_500_000
    rango_aceptable_max_clp: int = 30_000_000
    
    # Filtros (listas serializadas como JSON)
    regiones_objetivo: List[str] = field(default_factory=lambda: ["O'Higgins", "Metropolitana", "Maule", "Valparaíso"])
    categorias_objetivo: List[str] = field(default_factory=lambda: ["CE-01", "CE-02", "CE-06", "GP-04"])
    mandantes_recurrentes: List[str] = field(default_factory=lambda: ["I. Municipalidad de Machalí"])
    
    # Pesos match score
    peso_categoria: int = 35
    peso_region: int = 20
    peso_monto: int = 20
    peso_mandante: int = 10
    peso_recencia: int = 15
    
    # Notificaciones
    email_notificaciones: str = ""
    notif_diario_habilitado: bool = True
    notif_semanal_habilitado: bool = True
    
    # Storage
    google_drive_folder_id: str = ""
    
    @property
    def costo_hora_total(self) -> int:
        """Tarifa hora + overhead aplicado."""
        return int(self.tarifa_hora_clp * (1 + self.overhead_pct / 100))


def obtener_config() -> ConfigUsuario:
    """Lee la configuración de la tabla. Si no existe, devuelve defaults."""
    conn = get_connection()
    try:
        # Asegurar que existe fila default
        conn.execute("INSERT OR IGNORE INTO config_usuario (id) VALUES (1)")
        conn.commit()
        
        row = conn.execute("SELECT * FROM config_usuario WHERE id = 1").fetchone()
        if not row:
            return ConfigUsuario()
        
        d = dict(row)
        
        # Deserializar campos JSON
        for campo in ["regiones_objetivo", "categorias_objetivo", "mandantes_recurrentes"]:
            if campo in d and d[campo]:
                try:
                    d[campo] = json.loads(d[campo])
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Convertir int a bool
        for campo in ["notif_diario_habilitado", "notif_semanal_habilitado"]:
            if campo in d:
                d[campo] = bool(d[campo])
        
        # Filtrar campos que no existen en el dataclass
        campos_validos = {f.name for f in ConfigUsuario.__dataclass_fields__.values()}
        d_filtrado = {k: v for k, v in d.items() if k in campos_validos and v is not None}
        
        return ConfigUsuario(**d_filtrado)
    finally:
        conn.close()


def actualizar_config(cambios: Dict[str, Any]) -> ConfigUsuario:
    """
    Actualiza campos específicos. Devuelve la config actualizada.
    
    Ejemplo:
        actualizar_config({"tarifa_hora_clp": 80000, "overhead_pct": 20})
    """
    conn = get_connection()
    try:
        # Serializar listas como JSON
        cambios_serializados = {}
        for k, v in cambios.items():
            if isinstance(v, (list, tuple)):
                cambios_serializados[k] = json.dumps(list(v))
            elif isinstance(v, bool):
                cambios_serializados[k] = 1 if v else 0
            else:
                cambios_serializados[k] = v
        
        # Construir UPDATE dinámico
        if not cambios_serializados:
            return obtener_config()
        
        set_clause = ", ".join(f"{k} = ?" for k in cambios_serializados.keys())
        valores = list(cambios_serializados.values())
        
        conn.execute(
            f"UPDATE config_usuario SET {set_clause}, fecha_modificacion = datetime('now', 'localtime') WHERE id = 1",
            valores
        )
        conn.commit()
        
        return obtener_config()
    finally:
        conn.close()


def resetear_config() -> ConfigUsuario:
    """Resetea a valores default."""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM config_usuario WHERE id = 1")
        conn.execute("INSERT INTO config_usuario (id) VALUES (1)")
        conn.commit()
        return obtener_config()
    finally:
        conn.close()
