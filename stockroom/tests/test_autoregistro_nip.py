from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import signing
from django.test import TestCase
from django.urls import reverse

from stockroom.credentials import get_credential_for_setup
from stockroom.models import Employee, EmployeeCredential


class AutoRegistroNipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = Employee.objects.create(employee_id="AUTO-NIP-1", first_name="Prueba", last_name="Inicial")
        cls.credential = EmployeeCredential.objects.create(employee=cls.employee)
        cls.boss = get_user_model().objects.create_user(username="boss_autonip", password="Segura123456!", is_staff=True)
        cls.boss.groups.add(Group.objects.get_or_create(name="Jefes")[0])
        cls.other = get_user_model().objects.create_user(username="alm_autonip", password="Segura123456!", is_staff=True)

    def identify(self):
        return self.client.post(reverse("acceso_empleado"), {
            "access_method": "employee_id", "employee_id": self.employee.employee_id,
        })

    def token(self):
        self.client.force_login(self.boss)
        response = self.client.post(reverse("autorizar_nip_jefe", args=[self.employee.pk]))
        self.assertEqual(response.status_code, 200)
        return response.context["authorization"]

    def test_sin_nip_redirecciona_al_registro(self):
        response = self.identify()
        self.assertRedirects(response, reverse("inicio_nip_trabajador"))
        self.assertContains(self.client.get(reverse("inicio_nip_trabajador")), "Configurar mi NIP")

    def test_sin_identificacion_no_puede_activar(self):
        self.assertRedirects(self.client.get(reverse("inicio_nip_trabajador")), reverse("acceso_empleado"))
        self.assertEqual(self.client.get(reverse("activar_nip", args=[self.credential.barcode])).status_code, 403)

    def test_solo_jefe_emite_autorizaciones(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse("autorizar_nip_jefe", args=[self.employee.pk]))
        self.assertEqual(response.status_code, 403)
        token = self.token()
        self.assertEqual(get_credential_for_setup(barcode=self.credential.barcode, authorization=token).pk, self.credential.pk)

    def test_registro_autorizado_y_no_se_repite(self):
        token = self.token()
        self.client.logout()
        self.identify()
        response = self.client.post(reverse("inicio_nip_trabajador"), {"authorization": token})
        self.assertRedirects(response, reverse("activar_nip", args=[self.credential.barcode]))
        response = self.client.post(reverse("activar_nip", args=[self.credential.barcode]), {
            "pin": "684192", "pin_confirmation": "684192",
        })
        self.assertRedirects(response, reverse("acceso_empleado"))
        self.credential.refresh_from_db()
        self.assertTrue(self.credential.pin_hash)
        self.assertNotEqual(self.credential.pin_hash, "684192")
        self.assertEqual(self.client.get(reverse("activar_nip", args=[self.credential.barcode])).status_code, 403)

    def test_token_de_otro_trabajador_no_sirve(self):
        other_employee = Employee.objects.create(employee_id="AUTO-NIP-2", first_name="Otra", last_name="Persona")
        other_cred = EmployeeCredential.objects.create(employee=other_employee)
        token = self.token()
        self.client.logout()
        self.client.post(reverse("acceso_empleado"), {"access_method": "employee_id", "employee_id": other_employee.employee_id})
        response = self.client.post(reverse("inicio_nip_trabajador"), {"authorization": token})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(other_cred.pin_hash)

    def test_credencial_inactiva_no_puede_registrarse(self):
        self.credential.is_active = False
        self.credential.save(update_fields=["is_active"])
        response = self.identify()
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("pin_setup_pending", self.client.session)
