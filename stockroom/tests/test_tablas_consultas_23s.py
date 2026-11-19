"""Fase 23S: verificación estática y compilación de consultas del almacén."""
from pathlib import Path
from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR) / "stockroom"
VISTAS = (
    "consultar_piezas_individuales_almacen.html",
    "stock_asignado.html",
    "detalle_solicitud_almacen.html",
)


class TablasConsultas23STests(SimpleTestCase):
    def test_tres_plantillas_compilan(self):
        for filename in VISTAS:
            with self.subTest(plantilla=filename):
                get_template(f"stockroom/almacen/{filename}")

    def test_extends_es_primera_etiqueta(self):
        for filename in VISTAS:
            with self.subTest(plantilla=filename):
                html = (BASE / "templates/stockroom/almacen" / filename).read_text(encoding="utf-8")
                self.assertTrue(html.lstrip().startswith('{% extends "stockroom/base.html" %}'))

    def test_tres_pantallas_cargan_estilo_compartido(self):
        for filename in VISTAS:
            with self.subTest(plantilla=filename):
                html = (BASE / "templates/stockroom/almacen" / filename).read_text(encoding="utf-8")
                self.assertIn("tablas_consultas_23s.css", html)
                self.assertIn("{% load static %}", html)

    def test_estilo_aislado_y_sin_movimientos(self):
        css = (BASE / "static/stockroom/css/tablas_consultas_23s.css").read_text(encoding="utf-8")
        for selector in (".pagina-consultar-piezas .tabla-piezas", ".pagina-stock-asignado .tabla-resguardo", ".pagina-detalle-solicitud .tabla-solicitud"):
            self.assertIn(selector, css)
        self.assertNotIn("@import", css)
        self.assertNotIn("url(", css)
