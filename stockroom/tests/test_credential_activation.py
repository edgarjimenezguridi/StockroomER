from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.test import TestCase

from stockroom.credentials import activate_pin, authorize_pin_setup
from stockroom.models import Employee, EmployeeCredential


class CredentialActivationTests(TestCase):
    def setUp(self):
        self.operator = get_user_model().objects.create_superuser(
            username="admin_prueba",
            password="solo-para-prueba",
        )
        self.credential = self.crear_credencial("TEST-001")

    def crear_credencial(self, numero):
        employee = Employee.objects.create(
            employee_id=numero,
            first_name="Trabajador",
            last_name="De prueba",
        )
        return EmployeeCredential.objects.create(employee=employee)

    def autorizar(self, credential):
        return authorize_pin_setup(
            credential=credential,
            operator=self.operator,
        )

    def test_la_autorizacion_solo_activa_una_vez(self):
        token = self.autorizar(self.credential)
        activate_pin(
            barcode=self.credential.barcode,
            authorization=token,
            pin="012345",
            pin_confirmation="012345",
        )

        # Reutilizar la autorización no debe sobrescribir el primer NIP.
        with self.assertRaisesMessage(ValidationError, "ya tiene un NIP"):
            activate_pin(
                barcode=self.credential.barcode,
                authorization=token,
                pin="654321",
                pin_confirmation="654321",
            )

        self.credential.refresh_from_db()
        self.assertTrue(check_password("012345", self.credential.pin_hash))
        self.assertNotEqual(self.credential.pin_hash, "012345")

    def test_dos_trabajadores_no_pueden_elegir_el_mismo_nip(self):
        otra = self.crear_credencial("TEST-002")

        activate_pin(
            barcode=self.credential.barcode,
            authorization=self.autorizar(self.credential),
            pin="012345",
            pin_confirmation="012345",
        )

        with self.assertRaisesMessage(ValidationError, "no está disponible"):
            activate_pin(
                barcode=otra.barcode,
                authorization=self.autorizar(otra),
                pin="012345",
                pin_confirmation="012345",
            )

        otra.refresh_from_db()
        self.assertEqual(otra.pin_hash, "")
        self.assertIsNone(otra.pin_fingerprint)

    def test_confirmacion_distinta_deja_la_credencial_sin_activar(self):
        with self.assertRaisesMessage(ValidationError, "deben coincidir"):
            activate_pin(
                barcode=self.credential.barcode,
                authorization=self.autorizar(self.credential),
                pin="012345",
                pin_confirmation="012346",
            )

        self.credential.refresh_from_db()
        self.assertEqual(self.credential.pin_hash, "")
        self.assertIsNone(self.credential.pin_fingerprint)