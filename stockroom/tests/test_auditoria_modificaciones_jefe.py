
"""Fase 20N: auditoría de modificaciones de personal."""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee


class AuditoriaModificacionesJefeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_superuser(
            username="jefe_auditoria_20n",
            password="ClaveTemporalSegura123!",
        )

        cls.usuario = User.objects.create_user(
            username="usuario_auditoria_20n",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )

        tipo_empleado = ContentType.objects.get_for_model(
            Employee
        )

        cls.registro = LogEntry.objects.create(
            user=cls.jefe,
            content_type=tipo_empleado,
            object_id="1",
            object_repr="TRABAJADOR_PRUEBA_20N",
            action_flag=CHANGE,
            change_message="Actualización de datos de trabajador",
        )

    def test_modificacion_aparece_en_historial(self):
        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse("auditoria_jefe")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Datos de trabajador actualizados",
        )
        self.assertContains(
            response,
            "TRABAJADOR_PRUEBA_20N",
        )

    def test_filtro_modificaciones(self):
        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse("auditoria_jefe"),
            {"categoria": "datos"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["categoria"],
            "datos",
        )
        self.assertEqual(
            response.context["total"],
            1,
        )

    def test_busqueda_por_responsable(self):
        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse("auditoria_jefe"),
            {"q": "jefe_auditoria_20n"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "TRABAJADOR_PRUEBA_20N",
        )

        response = self.client.get(
            reverse("auditoria_jefe"),
            {"q": "responsable_inexistente_20n"},
        )

        self.assertEqual(
            response.context["total"],
            0,
        )

    def test_usuario_no_autorizado_no_consulta_historial(self):
        self.client.force_login(self.usuario)

        response = self.client.get(
            reverse("auditoria_jefe")
        )

        self.assertEqual(
            response.status_code,
            403,
        )
