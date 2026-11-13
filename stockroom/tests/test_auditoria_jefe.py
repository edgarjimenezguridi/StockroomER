from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.urls import reverse

from stockroom.boss_audit_views import audit_entries
from stockroom.models import Employee, EmployeeCredential, PinResetAuthorization
from stockroom.pin_reset_views import create_pin_reset, reset_employee_pin


class AuditoriaJefeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.boss = User.objects.create_user(username='jefe_audit', password='ClaveTemporalSegura!123', is_staff=True)
        cls.boss.groups.add(Group.objects.get_or_create(name='Jefes')[0])
        cls.staff = User.objects.create_user(username='otro_audit', password='ClaveTemporalSegura!123', is_staff=True)
        cls.employee = Employee.objects.create(employee_id='AUD-001', first_name='Laura', last_name='Auditada')
        cls.credential = EmployeeCredential.objects.create(employee=cls.employee, pin_hash=make_password('348129'))

    def test_almacenista_no_accede(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('auditoria_jefe')).status_code, 403)

    def test_jefe_consulta_movimientos_de_personal(self):
        self.client.force_login(self.boss)
        self.client.post(reverse('estado_trabajador_jefe', args=[self.employee.pk]), {'accion': 'desactivar'})
        response = self.client.get(reverse('auditoria_jefe'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Baja de trabajador')
        self.assertContains(response, 'AUD-001')

    def test_filtro_excluye_tipo_no_solicitado(self):
        self.client.force_login(self.boss)
        self.client.post(reverse('estado_trabajador_jefe', args=[self.employee.pk]), {'accion': 'desactivar'})
        response = self.client.get(reverse('auditoria_jefe'), {'categoria': 'permisos'})
        self.assertNotContains(response, 'Baja de trabajador')

    def test_recuperacion_nip_no_muestra_secretos(self):
        code = create_pin_reset(credential=self.credential, operator=self.boss)
        self.client.force_login(self.boss)
        response = self.client.get(reverse('auditoria_jefe'), {'categoria': 'nip'})
        self.assertContains(response, 'Recuperación de NIP autorizada')
        self.assertNotContains(response, code)
        self.assertNotContains(response, self.credential.pin_hash)

    def test_muestra_nip_restaurado_y_no_su_codigo(self):
        code = create_pin_reset(credential=self.credential, operator=self.boss)
        reset_employee_pin(credential_id=self.credential.pk, code=code, new_pin='672940')
        events = audit_entries(categoria='nip')
        self.assertTrue(any(e['action'] == 'Recuperación de NIP completada' for e in events))
        self.assertFalse(any(code in str(e) or '672940' in str(e) for e in events))

    def test_pagina_solo_admite_lectura(self):
        self.client.force_login(self.boss)
        self.assertEqual(self.client.post(reverse('auditoria_jefe')).status_code, 405)
