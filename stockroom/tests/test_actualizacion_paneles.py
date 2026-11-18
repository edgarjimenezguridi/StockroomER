"""Fase 23B: pruebas de la configuración de actualización visual."""
from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase

TEMPLATES = Path(settings.BASE_DIR) / "stockroom" / "templates" / "stockroom"
SCRIPT = Path(settings.BASE_DIR) / "stockroom" / "static" / "stockroom" / "js" / "panel_actualizacion.js"


class ActualizacionPanelesTests(SimpleTestCase):
    def test_panel_trabajador_actualiza_solicitudes_y_adeudos(self):
        html = (TEMPLATES / "empleados" / "panel_empleado.html").read_text(encoding="utf-8")
        for region in ("trabajador-resumen", "trabajador-solicitudes", "trabajador-adeudos"):
            self.assertIn(f'data-sr-live="{region}"', html)
        self.assertIn("panel_actualizacion.js", html)
        self.assertNotIn('data-sr-live="trabajador-carrito"', html)
        self.assertNotIn('data-sr-live="trabajador-catalogo"', html)

    def test_panel_almacen_usa_un_solo_actualizador(self):
        html = (TEMPLATES / "almacen" / "panel_almacen.html").read_text(encoding="utf-8")
        for region in ("almacen-resumen", "almacen-por-preparar", "almacen-por-confirmar"):
            self.assertIn(f'data-sr-live="{region}"', html)
        self.assertIn("panel_actualizacion.js", html)
        self.assertNotIn("setInterval(actualizarSolicitudes", html)

    def test_panel_jefe_actualiza_solo_consultas(self):
        html = (TEMPLATES / "jefe" / "panel_jefe.html").read_text(encoding="utf-8")
        for region in ("jefe-resumen", "jefe-alertas", "jefe-autorizaciones"):
            self.assertIn(f'data-sr-live="{region}"', html)
        self.assertIn("panel_actualizacion.js", html)
        self.assertNotIn('data-sr-live="jefe-formulario"', html)

    def test_actualizador_protege_sesion_y_formularios(self):
        js = SCRIPT.read_text(encoding="utf-8")
        for seguridad in ('credentials: "same-origin"', 'redirect: "manual"', 'cache: "no-store"',
                          'document.hidden', 'consultando', 'actual.contains(document.activeElement)',
                          'stockroom:panel-actualizado'):
            self.assertIn(seguridad, js)
