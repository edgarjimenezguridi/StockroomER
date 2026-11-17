
"""Fase 20Q: filtro de auditoría por responsable."""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee


class FiltroResponsableAuditoriaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_superuser(
            username="jefe_auditor_20q",
            password="ClaveTemporalSegura123!",
        )

        cls.otro = User.objects.create_user(
            username="otro_responsable_20q",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )

        tipo = ContentType.objects.get_for_model(Employee)

        for usuario, identificador in (
            (cls.jefe, "REGISTRO_JEFE_20Q"),
            (cls.otro, "REGISTRO_OTRO_20Q"),
        ):
            LogEntry.objects.create(
                user=usuario,
                content_type=tipo,
                object_id="1",
                object_repr=identificador,
                action_flag=CHANGE,
                change_message=(
                    "Actualización de datos de trabajador"
                ),
            )

    def setUp(self):
        self.client.force_login(self.jefe)

    def test_filtrar_por_responsable(self):
        response = self.client.get(
            reverse("auditoria_jefe"),
            {
                "categoria": "datos",
                "responsable": "jefe_auditor_20q",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 1)
        self.assertContains(response, "REGISTRO_JEFE_20Q")
        self.assertNotContains(response, "REGISTRO_OTRO_20Q")

    def test_responsable_inexistente_no_muestra_eventos(self):
        response = self.client.get(
            reverse("auditoria_jefe"),
            {
                "responsable": "usuario_inexistente_20q",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 0)
