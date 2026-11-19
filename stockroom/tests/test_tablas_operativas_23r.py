"""Fase 23R: unificación visual sin cambiar operaciones del almacén."""
from pathlib import Path
from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase

ROOT = Path(settings.BASE_DIR) / "stockroom"
BASE = ROOT / "templates" / "stockroom" / "almacen"
STYLES = ROOT / "static" / "stockroom" / "css" / "tablas_operativas_23r.css"

class TablasOperativas23RTests(SimpleTestCase):
    def test_las_tres_plantillas_compilan(self):
        for name in ("adeudos_almacen.html", "historial_almacen.html", "reabastecimiento_almacen.html"):
            with self.subTest(plantilla=name):
                get_template("stockroom/almacen/" + name)

    def test_plantillas_comparten_hoja_de_estilos(self):
        for name in ("adeudos_almacen.html", "historial_almacen.html", "reabastecimiento_almacen.html"):
            with self.subTest(plantilla=name):
                html = (BASE / name).read_text(encoding="utf-8")
                self.assertTrue(html.lstrip().startswith('{% extends "stockroom/base.html" %}'))
                self.assertIn("tablas_operativas_23r.css", html)
                self.assertIn("{% load static %}", html)

    def test_estilos_especificos_y_desplazamiento_horizontal(self):
        css = STYLES.read_text(encoding="utf-8")
        for marker in (".pagina-adeudos", ".pagina-historial", ".pagina-reabastecimiento", "overflow-x: auto", "thead th", "tbody td", "focus-visible"):
            with self.subTest(marker=marker):
                self.assertIn(marker, css)
        self.assertNotIn("form.submit()", css)

    def test_conserva_operaciones_y_filtros(self):
        adeudos = (BASE / "adeudos_almacen.html").read_text(encoding="utf-8")
        historial = (BASE / "historial_almacen.html").read_text(encoding="utf-8")
        reabastecimiento = (BASE / "reabastecimiento_almacen.html").read_text(encoding="utf-8")
        self.assertIn("Buscar devolución", adeudos)
        self.assertIn('id="resultados-historial"', historial)
        self.assertIn('tabla-reabastecimiento', reabastecimiento)
