
"""Comprueba el contenido real del expediente PDF."""

from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from pypdf import PdfReader

from stockroom.models import Employee


class ContenidoPDFExpedienteTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_user(
            username="jefe_contenido_pdf",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )

        cls.jefe.groups.add(
            Group.objects.get_or_create(name="Jefes")[0]
        )

        cls.empleado = Employee.objects.create(
            employee_id="PDF-CONTENIDO-001",
            first_name="Carlos",
            last_name="Prueba",
            is_active=True,
        )

    def test_pdf_contiene_informacion_principal(self):
        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse(
                "expediente_pdf_jefe",
                args=[self.empleado.pk],
            )
        )

        self.assertEqual(response.status_code, 200)

        lector = PdfReader(BytesIO(response.content))

        self.assertGreaterEqual(len(lector.pages), 1)

        texto = "\n".join(
            pagina.extract_text()
            for pagina in lector.pages
        )

        self.assertIn(
            "ENGRANES Y RECTIFICADOS",
            texto,
        )
        self.assertIn(
            "EXPEDIENTE INTEGRAL DEL TRABAJADOR",
            texto,
        )
        self.assertIn("Carlos", texto)
        self.assertIn("PDF-CONTENIDO-001", texto)
        self.assertIn("RESUMEN EJECUTIVO", texto)
        self.assertIn("Herramientas actualmente asignadas", texto)
        self.assertIn("Historial de devoluciones", texto)
        self.assertIn("Resoluciones de daños", texto)
        self.assertIn("Historial de solicitudes de baja", texto)

    def test_pdf_tiene_paginas_validas(self):
        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse(
                "expediente_pdf_jefe",
                args=[self.empleado.pk],
            )
        )

        lector = PdfReader(BytesIO(response.content))

        for pagina in lector.pages:
            self.assertGreater(
                float(pagina.mediabox.width),
                0,
            )
            self.assertGreater(
                float(pagina.mediabox.height),
                0,
            )
