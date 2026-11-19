"""Fase 23U: mejoras de interacción no destructivas al preparar piezas."""
from pathlib import Path
from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR) / "stockroom"
HTML = BASE / "templates/stockroom/almacen/preparar_articulo_almacen.html"
JS = BASE / "static/stockroom/js/preparar_comanda_23o.js"


class PreparacionAsistida23UTests(SimpleTestCase):
    def test_plantilla_compila_y_extiende_primero(self):
        codigo = HTML.read_text(encoding="utf-8")
        self.assertTrue(codigo.lstrip().startswith('{% extends "stockroom/base.html" %}'))
        get_template("stockroom/almacen/preparar_articulo_almacen.html")

    def test_controles_solo_aparecen_para_piezas_individuales(self):
        codigo = HTML.read_text(encoding="utf-8")
        seccion = codigo.split('{% if form.tools %}', 1)[1].split('{% endif %}', 1)[0]
        for elemento in ('codigo-pieza-preparacion', 'limpiar-seleccion-preparacion', 'coincidencia-preparacion'):
            self.assertIn(elemento, seccion)
        self.assertIn('type="button" id="limpiar-seleccion-preparacion"', seccion)
        self.assertIn('{{ form.tools }}', seccion)

    def test_limpiar_no_envia_solicitudes_ni_toca_inventario(self):
        codigo = JS.read_text(encoding="utf-8")
        self.assertIn('limpiar.addEventListener("click"', codigo)
        self.assertIn('c.checked = false', codigo)
        self.assertIn('campo.focus()', codigo)
        self.assertIn('event.preventDefault()', codigo)
        self.assertNotIn('fetch(', codigo)
        self.assertNotIn('.submit(', codigo)

    def test_contador_advierte_sin_guardar_automaticamente(self):
        codigo = JS.read_text(encoding="utf-8")
        self.assertIn('seleccionadas === solicitadas', codigo)
        self.assertIn('coincidencia.dataset.estado', codigo)
        self.assertIn('La cantidad a preparar debe coincidir', codigo)
        self.assertIn('if (document.activeElement === document.body)', codigo)
