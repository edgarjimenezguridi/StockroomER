
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from stockroom.boss_personnel_views import estado_trabajador_jefe
from stockroom.models import Employee


class BloqueoBajaDirectaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_user(
            username="jefe_bloqueo_prueba",
            password="ClaveTemporal123!",
            is_staff=True,
        )
        grupo, _ = Group.objects.get_or_create(name="Jefes")
        cls.jefe.groups.add(grupo)

        cls.empleado = Employee.objects.create(
            employee_id="TEST-SEG-BAJA",
            first_name="Empleado",
            last_name="Prueba",
            is_active=True,
        )

    def test_jefe_no_puede_desactivar_por_ruta_antigua(self):
        request = RequestFactory().post(
            "/jefe/personal/estado/",
            {"accion": "desactivar"},
        )
        request.user = self.jefe

        with self.assertRaises(PermissionDenied):
            estado_trabajador_jefe(
                request,
                employee_id=self.empleado.pk,
            )

        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.is_active)
