"""Empareja un destino y copia un respaldo SQLite verificado al SSD externo."""
import hashlib
import time
import secrets
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

MARKER_NAME = ".stockroomer_backup_id"


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_sqlite(path):
    try:
        # Modo solo lectura: no crea ni modifica el archivo consultado.
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=15)) as db:
            result = db.execute("PRAGMA integrity_check").fetchone()
            if result != ("ok",):
                raise CommandError(f"El archivo no superó integrity_check: {path.name}")
    except sqlite3.Error as exc:
        raise CommandError(f"No se pudo verificar {path.name}: {exc}") from exc


class Command(BaseCommand):
    help = "Empareja un SSD externo y copia al mismo el último respaldo SQLite verificado."

    def add_arguments(self, parser):
        parser.add_argument("--destination", required=True, help="Carpeta del SSD USB, por ejemplo E:\\StockroomER_Respaldos")
        parser.add_argument("--pair", action="store_true", help="Empareja por primera vez la carpeta de destino (no copia datos)")
        parser.add_argument("--max-hours", type=int, default=26, help="Antigüedad máxima del respaldo local en horas (predeterminado: 26)")

    def handle(self, *args, **options):
        if options["max_hours"] <= 0:
            raise CommandError("--max-hours debe ser mayor que cero.")
        root = Path(settings.BASE_DIR).resolve()
        local = root / "backups"
        target = Path(options["destination"]).resolve()

        if not target.is_dir():
            raise CommandError("La carpeta de destino no existe. Conecta el SSD y créala antes.")
        if target == local or target.is_relative_to(root):
            raise CommandError("El destino debe estar fuera de la carpeta del proyecto.")

        local.mkdir(parents=True, exist_ok=True)
        local_marker = local / MARKER_NAME
        external_marker = target / MARKER_NAME

        if options["pair"]:
            if external_marker.exists():
                raise CommandError("El destino ya tiene un identificador. No se sobrescribirá.")
            if not local_marker.exists():
                local_marker.write_text(secrets.token_hex(32), encoding="ascii")
            token = local_marker.read_text(encoding="ascii").strip()
            if not token:
                raise CommandError("Identificador local inválido.")
            # x evita sobrescribir otro emparejamiento por accidente.
            with external_marker.open("x", encoding="ascii") as file:
                file.write(token)
            self.stdout.write(self.style.SUCCESS("SSD emparejado. No se copió ninguna base de datos."))
            return

        if not local_marker.is_file() or not external_marker.is_file():
            raise CommandError("SSD no emparejado. Revisa el dispositivo y ejecuta --pair una sola vez.")
        if local_marker.read_text(encoding="ascii").strip() != external_marker.read_text(encoding="ascii").strip():
            raise CommandError("Identificador incorrecto: se rechaza la copia al destino.")

        files = [p for p in local.glob("stockroom_*.sqlite3") if p.is_file()]
        if not files:
            raise CommandError("No hay respaldos locales; ejecuta primero respaldo_almacen.")
        source = max(files, key=lambda p: (p.stat().st_mtime_ns, p.name))
        age_hours = (time.time() - source.stat().st_mtime) / 3600
        if age_hours > options["max_hours"]:
            raise CommandError("El respaldo local es demasiado antiguo; genera uno nuevo antes de copiar.")
        _check_sqlite(source)

        final = target / source.name
        partial = target / (source.name + ".partial")
        if final.exists() or partial.exists():
            raise CommandError("El respaldo ya existe o hay una copia incompleta. No se sobrescribirá.")

        try:
            with source.open("rb") as src, partial.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            if _sha256(source) != _sha256(partial):
                raise CommandError("Falló la comprobación SHA-256 del archivo copiado.")
            _check_sqlite(partial)
            partial.rename(final)
        finally:
            if partial.exists():
                partial.unlink()

        self.stdout.write(self.style.SUCCESS(f"Respaldo copiado y verificado: {final}"))
        self.stdout.write(f"SHA-256: {_sha256(final)}")
