from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee, EmployeeCredential
from stockroom.worker_session_security import SESSION_KEY, pin_session_version


class SeguridadSesionesNipTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            employee_id="SESSION-PIN-01", first_name="Prueba", last_name="Sesion"
        )
        self.credential = EmployeeCredential.objects.create(
            employee=self.employee, pin_hash=make_password("348129")
        )
        self.panel = reverse("panel_empleado")
        self.access = reverse("acceso_empleado")

    def autenticar(self):
        session = self.client.session
        session["worker_employee_id"] = self.employee.pk
        session["worker_credential_id"] = self.credential.pk
        session[SESSION_KEY] = pin_session_version(self.credential.pin_hash)
        session.save()

    def test_sesion_valida_mantiene_acceso(self):
        self.autenticar()
        self.assertEqual(self.client.get(self.panel).status_code, 200)

    def test_cambio_de_nip_revoca_sesion_previa(self):
        self.autenticar()
        self.credential.pin_hash = make_password("672940")
        self.credential.save(update_fields=["pin_hash"])
        self.assertRedirects(self.client.get(self.panel), self.access)
        self.assertNotIn("worker_employee_id", self.client.session)

    def test_sesion_anterior_sin_marca_se_revoca(self):
        session = self.client.session
        session["worker_employee_id"] = self.employee.pk
        session["worker_credential_id"] = self.credential.pk
        session.save()
        self.assertRedirects(self.client.get(self.panel), self.access)

    def test_baja_del_trabajador_revoca_sesion(self):
        self.autenticar()
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])
        self.assertRedirects(self.client.get(self.panel), self.access)

    def test_credencial_inactiva_revoca_sesion(self):
        self.autenticar()
        self.credential.is_active = False
        self.credential.save(update_fields=["is_active"])
        self.assertRedirects(self.client.get(self.panel), self.access)
