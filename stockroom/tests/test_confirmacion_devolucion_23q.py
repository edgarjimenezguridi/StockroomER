"""Fase 23Q: protección de la confirmación manual de devoluciones."""
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import get_template
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from stockroom.models import (
    Article, Employee, QuantityIssue, QuantityReturn, Tool,
)

PLANTILLA = (
    Path(settings.BASE_DIR) / "stockroom" / "templates" /
    "stockroom" / "almacen" / "registrar_devolucion_almacen.html"
)


class ConfirmacionDevolucionPlantilla23QTests(SimpleTestCase):
    def test_plantilla_compila(self):
        get_template("stockroom/almacen/registrar_devolucion_almacen.html")

    def test_doble_clic_no_envia_un_segundo_formulario(self):
        html = PLANTILLA.read_text(encoding="utf-8")
        for esperado in (
            'let enviandoDevolucion = false',
            'if (enviandoDevolucion)',
            'event.preventDefault()',
            'submitButton.disabled = true',
            'submitButton.setAttribute("aria-busy", "true")',
        ):
            with self.subTest(esperado=esperado):
                self.assertIn(esperado, html)

    def test_regresar_con_historial_restaurara_el_boton(self):
        html = PLANTILLA.read_text(encoding="utf-8")
        self.assertIn('window.addEventListener("pageshow"', html)
        self.assertIn('if (event.persisted)', html)
        self.assertIn('submitButton.disabled = false', html)
        self.assertIn('replacementCode.addEventListener("keydown"', html)
        self.assertIn('event.key === "Enter"', html)


class ConfirmacionDevolucionServidor23QTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_superuser(
            username="almacen_dev_23q", email="dev23q@example.com",
            password="PruebaSegura123!",
        )
        cls.empleado = Employee.objects.create(
            employee_id="EMP-23Q", first_name="Prueba", last_name="Devolucion",
            is_active=True,
        )
        cls.articulo = Article.objects.create(
            article_code="ART-23Q", name="Herramienta individual 23Q",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE, is_active=True,
        )
        cls.pieza = Tool.objects.create(
            article=cls.articulo, tool_code="PIEZA-23Q", name="Pieza 23Q",
            inventory_status=Tool.InventoryStatus.LOANED, is_active=True,
        )
        cls.entrega = QuantityIssue.objects.create(
            tool=cls.pieza, employee=cls.empleado, quantity=1,
            returned_quantity=0, requires_return=True,
        )

    def test_post_repetido_no_devuelve_dos_veces_la_pieza(self):
        self.client.force_login(self.usuario)
        url = reverse("registrar_devolucion_almacen", args=[self.entrega.pk])
        datos = {
            "operation": "return_only",
            "quantity": "1",
            "condition": QuantityReturn.Condition.GOOD,
            "reason": "",
            "notes": "",
            "replacement_tool": "",
            "replacement_code": "",
        }
        primero = self.client.post(url, datos)
        self.assertEqual(primero.status_code, 302)
        self.entrega.refresh_from_db()
        self.assertEqual(self.entrega.returned_quantity, 1)
        self.assertEqual(QuantityReturn.objects.filter(issue=self.entrega).count(), 1)

        segundo = self.client.post(url, datos)
        self.assertEqual(segundo.status_code, 302)
        self.entrega.refresh_from_db()
        self.assertEqual(self.entrega.returned_quantity, 1)
        self.assertEqual(QuantityReturn.objects.filter(issue=self.entrega).count(), 1)
