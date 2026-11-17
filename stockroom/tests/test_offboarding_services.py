
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from stockroom.models import Employee, EmployeeOffboardingRequest
from stockroom.offboarding_services import aprobar_baja_trabajador


class SeguridadServicioBajasTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_user(
            username="jefe_prueba_servicio",
            password="PruebaTemporal123!",
            is_staff=True,
        )

        grupo, _ = Group.objects.get_or_create(name="Jefes")
        cls.jefe.groups.add(grupo)

        cls.almacenista = User.objects.create_user(
            username="almacenista_prueba_servicio",
            password="PruebaTemporal123!",
            is_staff=True,
        )

    def setUp(self):
        self.empleado = Employee.objects.create(
            employee_id="TEST-BAJA-001",
            first_name="Trabajador",
            last_name="Prueba",
            is_active=True,
        )

        self.solicitud = EmployeeOffboardingRequest.objects.create(
            employee=self.empleado,
            requested_by=self.almacenista,
        )

    def test_almacenista_no_puede_aprobar(self):
        with self.assertRaises(PermissionDenied):
            aprobar_baja_trabajador(
                solicitud_id=self.solicitud.pk,
                autorizado_por=self.almacenista,
            )

        self.empleado.refresh_from_db()
        self.solicitud.refresh_from_db()

        self.assertTrue(self.empleado.is_active)
        self.assertEqual(
            self.solicitud.status,
            EmployeeOffboardingRequest.Status.PENDING,
        )

    def test_jefe_puede_aprobar_sin_adeudos(self):
        aprobar_baja_trabajador(
            solicitud_id=self.solicitud.pk,
            autorizado_por=self.jefe,
        )

        self.empleado.refresh_from_db()
        self.solicitud.refresh_from_db()

        self.assertFalse(self.empleado.is_active)
        self.assertEqual(
            self.solicitud.status,
            EmployeeOffboardingRequest.Status.APPROVED,
        )
        self.assertEqual(self.solicitud.decided_by, self.jefe)
        self.assertIsNotNone(self.solicitud.decided_at)

    def test_no_se_puede_aprobar_dos_veces(self):
        aprobar_baja_trabajador(
            solicitud_id=self.solicitud.pk,
            autorizado_por=self.jefe,
        )

        with self.assertRaises(ValidationError):
            aprobar_baja_trabajador(
                solicitud_id=self.solicitud.pk,
                autorizado_por=self.jefe,
            )
