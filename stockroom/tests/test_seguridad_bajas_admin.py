
from django.contrib import admin
from django.test import RequestFactory, SimpleTestCase

from stockroom.admin import EmployeeAdmin
from stockroom.models import Employee


class SeguridadBajasAdminTests(SimpleTestCase):

    def setUp(self):
        self.admin_empleados = EmployeeAdmin(
            Employee,
            admin.site,
        )
        self.request = RequestFactory().get("/admin/stockroom/employee/")

    def test_is_active_no_se_puede_editar_en_admin(self):
        campos = self.admin_empleados.get_readonly_fields(
            self.request,
        )
        self.assertIn("is_active", campos)

    def test_no_se_pueden_eliminar_trabajadores(self):
        self.assertFalse(
            self.admin_empleados.has_delete_permission(
                self.request,
            )
        )
