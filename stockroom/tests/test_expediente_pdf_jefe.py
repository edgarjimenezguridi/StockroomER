
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee


class ExpedientePDFJefeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_user(
            username="jefe_pdf_expediente",
            password="ClaveTemporal123!",
            is_staff=True,
        )
        cls.jefe.groups.add(
            Group.objects.get_or_create(name="Jefes")[0]
        )

        cls.almacenista = User.objects.create_user(
            username="almacen_pdf_expediente",
            password="ClaveTemporal123!",
            is_staff=True,
        )

        cls.empleado = Employee.objects.create(
            employee_id="PDF-EMP-001",
            first_name="Trabajador",
            last_name="Prueba",
            is_active=True,
        )

    def test_jefe_descarga_pdf(self):
        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse(
                "expediente_pdf_jefe",
                args=[self.empleado.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/pdf",
        )
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertIn(
            "attachment",
            response["Content-Disposition"],
        )
        self.assertIn(
            "no-store",
            response["Cache-Control"],
        )

    def test_almacenista_no_puede_descargar(self):
        self.client.force_login(self.almacenista)

        response = self.client.get(
            reverse(
                "expediente_pdf_jefe",
                args=[self.empleado.pk],
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_descarga_no_modifica_estado_empleado(self):
        self.client.force_login(self.jefe)

        self.client.get(
            reverse(
                "expediente_pdf_jefe",
                args=[self.empleado.pk],
            )
        )

        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.is_active)

    
    def test_pdf_permite_consultar_trabajador_inactivo(self):
        self.empleado.is_active = False
        self.empleado.save(update_fields=["is_active"])

        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse(
                "expediente_pdf_jefe",
                args=[self.empleado.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))

        self.empleado.refresh_from_db()
        self.assertFalse(self.empleado.is_active)

    def test_pdf_trabajador_inexistente(self):
        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse(
                "expediente_pdf_jefe",
                args=[999999999],
            )
        )

        self.assertEqual(response.status_code, 404)

