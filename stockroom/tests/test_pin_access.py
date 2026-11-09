from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from stockroom.credentials import verify_employee_pin
from stockroom.models import Employee, EmployeeCredential


class PinAccessTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            employee_id="TEST-PIN",
            first_name="Trabajador",
            last_name="De prueba",
        )
        self.credential = EmployeeCredential.objects.create(
            employee=self.employee,
            pin_hash=make_password("012345"),
        )

    def verificar(self, pin):
        return verify_employee_pin(
            barcode=self.credential.barcode,
            pin=pin,
        )

    def test_nip_correcto_reinicia_intentos(self):
        with self.assertRaises(ValidationError):
            self.verificar("999999")

        self.credential.refresh_from_db()
        self.assertEqual(self.credential.failed_pin_attempts, 1)

        employee = self.verificar("012345")

        self.credential.refresh_from_db()
        self.assertEqual(employee.pk, self.employee.pk)
        self.assertEqual(self.credential.failed_pin_attempts, 0)
        self.assertIsNone(self.credential.pin_locked_until)

    def test_cinco_fallos_bloquean_incluso_el_nip_correcto(self):
        for attempt in range(1, 6):
            with self.assertRaises(ValidationError):
                self.verificar("999999")

            self.credential.refresh_from_db()
            self.assertEqual(
                self.credential.failed_pin_attempts,
                attempt,
            )

        locked_until = self.credential.pin_locked_until
        self.assertIsNotNone(locked_until)
        self.assertGreater(locked_until, timezone.now())

        with self.assertRaisesMessage(
            ValidationError, "bloqueado temporalmente"
        ):
            self.verificar("012345")

        self.credential.refresh_from_db()
        self.assertEqual(self.credential.failed_pin_attempts, 5)
        self.assertEqual(
            self.credential.pin_locked_until,
            locked_until,
        )

    def test_bloqueo_vencido_permite_ingresar(self):
        EmployeeCredential.objects.filter(
            pk=self.credential.pk
        ).update(
            failed_pin_attempts=5,
            pin_locked_until=timezone.now() - timedelta(seconds=1),
        )

        employee = self.verificar("012345")

        self.credential.refresh_from_db()
        self.assertEqual(employee.pk, self.employee.pk)
        self.assertEqual(self.credential.failed_pin_attempts, 0)
        self.assertIsNone(self.credential.pin_locked_until)

    def test_trabajador_inactivo_no_puede_ingresar(self):
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])

        with self.assertRaisesMessage(ValidationError, "inactiva"):
            self.verificar("012345")