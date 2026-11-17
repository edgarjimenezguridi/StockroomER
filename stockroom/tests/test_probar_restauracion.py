"""Pruebas de restauración sin acceso a la base real del almacén."""

import io
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings


class ProbarRestauracionTests(SimpleTestCase):
    def setUp(self):
        self.temporal = TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        self.base = Path(self.temporal.name)
        self.respaldos = self.base / "backups"
        self.respaldos.mkdir()
        self.archivo = self.respaldos / "stockroom_20261117_120000_000001.sqlite3"
        with closing(sqlite3.connect(str(self.archivo))) as db:
            db.execute("CREATE TABLE articulos (codigo TEXT PRIMARY KEY, cantidad INTEGER)")
            db.execute("INSERT INTO articulos VALUES ('A1', 25)")
            db.commit()

    def test_restaura_copia_y_conserva_registros(self):
        salida = io.StringIO()
        with override_settings(BASE_DIR=self.base):
            call_command("probar_restauracion", stdout=salida)
        self.assertIn("RESTAURACION DE PRUEBA CORRECTA", salida.getvalue())
        with closing(sqlite3.connect(str(self.archivo))) as db:
            self.assertEqual(db.execute("SELECT cantidad FROM articulos").fetchone()[0], 25)

    def test_rechaza_respaldo_corrupto(self):
        self.archivo.write_bytes(b"No es una base de datos SQLite")
        with override_settings(BASE_DIR=self.base):
            with self.assertRaises(CommandError):
                call_command("probar_restauracion")

    def test_rechaza_carpeta_sin_respaldos(self):
        self.archivo.unlink()
        with override_settings(BASE_DIR=self.base):
            with self.assertRaisesMessage(CommandError, "No se encontraron respaldos"):
                call_command("probar_restauracion")
