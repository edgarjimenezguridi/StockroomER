"""Fase 23C: consistencia de navegación y formularios sin alterar operaciones."""
from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR) / "stockroom" / "templates" / "stockroom"
CSS = Path(settings.BASE_DIR) / "stockroom" / "static" / "stockroom" / "css" / "empresa.css"

class DisenoUnificadoTests(SimpleTestCase):
    def test_estilos_corporativos_reutilizables(self):
        css = CSS.read_text(encoding="utf-8")
        for nombre in (".sr-nav", ".sr-btn", ".sr-btn-secondary", ".sr-section", ".sr-form", ".sr-table"):
            self.assertIn(nombre, css)

    def test_confirmacion_mantiene_post_y_version_de_preparacion(self):
        html = (BASE / "empleados/confirmar_recibido.html").read_text(encoding="utf-8")
        for fragmento in ('extends "stockroom/base.html"', 'method="post"', '{% csrf_token %}', 'name="preparation_version"', '{{ form.as_p }}', 'type="submit"'):
            self.assertIn(fragmento, html)
        self.assertIn('sr-btn sr-btn-secondary', html)

    def test_regresos_de_cada_rol_con_boton(self):
        rutas = {
            "empleados/solicitar_duplicado.html": "panel_empleado",
            "almacen/asignar_stock_inicial.html": "panel_almacen",
            "jefe/reportes.html": "panel_jefe",
            "jefe/auditoria.html": "panel_jefe",
            "jefe/consultas_operativas.html": "panel_jefe",
        }
        for archivo, ruta in rutas.items():
            with self.subTest(archivo=archivo):
                contenido = (BASE / archivo).read_text(encoding="utf-8")
                self.assertIn(f"{{% url '{ruta}' %}}", contenido)
                self.assertIn('sr-btn sr-btn-secondary', contenido)

    def test_operaciones_siguen_con_confirmacion_explicita(self):
        html = (BASE / "almacen/asignar_stock_inicial.html").read_text(encoding="utf-8")
        self.assertIn('method="post"', html)
        self.assertIn('{% csrf_token %}', html)
        self.assertIn('type="submit"', html)
