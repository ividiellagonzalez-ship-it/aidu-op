"""
AIDU Op · CLI Principal
========================
Punto de entrada para operaciones de administración:
  python -m app.cli init                # Inicializar sistema (migraciones)
  python -m app.cli backfill            # Backfill 24 meses
  python -m app.cli update              # Actualización incremental diaria
  python -m app.cli status              # Estado de la BD
  python -m app.cli migrations          # Ver estado migraciones
  python -m app.cli backup              # Backup manual
  python -m app.cli restore <archivo>   # Restaurar backup
"""
import sys
import argparse
import logging
from pathlib import Path
from datetime import date

# Logging hacia archivo + consola
def setup_logging():
    from config.settings import LOG_FILE
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)-25s | %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )


def cmd_init(args):
    """Inicializa la BD ejecutando migraciones"""
    from app.db.migrator import run_migrations, show_migration_status
    from config.settings import get_version, write_installed_version, AIDU_HOME

    print(f"\n🔧 Inicializando AIDU Op v{get_version()}")
    print(f"   Home: {AIDU_HOME}")

    n, applied = run_migrations()
    if n > 0:
        print(f"\n✅ {n} migración(es) aplicada(s):")
        for m in applied:
            print(f"   • {m}")
    else:
        print("\nℹ️  Sistema ya está al día")

    write_installed_version(get_version())
    show_migration_status()


def cmd_backfill(args):
    """Backfill MVP: pocos días (rápido, costo bajo)"""
    from app.core.backfill import ejecutar_backfill_dias
    print(f"\n📥 Descarga histórico de {args.dias} días")
    print(f"   ~{args.dias} días × ~50 licitaciones/día = ~{args.dias*50} registros")
    print(f"   Tiempo estimado: {args.dias*1.5:.0f} - {args.dias*3:.0f} minutos\n")

    if not args.yes:
        respuesta = input("¿Continuar? (s/N): ").strip().lower()
        if respuesta != "s":
            print("Cancelado")
            return

    result = ejecutar_backfill_dias(dias=args.dias)
    print(f"\n📊 RESULTADO:")
    print(f"   Días procesados: {result['dias_procesados']}")
    print(f"   Licitaciones descargadas: {result['total_descargadas']}")
    print(f"   Nuevas en BD: {result['nuevas']}")
    print(f"   Duración: {result['duracion_minutos']} minutos")


def cmd_update(args):
    """Actualización incremental diaria"""
    from app.core.backfill import actualizacion_incremental
    result = actualizacion_incremental(dias_lookback=args.dias)
    print(f"✅ Incremental: {result['total']} revisadas, {result['nuevas']} nuevas")


def cmd_status(args):
    """Estado de la BD"""
    from app.core.backfill import estado_actual
    from config.settings import get_version, get_installed_version

    print(f"\n📊 AIDU Op · Estado del Sistema")
    print(f"   Versión código: {get_version()}")
    print(f"   Versión instalada: {get_installed_version() or 'No inicializado'}")
    print()

    estado = estado_actual()
    print(f"📥 Histórico Mercado Público:")
    print(f"   Licitaciones indexadas: {estado['licitaciones_historicas']:,}")
    print(f"   Categorizadas AIDU: {estado['categorizadas_aidu']:,}")
    print(f"   Backfill completado: {'✅' if estado['backfill_completado'] else '❌'}")
    print(f"   Última ingesta: {estado['ultima_ingesta'] or 'Nunca'}")
    print(f"   Total ingestas: {estado['ingestas_ejecutadas']:,}")
    print()
    print(f"📂 Cartera AIDU Op:")
    print(f"   Proyectos en cartera: {estado['proyectos_cartera']:,}")


def cmd_migrations(args):
    """Estado de migraciones"""
    from app.db.migrator import show_migration_status
    show_migration_status()


def cmd_backup(args):
    """Backup manual"""
    from app.db.migrator import backup_database
    path = backup_database()
    if path:
        print(f"✅ Backup creado: {path}")
    else:
        print("ℹ️  No hay BD que respaldar todavía")


def cmd_restore(args):
    """Restaurar desde backup"""
    import shutil
    from config.settings import DB_PATH, BACKUP_DIR

    backup_file = Path(args.archivo)
    if not backup_file.exists():
        backup_file = BACKUP_DIR / args.archivo

    if not backup_file.exists():
        print(f"❌ No encontrado: {args.archivo}")
        print(f"\nBackups disponibles en {BACKUP_DIR}:")
        for b in sorted(BACKUP_DIR.glob("*.db")):
            print(f"   • {b.name}")
        return

    # Backup actual antes de restaurar
    if DB_PATH.exists():
        from app.db.migrator import backup_database
        path_actual = backup_database()
        print(f"📦 Backup de la BD actual: {path_actual}")

    shutil.copy2(backup_file, DB_PATH)
    print(f"✅ Restaurada desde: {backup_file}")


def cmd_seed_demo(args):
    """Cargar/limpiar datos demo"""
    from app.core.seed_demo import seed_demo, clean_demo
    if args.clean:
        clean_demo()
    else:
        seed_demo(con_cartera=True)


def main():
    setup_logging()

    parser = argparse.ArgumentParser(
        description="AIDU Op CLI · Sistema de Gestión Comercial B2G"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init", help="Inicializar sistema (migraciones)").set_defaults(func=cmd_init)

    p_bf = sub.add_parser("backfill", help="Backfill MVP de pocos dias")
    p_bf.add_argument("--dias", type=int, default=14, help="Cuantos dias atras descargar (default: 14)")
    p_bf.add_argument("--yes", action="store_true", help="Sin confirmacion")
    p_bf.set_defaults(func=cmd_backfill)

    p_up = sub.add_parser("update", help="Actualización incremental")
    p_up.add_argument("--dias", type=int, default=7)
    p_up.set_defaults(func=cmd_update)

    sub.add_parser("status", help="Estado del sistema").set_defaults(func=cmd_status)
    sub.add_parser("migrations", help="Estado migraciones").set_defaults(func=cmd_migrations)
    sub.add_parser("backup", help="Backup manual de la BD").set_defaults(func=cmd_backup)

    p_res = sub.add_parser("restore", help="Restaurar desde backup")
    p_res.add_argument("archivo", help="Nombre del archivo de backup")
    p_res.set_defaults(func=cmd_restore)

    p_seed = sub.add_parser("seed-demo", help="Cargar datos demo para probar la UI")
    p_seed.add_argument("--clean", action="store_true", help="Eliminar datos demo")
    p_seed.set_defaults(func=cmd_seed_demo)

    args = parser.parse_args()
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n⚠️  Interrumpido por el usuario")
        sys.exit(1)


if __name__ == "__main__":
    main()
