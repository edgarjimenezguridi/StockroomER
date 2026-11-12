
import sqlite3
from contextlib import closing
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.utils import timezone


class Command(BaseCommand):
    help = (
        "Crea y verifica un respaldo consistente "
        "de la base de datos SQLite de StockroomER."
    )

    def handle(self, *args, **options):
        database = connections["default"].settings_dict

        if database["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError(
                "Este comando solo admite SQLite. "
                "Para PostgreSQL utilizaremos pg_dump."
            )

        origen = Path(database["NAME"]).resolve()

        if not origen.is_file():
            raise CommandError(
                f"No existe la base de datos: {origen}"
            )

        carpeta = Path(settings.BASE_DIR) / "backups"
        carpeta.mkdir(parents=True, exist_ok=True)

        fecha = timezone.localtime().strftime(
            "%Y%m%d_%H%M%S_%f"
        )

        destino = carpeta / f"stockroom_{fecha}.sqlite3"
        temporal = carpeta / f"stockroom_{fecha}.tmp"

        self.stdout.write(
            "Iniciando respaldo de StockroomER..."
        )

        try:
            # closing() garantiza que ambas conexiones
            # SQLite se cierren antes de renombrar el archivo.
            with closing(
                sqlite3.connect(str(origen), timeout=30)
            ) as fuente:

                with closing(
                    sqlite3.connect(str(temporal), timeout=30)
                ) as copia:

                    fuente.backup(copia)

            # Abrir el respaldo temporal para verificar
            # su integridad y cerrar la conexión después.
            with closing(
                sqlite3.connect(str(temporal), timeout=30)
            ) as verificacion:

                resultado = verificacion.execute(
                    "PRAGMA integrity_check"
                ).fetchone()

                if not resultado or resultado[0] != "ok":
                    raise CommandError(
                        "El respaldo no superó la "
                        "verificación de integridad."
                    )

            # En este punto todas las conexiones
            # al archivo temporal ya están cerradas.
            temporal.replace(destino)

        except (OSError, sqlite3.Error) as exc:
            raise CommandError(
                f"No se pudo crear el respaldo: {exc}"
            ) from exc

        finally:
            if temporal.exists():
                try:
                    temporal.unlink()
                except OSError:
                    self.stderr.write(
                        "Aviso: no se pudo eliminar el archivo "
                        "temporal. Puedes revisarlo después."
                    )

        tamano_mb = destino.stat().st_size / (1024 * 1024)

        self.stdout.write(
            self.style.SUCCESS(
                "Respaldo creado y verificado correctamente."
            )
        )

        self.stdout.write(f"Archivo: {destino}")
        self.stdout.write(f"Tamaño: {tamano_mb:.2f} MB")
