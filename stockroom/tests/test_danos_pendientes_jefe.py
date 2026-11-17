
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse


class DanosPendientesJefeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_user(
            username="jefe_danos_20e",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )
        cls.jefe.groups.add(
            Group.objects.get_or_create(name="Jefes")[0]
        )

        cls.almacenista = User.objects.create_user(
            username="almacen_danos_20e",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )

    def test_jefe_puede_consultar_danos(self):
        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse("danos_pendientes_jefe")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["total_pendientes"],
            0,
        )

    def test_almacenista_no_puede_consultar(self):
        self.client.force_login(self.almacenista)

        response = self.client.get(
            reverse("danos_pendientes_jefe")
        )

        self.assertEqual(response.status_code, 403)

    def test_no_permite_registrar_movimientos(self):
        self.client.force_login(self.jefe)

        response = self.client.post(
            reverse("danos_pendientes_jefe"),
            {"quantity": 1},
        )

        self.assertEqual(response.status_code, 405)
