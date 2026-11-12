
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Verifica la antiguedad y la integridad "
        "del respaldo SQLite mas reciente."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--max-hours",
            type=int,
            default=26,
            help="Antiguedad maxima permitida en horas.",
        )

    def handle(self, *args, **options):
        max_hours = options["max_hours"]

        if max_hours <= 0:
            raise CommandError(
                "La antiguedad maxima debe ser mayor que cero."
            )

        carpeta = Path(settings.BASE_DIR) / "backups"

        if not carpeta.is_dir():
            raise CommandError(
                "No existe la carpeta de respaldos."
            )

        archivos = list(
            carpeta.glob("stockroom_*.sqlite3")
        )

        if not archivos:
            raise CommandError(
                "No se encontraron respaldos de StockroomER."
            )

        ultimo = max(
            archivos,
            key=lambda archivo: archivo.stat().st_mtime,
        )

        modificacion = datetime.fromtimestamp(
            ultimo.stat().st_mtime,
            tz=timezone.utc,
        )

        ahora = datetime.now(timezone.utc)

        antiguedad = (
            ahora - modificacion
        ).total_seconds() / 3600

        self.stdout.write(
            f"Ultimo respaldo: {ultimo.name}"
        )

        self.stdout.write(
            f"Antiguedad: {antiguedad:.2f} horas"
        )

        if antiguedad > max_hours:
            raise CommandError(
                "ALERTA: el ultimo respaldo "
                "es demasiado antiguo."
            )

        try:
            # Abrimos en modo lectura para evitar modificar
            # accidentalmente el archivo respaldado.
            uri = ultimo.resolve().as_uri() + "?mode=ro"

            with sqlite3.connect(
                uri,
                uri=True,
                timeout=10,
            ) as conexion:
                resultado = conexion.execute(
                    "PRAGMA integrity_check"
                ).fetchone()

                if resultado != ("ok",):
                    raise CommandError(
                        "ALERTA: el respaldo no supero "
                        "la verificacion de integridad."
                    )

        except sqlite3.Error as exc:
            raise CommandError(
                f"No se pudo verificar el respaldo: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "RESPALDO VERIFICADO CORRECTAMENTE"
            )
        )
