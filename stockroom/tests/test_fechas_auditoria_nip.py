
"""Fase 20U: fechas reales de eventos de recuperación de NIP."""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stockroom.models import (
    Employee,
    EmployeeCredential,
    PinResetAuthorization,
)


class FechasAuditoriaNipTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_superuser(
            username="jefe_fechas_nip_20u",
            password="ClaveTemporalSegura123!",
        )

        hoy = timezone.localdate()
        cls.hoy = hoy.isoformat()
        cls.fecha_antigua = (
            hoy - timedelta(days=10)
        ).isoformat()

        # Horarios definidos dentro de cada fecha local.
        cls.emision = timezone.make_aware(
            datetime.combine(
                hoy - timedelta(days=10),
                time(12, 0),
            ),
            timezone.get_current_timezone(),
        )

        cls.uso = timezone.make_aware(
            datetime.combine(hoy, time(10, 0)),
            timezone.get_current_timezone(),
        )

        cls.revocacion = timezone.make_aware(
            datetime.combine(hoy, time(11, 0)),
            timezone.get_current_timezone(),
        )

        empleado_uso = Employee.objects.create(
            employee_id="NIP20U001",
            first_name="Prueba",
            last_name="Uso",
        )

        empleado_revocacion = Employee.objects.create(
            employee_id="NIP20U002",
            first_name="Prueba",
            last_name="Revocacion",
        )

        credencial_uso, _ = (
            EmployeeCredential.objects.get_or_create(
                employee=empleado_uso
            )
        )

        credencial_revocacion, _ = (
            EmployeeCredential.objects.get_or_create(
                employee=empleado_revocacion
            )
        )

        # No almacenamos NIP ni códigos reales.
        autorizacion_uso = PinResetAuthorization.objects.create(
            credential=credencial_uso,
            issued_by=cls.jefe,
            code_digest="digest_ficticio_uso_20u",
            expires_at=cls.emision + timedelta(days=15),
        )

        autorizacion_revocacion = (
            PinResetAuthorization.objects.create(
                credential=credencial_revocacion,
                issued_by=cls.jefe,
                code_digest="digest_ficticio_revocacion_20u",
                expires_at=cls.emision + timedelta(days=15),
            )
        )

        # Actualizamos las fechas de prueba directamente
        # para evitar restricciones de auto_now_add.
        PinResetAuthorization.objects.filter(
            pk=autorizacion_uso.pk
        ).update(
            created_at=cls.emision,
            used_at=cls.uso,
        )

        PinResetAuthorization.objects.filter(
            pk=autorizacion_revocacion.pk
        ).update(
            created_at=cls.emision,
            revoked_at=cls.revocacion,
        )

    def setUp(self):
        self.client.force_login(self.jefe)
        self.url = reverse("auditoria_jefe")

    def consultar(self, fecha):
        return self.client.get(
            self.url,
            {
                "desde": fecha,
                "hasta": fecha,
                "categoria": "nip",
            },
        )

    def test_uso_aparece_en_fecha_real(self):
        response = self.consultar(self.hoy)

        self.assertEqual(response.status_code, 200)

        acciones = [
            evento["action"]
            for evento in response.context["eventos"]
        ]

        self.assertIn(
            "Recuperación de NIP completada",
            acciones,
        )

        self.assertNotIn(
            "Recuperación de NIP autorizada",
            acciones,
        )

    def test_revocacion_aparece_en_fecha_real(self):
        response = self.consultar(self.hoy)

        acciones = [
            evento["action"]
            for evento in response.context["eventos"]
        ]

        self.assertIn(
            "Autorización de recuperación revocada",
            acciones,
        )

    def test_fecha_antigua_muestra_solo_emisiones(self):
        response = self.consultar(self.fecha_antigua)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 2)

        acciones = [
            evento["action"]
            for evento in response.context["eventos"]
        ]

        self.assertEqual(
            acciones.count(
                "Recuperación de NIP autorizada"
            ),
            2,
        )

    def test_historial_no_muestra_digest(self):
        response = self.consultar(self.hoy)

        self.assertNotContains(
            response,
            "digest_ficticio_uso_20u",
        )

        self.assertNotContains(
            response,
            "digest_ficticio_revocacion_20u",
        )

    def test_eventos_ordenados_por_fecha(self):
        response = self.consultar(self.hoy)

        fechas = [
            evento["when"]
            for evento in response.context["eventos"]
        ]

        self.assertEqual(
            fechas,
            sorted(fechas, reverse=True),
        )
