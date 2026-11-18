"""Regresión 23G: las pantallas de captura del almacén deben compilar.

No usa la base de datos ni registra movimientos de inventario.
"""
from pathlib import Path

from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase


PLANTILLAS = (
    "stockroom/almacen/corregir_existencia_almacen.html",
    "stockroom/almacen/registrar_entrada_almacen.html",
    "stockroom/almacen/asignar_stock_inicial.html",
)


class PlantillasAlmacen23GTests(SimpleTestCase):
    def test_plantillas_de_captura_compilan(self):
        for plantilla in PLANTILLAS:
            with self.subTest(plantilla=plantilla):
                self.assertIsNotNone(get_template(plantilla))

    def test_plantilla_corregir_existencias_extiende_primero(self):
        ruta = (
            Path(settings.BASE_DIR)
            / "stockroom"
            / "templates"
            / "stockroom"
            / "almacen"
            / "corregir_existencia_almacen.html"
        )
        contenido = ruta.read_text(encoding="utf-8-sig")
        self.assertTrue(
            contenido.lstrip().startswith('{% extends "stockroom/base.html" %}'),
            "La primera etiqueta de corregir existencias debe ser extends.",
        )

    def test_script_de_busqueda_escaneo_existe(self):
        ruta = (
            Path(settings.BASE_DIR)
            / "stockroom"
            / "static"
            / "stockroom"
            / "js"
            / "busqueda_escaneo.js"
        )
        self.assertTrue(ruta.is_file(), "Falta el JS de búsqueda y escaneo.")
