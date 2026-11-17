"""Pruebas seguras: no requieren un SSD ni modifican datos reales."""
import io
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class CopiarRespaldoUSBTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name) / "proyecto"
        self.base.mkdir()
        self.destino = Path(self.temp.name) / "usb"
        self.destino.mkdir()
        (self.base / "backups").mkdir()
        self.override = override_settings(BASE_DIR=self.base)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.backup = self.base / "backups" / "stockroom_20261117_120000_000001.sqlite3"
        # En Windows, el context manager de sqlite3 NO cierra la conexión.
        # closing() libera el archivo antes de eliminar el directorio temporal.
        with closing(sqlite3.connect(self.backup)) as db:
            with db:
                db.execute("CREATE TABLE prueba (valor TEXT)")
                db.execute("INSERT INTO prueba VALUES ('inventario')")

    def ejecutar(self, *args):
        out = io.StringIO()
        call_command("copiar_respaldo_usb", "--destination", str(self.destino), *args, stdout=out)
        return out.getvalue()

    def test_emparejar_y_copiar_respaldo_verificado(self):
        self.ejecutar("--pair")
        salida = self.ejecutar()
        self.assertIn("Respaldo copiado y verificado", salida)
        copia = self.destino / self.backup.name
        self.assertTrue(copia.exists())
        with closing(sqlite3.connect(copia)) as db:
            self.assertEqual(
                db.execute("SELECT valor FROM prueba").fetchone(),
                ("inventario",),
            )
        with self.assertRaises(CommandError):
            self.ejecutar()  # Nunca sobrescribe un respaldo existente.

    def test_rechaza_ssd_con_identificador_incorrecto(self):
        self.ejecutar("--pair")
        (self.destino / ".stockroomer_backup_id").write_text("otro_identificador", encoding="ascii")
        with self.assertRaisesMessage(CommandError, "Identificador incorrecto"):
            self.ejecutar()
        self.assertFalse((self.destino / self.backup.name).exists())

    def test_rechaza_base_local_corrupta(self):
        self.ejecutar("--pair")
        self.backup.write_bytes(b"NO ES SQLITE")
        with self.assertRaises(CommandError):
            self.ejecutar()
        self.assertFalse((self.destino / self.backup.name).exists())
