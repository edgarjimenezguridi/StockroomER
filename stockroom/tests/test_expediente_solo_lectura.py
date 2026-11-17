
"""Verifica que consultar expedientes no altere la base de datos."""

import re

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from stockroom.models import Employee


class ExpedienteSoloLecturaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_user(
            username="jefe_integridad_19g",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )
        grupo, _ = Group.objects.get_or_create(name="Jefes")
        cls.jefe.groups.add(grupo)

        cls.empleado = Employee.objects.create(
            employee_id="INTEGRIDAD-19G",
            first_name="Trabajador",
            last_name="Integridad",
            is_active=True,
        )

    def setUp(self):
        self.client.force_login(self.jefe)

    def comprobar_sin_escrituras(self, consultas):
        patron = re.compile(
            r"^\s*(INSERT|UPDATE|DELETE|REPLACE|"
            r"ALTER|DROP|CREATE)\b",
            re.IGNORECASE,
        )

        escrituras = [
            consulta["sql"]
            for consulta in consultas
            if patron.match(consulta["sql"])
        ]

        self.assertEqual(
            escrituras,
            [],
            "La consulta del expediente ejecutó escrituras.",
        )

    def test_expediente_web_no_escribe_en_base_de_datos(self):
        url = reverse(
            "expediente_trabajador_jefe",
            args=[self.empleado.pk],
        )

        with CaptureQueriesContext(connection) as consultas:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.comprobar_sin_escrituras(consultas.captured_queries)

    def test_expediente_pdf_no_escribe_en_base_de_datos(self):
        url = reverse(
            "expediente_pdf_jefe",
            args=[self.empleado.pk],
        )

        with CaptureQueriesContext(connection) as consultas:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.comprobar_sin_escrituras(consultas.captured_queries)

    def test_pdf_rechaza_operaciones_post(self):
        url = reverse(
            "expediente_pdf_jefe",
            args=[self.empleado.pk],
        )

        response = self.client.post(
            url,
            {"accion": "modificar"},
        )

        self.assertEqual(response.status_code, 405)

    def test_consultas_conservan_estado_del_empleado(self):
        estado_original = self.empleado.is_active

        self.client.get(
            reverse(
                "expediente_trabajador_jefe",
                args=[self.empleado.pk],
            )
        )

        self.client.get(
            reverse(
                "expediente_pdf_jefe",
                args=[self.empleado.pk],
            )
        )

        self.empleado.refresh_from_db()
        self.assertEqual(
            self.empleado.is_active,
            estado_original,
        )
