"""Fase 23P: escaneo de devoluciones sin movimientos automáticos."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.template.loader import get_template
from django.urls import reverse

from stockroom.models import Article, Employee, QuantityIssue, QuantityReturn, Tool

PLANTILLAS = Path(settings.BASE_DIR) / 'stockroom' / 'templates' / 'stockroom' / 'almacen'


class DevolucionEscanerPlantillas23PTests(SimpleTestCase):
    def test_plantillas_compilan(self):
        for nombre in ('adeudos_almacen.html', 'registrar_devolucion_almacen.html'):
            with self.subTest(plantilla=nombre):
                get_template(f'stockroom/almacen/{nombre}')

    def test_limpiar_escaneo_no_envia_formulario(self):
        html = (PLANTILLAS / 'adeudos_almacen.html').read_text(encoding='utf-8')
        self.assertIn('id="limpiar-escaneo-pieza"', html)
        self.assertIn('type="button"', html)
        self.assertIn('scanInput.focus()', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('name="scan"', html)

    def test_devolucion_exige_guardado_manual(self):
        html = (PLANTILLAS / 'registrar_devolucion_almacen.html').read_text(encoding='utf-8')
        self.assertIn('entrega.employee.employee_id', html)
        self.assertIn('entrega.issued_at', html)
        self.assertIn('entrega.pending_quantity', html)
        self.assertIn('id="submit-return"', html)
        self.assertIn('Escanear solo localiza la entrega', html)


class DevolucionEscanerFlujo23PTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser(
            username='almacen_scan_23p', email='scan23p@example.com', password='Test1234!'
        )
        cls.trabajador = Employee.objects.create(
            employee_id='EMP-23P', first_name='Trabajador', last_name='Escaner', is_active=True
        )
        cls.articulo = Article.objects.create(
            article_code='ART-23P', name='Vernier de prueba',
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE, is_active=True,
        )
        cls.pieza = Tool.objects.create(
            article=cls.articulo, tool_code='PIEZA-23P', name='Vernier',
            inventory_status=Tool.InventoryStatus.LOANED, is_active=True,
        )
        cls.entrega = QuantityIssue.objects.create(
            tool=cls.pieza, employee=cls.trabajador, quantity=1,
            returned_quantity=0, requires_return=True,
        )

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_escaneo_con_espacios_y_minusculas_localiza_entrega(self):
        respuesta = self.client.get(reverse('adeudos_almacen'), {'scan': '  pieza-23p  '})
        self.assertRedirects(
            respuesta,
            reverse('registrar_devolucion_almacen', args=[self.entrega.pk]),
        )
        self.assertEqual(QuantityReturn.objects.count(), 0)
        self.entrega.refresh_from_db()
        self.assertEqual(self.entrega.returned_quantity, 0)

    def test_escaneo_de_codigo_de_articulo_no_se_confunde_con_pieza(self):
        respuesta = self.client.get(reverse('adeudos_almacen'), {'scan': 'ART-23P'})
        self.assertRedirects(respuesta, reverse('adeudos_almacen'))
        self.assertEqual(QuantityReturn.objects.count(), 0)

    def test_abrir_formulario_despues_de_escanear_no_devuelve_pieza(self):
        respuesta = self.client.get(reverse('registrar_devolucion_almacen', args=[self.entrega.pk]))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'EMP-23P')
        self.assertContains(respuesta, 'PIEZA-23P')
        self.assertEqual(QuantityReturn.objects.count(), 0)
        self.pieza.refresh_from_db()
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.LOANED)
