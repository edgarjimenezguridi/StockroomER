"""Fase 23F: la presentación no cambia la lógica de almacén."""
from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase

PANEL = Path(settings.BASE_DIR) / "stockroom/templates/stockroom/almacen/panel_almacen.html"
CSS = Path(settings.BASE_DIR) / "stockroom/static/stockroom/css/almacen_tablas.css"


class TablasAlmacen23FTests(SimpleTestCase):
    def test_tres_tablas_comparten_estilo(self):
        texto = PANEL.read_text(encoding="utf-8")
        self.assertEqual(texto.count('class="almacen-tabla"'), 3)
        self.assertIn('id="tabla-existencias" class="almacen-tabla"', texto)
        self.assertIn("stockroom/css/almacen_tablas.css", texto)

    def test_ver_solicitud_usa_boton_en_ambas_listas(self):
        texto = PANEL.read_text(encoding="utf-8")
        self.assertEqual(texto.count('class="almacen-boton-tabla"'), 2)
        self.assertEqual(texto.count("{% url 'detalle_solicitud_almacen' solicitud.pk %}"), 2)
        self.assertIn('aria-label="Ver solicitud número {{ solicitud.pk }}"', texto)

    def test_estilos_legibles_y_con_foco(self):
        css = CSS.read_text(encoding="utf-8")
        for selector in (".almacen-tabla", ".almacen-boton-tabla", ":focus-visible", "overflow-x: auto"):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)

    def test_se_conservan_refresco_y_filtros(self):
        texto = PANEL.read_text(encoding="utf-8")
        for fragmento in ('data-sr-live="almacen-por-preparar"',
                          'data-sr-live="almacen-por-confirmar"',
                          'id="buscar-existencias"', 'id="filtro-categoria"',
                          'id="filtro-control"'):
            with self.subTest(fragmento=fragmento):
                self.assertIn(fragmento, texto)
