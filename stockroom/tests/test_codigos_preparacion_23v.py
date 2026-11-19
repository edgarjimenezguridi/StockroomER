"""Fase 23V: lectura inequívoca de códigos de piezas individuales."""
from pathlib import Path
from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR) / "stockroom"
HTML = BASE / "templates/stockroom/almacen/preparar_articulo_almacen.html"
JS = BASE / "static/stockroom/js/preparar_comanda_23o.js"
VIEWS = BASE / "warehouse_views.py"


class CodigosPreparacion23VTests(SimpleTestCase):
    def test_plantilla_compila_y_publica_mapa_seguro(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertTrue(html.lstrip().startswith('{% extends "stockroom/base.html" %}'))
        get_template("stockroom/almacen/preparar_articulo_almacen.html")
        self.assertIn('codigos_piezas|json_script:"codigos-piezas-preparacion"', html)
        self.assertIn("?v=23w1", html)

    def test_vista_entrega_solo_codigos_de_piezas_seleccionables(self):
        vista = VIEWS.read_text(encoding="utf-8")
        inicio = vista.index("def preparar_articulo_almacen(")
        fin = vista.index("@never_cache", inicio + 1)
        codigo = vista[inicio:fin]
        self.assertIn('if "tools" in form.fields:', codigo)
        self.assertIn('for pieza in form.fields["tools"].queryset', codigo)
        self.assertIn('str(pieza.pk): pieza.tool_code', codigo)
        self.assertIn('"codigos_piezas": codigos_piezas', codigo)

    def test_escaner_compara_codigo_exactamente_con_id(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn('JSON.parse(mapa.textContent)', js)
        self.assertIn('codigosPiezas[String(checkbox.value)]', js)
        self.assertIn('codigoDe(c) === codigo', js)
        self.assertNotIn('label.textContent', js)
        self.assertNotIn('CSS.escape', js)

    def test_escanear_solo_marca_y_no_registra_movimientos(self):
        js = JS.read_text(encoding="utf-8")
        self.assertIn('event.preventDefault()', js)
        self.assertIn('casilla.checked = true', js)
        self.assertIn('ya está seleccionada', js)
        self.assertNotIn('fetch(', js)
        self.assertNotIn('.submit(', js)
