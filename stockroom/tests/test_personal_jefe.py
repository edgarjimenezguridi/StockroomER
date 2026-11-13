from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from stockroom.models import Employee, EmployeeCredential


class PersonalJefeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.jefe = User.objects.create_user(username='boss_per_1', password='superclave123456', is_staff=True)
        cls.jefes, _ = Group.objects.get_or_create(name='Jefes')
        cls.jefe.groups.add(cls.jefes)
        cls.otro = User.objects.create_user(username='warehouse_per_2', password='superclave123456', is_staff=True)
        cls.trabajador = Employee.objects.create(employee_id='EMP-PER-1', first_name='Ana', last_name='Prueba')
        EmployeeCredential.objects.create(employee=cls.trabajador)

    def setUp(self):
        self.client.force_login(self.jefe)

    def test_solo_jefe_accede(self):
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(reverse('personal_jefe')).status_code, 403)
        self.assertEqual(self.client.post(reverse('estado_trabajador_jefe', args=[self.trabajador.pk]), {'accion': 'desactivar'}).status_code, 403)

    def test_alta_empleado_con_credencial(self):
        response = self.client.post(reverse('personal_jefe'), {
            'tipo': 'empleado', 'empleado-employee_id': 'EMP-PER-2',
            'empleado-first_name': 'Laura', 'empleado-last_name': 'Prueba',
        })
        self.assertEqual(response.status_code, 302)
        e = Employee.objects.get(employee_id='EMP-PER-2')
        self.assertTrue(EmployeeCredential.objects.filter(employee=e).exists())

    def test_no_permite_empleado_duplicado(self):
        self.client.post(reverse('personal_jefe'), {
            'tipo': 'empleado', 'empleado-employee_id': 'EMP-PER-1',
            'empleado-first_name': 'Otra', 'empleado-last_name': 'Persona',
        })
        self.assertEqual(Employee.objects.filter(employee_id='EMP-PER-1').count(), 1)

    def test_baja_y_reactivacion_preservan_empleado(self):
        ruta = reverse('estado_trabajador_jefe', args=[self.trabajador.pk])
        self.client.post(ruta, {'accion': 'desactivar'})
        self.trabajador.refresh_from_db()
        self.assertFalse(self.trabajador.is_active)
        self.assertFalse(self.trabajador.credential.is_active)
        self.client.post(ruta, {'accion': 'activar'})
        self.trabajador.refresh_from_db()
        self.assertTrue(self.trabajador.is_active)
        self.trabajador.credential.refresh_from_db()
        self.assertTrue(self.trabajador.credential.is_active)

    def test_no_modificar_propia_cuenta(self):
        response = self.client.post(reverse('estado_cuenta_jefe', args=[self.jefe.pk]), {'accion': 'desactivar'})
        self.assertEqual(response.status_code, 403)
        self.jefe.refresh_from_db()
        self.assertTrue(self.jefe.is_active)

    def test_alta_almacenista_rol_y_sin_superusuario(self):
        response = self.client.post(reverse('personal_jefe'), {
            'tipo': 'cuenta', 'cuenta-username': 'alm_nuevo',
            'cuenta-first_name': 'Nuevo', 'cuenta-last_name': 'Almacenista',
            'cuenta-role': 'warehouse', 'cuenta-password': 'ClaveInicialSegura123!',
        })
        self.assertEqual(response.status_code, 302)
        u = get_user_model().objects.get(username='alm_nuevo')
        self.assertTrue(u.is_staff)
        self.assertFalse(u.is_superuser)
        self.assertTrue(u.has_perm('stockroom.view_materialrequest'))
        self.assertFalse(u.has_perm('auth.add_user'))

    def test_puede_ver_expediente(self):
        response = self.client.get(reverse('expediente_trabajador_jefe', args=[self.trabajador.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'EMP-PER-1')

    def test_cuenta_superusuario_protegida(self):
        u = get_user_model().objects.create_superuser(username='super_per', password='superclave123456')
        response = self.client.post(reverse('estado_cuenta_jefe', args=[u.pk]), {'accion': 'desactivar'})
        self.assertEqual(response.status_code, 403)
        u.refresh_from_db()
        self.assertTrue(u.is_active)

    def test_cambio_de_rol_jefatura_a_almacen(self):
        self.otro.groups.add(self.jefes)
        response = self.client.post(
            reverse('estado_cuenta_jefe', args=[self.otro.pk]),
            {'accion': 'warehouse'},
        )
        self.assertEqual(response.status_code, 302)
        self.otro.refresh_from_db()
        self.assertFalse(self.otro.groups.filter(name='Jefes').exists())
        self.assertTrue(self.otro.has_perm('stockroom.view_materialrequest'))

    def test_cuentas_con_permisos_extra_requieren_administrador(self):
        other_group = Group.objects.create(name='Grupo extra')
        self.otro.groups.add(other_group)
        response = self.client.post(
            reverse('estado_cuenta_jefe', args=[self.otro.pk]),
            {'accion': 'boss'},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(self.otro.groups.filter(name='Jefes').exists())
