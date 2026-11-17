
"""Fase 20S: confidencialidad del historial administrativo."""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee


class ConfidencialidadAuditoriaJefeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_superuser(
            username="jefe_confidencialidad_20s",
            password="ClaveTemporalSegura123!",
        )

        tipo = ContentType.objects.get_for_model(Employee)

        LogEntry.objects.create(
            user=cls.jefe,
            content_type=tipo,
            object_id="1",
            object_repr="TRABAJADOR_PERMITIDO_20S",
            action_flag=CHANGE,
            change_message="Actualización de datos de trabajador",
        )

        LogEntry.objects.create(
            user=cls.jefe,
            content_type=tipo,
            object_id="2",
            object_repr="REGISTRO_CONFIDENCIAL_20S",
            action_flag=CHANGE,
            change_message=(
                "CAMPO_SENSIBLE_20S: "
                "VALOR_SECRETO_20S"
            ),
        )

    def setUp(self):
        self.client.force_login(self.jefe)

    def test_historial_muestra_solo_eventos_permitidos(self):
        response = self.client.get(
            reverse("auditoria_jefe")
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(
            response,
            "TRABAJADOR_PERMITIDO_20S",
        )

        self.assertNotContains(
            response,
            "REGISTRO_CONFIDENCIAL_20S",
        )

        self.assertNotContains(
            response,
            "VALOR_SECRETO_20S",
        )

    def test_busqueda_no_revela_eventos_confidenciales(self):
        response = self.client.get(
            reverse("auditoria_jefe"),
            {
                "q": "REGISTRO_CONFIDENCIAL_20S",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["total"],
            0,
        )

        self.assertNotContains(
            response,
            "VALOR_SECRETO_20S",
        )

    def test_historial_no_permite_modificaciones(self):
        cantidad_antes = LogEntry.objects.count()

        response = self.client.post(
            reverse("auditoria_jefe"),
            {"accion": "eliminar"},
        )

        self.assertEqual(response.status_code, 405)

        self.assertEqual(
            LogEntry.objects.count(),
            cantidad_antes,
        )
