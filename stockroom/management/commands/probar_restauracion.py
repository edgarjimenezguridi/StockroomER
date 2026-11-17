"""Comprueba una restauración de SQLite sin tocar la base activa."""

import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


def verificar_integridad(conexion):
    filas = conexion.execute("PRAGMA integrity_check").fetchall()
    if filas != [("ok",)]:
        raise CommandError("La base no superó PRAGMA integrity_check.")


def contar_registros(conexion):
    """Cuenta las filas de cada tabla; no lee ni muestra datos privados."""
    tablas = [
        fila[0]
        for fila in conexion.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
    ]
    resultado = {}
    for nombre in tablas:
        identificador = '"' + nombre.replace('"', '""') + '"'
        resultado[nombre] = conexion.execute(
            f"SELECT COUNT(*) FROM {identificador}"
        ).fetchone()[0]
    return resultado


class Command(BaseCommand):
    help = "Ensaya restaurar un respaldo SQLite en una carpeta temporal, sin modificar la base activa."

    def add_arguments(self, parser):
        parser.add_argument(
            "--archivo",
            help="Ruta de un respaldo SQLite. Por defecto, se utiliza el más reciente de backups/.",
        )

    def handle(self, *args, **options):
        if options["archivo"]:
            origen = Path(options["archivo"]).expanduser().resolve()
        else:
            carpeta = Path(settings.BASE_DIR) / "backups"
            archivos = list(carpeta.glob("stockroom_*.sqlite3")) if carpeta.is_dir() else []
            if not archivos:
                raise CommandError("No se encontraron respaldos en backups/.")
            try:
                origen = max(archivos, key=lambda p: p.stat().st_mtime).resolve()
            except OSError as exc:
                raise CommandError(f"No se pudo localizar el respaldo: {exc}") from exc

        if not origen.is_file():
            raise CommandError(f"No existe el respaldo: {origen}")

        try:
            # El origen se abre exclusivamente en modo lectura.
            uri = origen.as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True, timeout=30)) as fuente:
                verificar_integridad(fuente)
                esperados = contar_registros(fuente)

                # TemporaryDirectory crea la copia fuera del proyecto; se elimina al salir.
                with TemporaryDirectory(prefix="stockroom_restauracion_") as temporal:
                    destino = Path(temporal) / "restauracion_prueba.sqlite3"
                    with closing(sqlite3.connect(str(destino), timeout=30)) as copia:
                        fuente.backup(copia)

                    # Volvemos a abrir el archivo restaurado para comprobarlo.
                    with closing(sqlite3.connect(str(destino), timeout=30)) as restaurada:
                        verificar_integridad(restaurada)
                        obtenidos = contar_registros(restaurada)

                    if esperados != obtenidos:
                        raise CommandError(
                            "La restauración no conservó el número de registros por tabla."
                        )
        except (OSError, sqlite3.Error) as exc:
            raise CommandError(f"No se pudo completar la restauración de prueba: {exc}") from exc

        self.stdout.write(f"Respaldo comprobado: {origen.name}")
        self.stdout.write(f"Tablas comparadas: {len(esperados)}")
        self.stdout.write(self.style.SUCCESS("RESTAURACION DE PRUEBA CORRECTA"))
        self.stdout.write("La base de datos activa no fue modificada.")
