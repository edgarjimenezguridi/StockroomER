"""Fase 23W: revisión de coincidencia antes de guardar preparación."""
from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase
from django.template.loader import get_template

BASE = Path(settings.BASE_DIR) / "stockroom"
JS = BASE / "static/stockroom/js/preparar_comanda_23o.js"
HTML = BASE / "templates/stockroom/almacen/preparar_articulo_almacen.html"

class ValidacionPreparacion23WTests(SimpleTestCase):
    def test_plantilla_compila_y_actualiza_version_de_script(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertTrue(html.lstrip().startswith('{% extends "stockroom/base.html" %}'))
        get_template("stockroom/almacen/preparar_articulo_almacen.html")
        self.assertIn("?v=23w1", html)

    def test_no_envia_preparacion_incompleta(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn('formulario.addEventListener("submit", event => {', js)
        self.assertIn('event.preventDefault()', js)
        self.assertIn('seleccionadas === solicitadas', js)
        self.assertIn('cantidad.value.trim() !== ""', js)
        self.assertIn('Number.isInteger(solicitadas)', js)
        self.assertNotIn('fetch(', js)
        self.assertNotIn('.submit(', js)

    def test_permite_preparar_cero_piezas_sin_seleccion(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn('solicitadas >= 0', js)
        self.assertIn('solicitadas === 0', js)
        self.assertIn('Prepararás 0 piezas.', js)

    def test_doble_envio_y_volver_atras(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn('guardar.disabled = true', js)
        self.assertIn('window.addEventListener("pageshow"', js)
        self.assertIn('guardar.disabled = false', js)
        self.assertIn('guardar.textContent = "Guardar preparación"', js)
