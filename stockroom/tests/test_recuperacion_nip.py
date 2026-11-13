from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stockroom.models import Employee, EmployeeCredential, PinResetAuthorization
from stockroom.pin_reset_views import create_pin_reset, reset_employee_pin


class RecuperacionNipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.employee = Employee.objects.create(employee_id='RST-001', first_name='Prueba', last_name='Recuperacion')
        cls.credential = EmployeeCredential.objects.create(
            employee=cls.employee, pin_hash=make_password('348129'),
        )
        cls.boss = get_user_model().objects.create_user(username='boss_reset', password='Segura123456!', is_staff=True)
        cls.boss.groups.add(Group.objects.get_or_create(name='Jefes')[0])
        cls.other = get_user_model().objects.create_user(username='warehouse_reset', password='Segura123456!', is_staff=True)

    def test_solo_jefe_puede_emitir_codigo(self):
        with self.assertRaises(PermissionDenied):
            create_pin_reset(credential=self.credential, operator=self.other)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(reverse('autorizar_reset_nip_jefe', args=[self.employee.pk])).status_code, 403)
        self.assertEqual(PinResetAuthorization.objects.count(), 0)

    def test_codigo_un_solo_uso_y_nip_nuevo(self):
        code = create_pin_reset(credential=self.credential, operator=self.boss)
        self.assertEqual(len(code), 10)
        self.assertNotEqual(PinResetAuthorization.objects.get().code_digest, code)
        reset_employee_pin(credential_id=self.credential.pk, code=code, new_pin='672940')
        self.credential.refresh_from_db()
        self.assertTrue(check_password('672940', self.credential.pin_hash))
        self.assertFalse(check_password('348129', self.credential.pin_hash))
        self.assertIsNotNone(PinResetAuthorization.objects.get().used_at)
        with self.assertRaises(ValidationError):
            reset_employee_pin(credential_id=self.credential.pk, code=code, new_pin='564320')

    def test_codigo_de_otro_trabajador_no_funciona(self):
        second = Employee.objects.create(employee_id='RST-002', first_name='Otra', last_name='Persona')
        second_cred = EmployeeCredential.objects.create(employee=second, pin_hash=make_password('238419'))
        code = create_pin_reset(credential=self.credential, operator=self.boss)
        with self.assertRaises(ValidationError):
            reset_employee_pin(credential_id=second_cred.pk, code=code, new_pin='672940')
        second_cred.refresh_from_db()
        self.assertTrue(check_password('238419', second_cred.pin_hash))

    def test_codigo_expirado_no_funciona(self):
        code = create_pin_reset(credential=self.credential, operator=self.boss)
        PinResetAuthorization.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        with self.assertRaises(ValidationError):
            reset_employee_pin(credential_id=self.credential.pk, code=code, new_pin='672940')

    def test_cinco_intentos_invalidan_codigo(self):
        code = create_pin_reset(credential=self.credential, operator=self.boss)
        wrong = '9999999999' if code != '9999999999' else '8888888888'
        for _ in range(5):
            with self.assertRaises(ValidationError):
                reset_employee_pin(credential_id=self.credential.pk, code=wrong, new_pin='672940')
        self.assertEqual(PinResetAuthorization.objects.get().attempts, 5)
        with self.assertRaises(ValidationError):
            reset_employee_pin(credential_id=self.credential.pk, code=code, new_pin='672940')

    def test_codigo_nuevo_revoca_anterior(self):
        first = create_pin_reset(credential=self.credential, operator=self.boss)
        second = create_pin_reset(credential=self.credential, operator=self.boss)
        self.assertIsNotNone(PinResetAuthorization.objects.order_by('pk').first().revoked_at)
        with self.assertRaises(ValidationError):
            reset_employee_pin(credential_id=self.credential.pk, code=first, new_pin='672940')
        reset_employee_pin(credential_id=self.credential.pk, code=second, new_pin='672940')

    def test_trabajador_sin_identificar_no_puede_recuperar(self):
        self.assertRedirects(self.client.get(reverse('recuperar_nip_trabajador')), reverse('acceso_empleado'))

    def test_flujo_web_identificacion_y_restablecimiento(self):
        code = create_pin_reset(credential=self.credential, operator=self.boss)
        self.client.post(reverse('acceso_empleado'), {
            'access_method': 'employee_id', 'employee_id': self.employee.employee_id,
        })
        self.assertContains(self.client.get(reverse('recuperar_nip_trabajador')), 'Restablecer mi NIP')
        response = self.client.post(reverse('recuperar_nip_trabajador'), {
            'code': code, 'pin': '672940', 'pin_confirmation': '672940',
        })
        self.assertRedirects(response, reverse('acceso_empleado'))
        self.assertTrue(check_password('672940', EmployeeCredential.objects.get(pk=self.credential.pk).pin_hash))

    def test_cuenta_inactiva_no_recupera(self):
        code = create_pin_reset(credential=self.credential, operator=self.boss)
        self.employee.is_active = False
        self.employee.save(update_fields=['is_active'])
        with self.assertRaises(Exception):
            reset_employee_pin(credential_id=self.credential.pk, code=code, new_pin='672940')
