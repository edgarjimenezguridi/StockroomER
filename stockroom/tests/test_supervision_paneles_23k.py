"""Fase 23K: regresión de refresco visual de paneles, sin inventario real."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR) / "stockroom"
JS = BASE / "static" / "stockroom" / "js" / "panel_actualizacion.js"
TEMPLATES = BASE / "templates" / "stockroom"


class SupervisionPaneles23KTests(SimpleTestCase):
    def test_paneles_contienen_las_regiones_de_consulta(self):
        casos = {
            "almacen/panel_almacen.html": ("almacen-resumen", "almacen-por-preparar", "almacen-por-confirmar"),
            "empleados/panel_empleado.html": ("trabajador-resumen", "trabajador-solicitudes", "trabajador-adeudos"),
            "jefe/panel_jefe.html": ("jefe-resumen", "jefe-alertas", "jefe-autorizaciones"),
        }
        for ruta, regiones in casos.items():
            with self.subTest(panel=ruta):
                html = (TEMPLATES / ruta).read_text(encoding="utf-8")
                self.assertIn("panel_actualizacion.js", html)
                for region in regiones:
                    self.assertIn('data-sr-live="' + region + '"', html)

    def test_actualizador_indica_ultima_comprobacion_y_estado_red(self):
        js = JS.read_text(encoding="utf-8")
        for texto in ("Actualizado ", "Sin conexión", "aria-live", "stockroom:panel-actualizado", "[data-sr-update-host]"):
            with self.subTest(texto=texto):
                self.assertIn(texto, js)

    def test_indicador_sin_boton_y_visible_en_almacen(self):
        js = JS.read_text(encoding="utf-8")
        almacen = (TEMPLATES / "almacen/panel_almacen.html").read_text(encoding="utf-8")
        self.assertNotIn("Actualizar ahora", js)
        self.assertNotIn('document.createElement("button")', js)
        self.assertIn('data-sr-update-host', almacen)
        self.assertIn('panel_actualizacion.js', almacen)
        self.assertIn('?v=23k1', almacen)

    def test_actualizador_conserva_sesion_formularios_y_no_hace_post(self):
        js = JS.read_text(encoding="utf-8")
        for texto in ('method: "GET"', 'credentials: "same-origin"', 'redirect: "manual"',
                      'cache: "no-store"', 'respuesta.redirected', 'document.hidden',
                      'actual.contains(activo)', 'const formularios = actual.querySelectorAll("form")',
                      'tieneCambiosPendientes(actual)', 'consultando'):
            with self.subTest(texto=texto):
                self.assertIn(texto, js)
        self.assertNotIn('method: "POST"', js)
        self.assertNotIn('actual.contains(document.activeElement)', js)

    def test_actualizador_no_acumula_solicitudes_y_limita_espera(self):
        js = JS.read_text(encoding="utf-8")
        for texto in ('const INTERVALO = 10000', 'const TIMEOUT = 8000', 'new AbortController()',
                      'controlador.abort()', 'window.clearTimeout(limite)',
                      'window.clearInterval(reloj)', 'if (!document.hidden) actualizar()'):
            with self.subTest(texto=texto):
                self.assertIn(texto, js)
