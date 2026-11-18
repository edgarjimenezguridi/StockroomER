"""Pruebas estáticas y de compilación para la pantalla segura de preparación."""
from pathlib import Path
from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR) / "stockroom"
HTML = BASE / "templates/stockroom/almacen/preparar_articulo_almacen.html"
JS = BASE / "static/stockroom/js/preparar_comanda_23o.js"

class PreparacionEscaneo23OTests(SimpleTestCase):
    def test_plantilla_compila_y_extends_es_primera_etiqueta(self):
        codigo = HTML.read_text(encoding="utf-8")
        self.assertTrue(codigo.lstrip().startswith('{% extends "stockroom/base.html" %}'))
        get_template("stockroom/almacen/preparar_articulo_almacen.html")

    def test_informacion_ubicacion_y_escaneo_solo_individual(self):
        codigo = HTML.read_text(encoding="utf-8")
        self.assertIn("linea.article.location", codigo)
        self.assertIn("{% if form.tools %}", codigo)
        self.assertIn("codigo-pieza-preparacion", codigo)
        self.assertIn("{{ form.tools }}", codigo)
        self.assertIn("{{ form.quantity }}", codigo)

    def test_escaneo_no_envia_formularios_ni_realiza_peticion(self):
        codigo = JS.read_text(encoding="utf-8")
        self.assertIn('event.preventDefault()', codigo)
        self.assertIn('casilla.checked = true', codigo)
        self.assertNotIn('.submit(', codigo)
        self.assertNotIn('fetch(', codigo)

    def test_escaneo_maneja_repetidos_y_contador(self):
        codigo = JS.read_text(encoding="utf-8")
        self.assertIn('casilla.checked', codigo)
        self.assertIn('ya está seleccionada', codigo)
        self.assertIn('Piezas seleccionadas:', codigo)
