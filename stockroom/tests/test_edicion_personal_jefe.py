
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee


class EdicionPersonalJefeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_user(
            username='jefe_edicion',
            password='ClaveSegura123!',
            is_staff=True,
        )
        grupo, _ = Group.objects.get_or_create(name='Jefes')
        cls.jefe.groups.add(grupo)

        cls.almacenista = User.objects.create_user(
            username='almacen_edicion',
            password='ClaveSegura123!',
            is_staff=True,
        )

        cls.empleado = Employee.objects.create(
            employee_id='EDIT-001',
            first_name='Nombre',
            last_name='Anterior',
            is_active=True,
        )

    def test_jefe_puede_editar_datos(self):
        self.client.force_login(self.jefe)

        response = self.client.post(
            reverse('personal_jefe'),
            {
                'tipo': 'editar_empleado',
                'empleado_pk': str(self.empleado.pk),
                'editar-employee_id': 'EDIT-001',
                'editar-first_name': 'Nombre',
                'editar-last_name': 'Actualizado',
            },
        )

        self.assertEqual(response.status_code, 302)

        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.last_name, 'Actualizado')
        self.assertTrue(self.empleado.is_active)

    def test_almacenista_no_puede_editar(self):
        self.client.force_login(self.almacenista)

        response = self.client.post(
            reverse('personal_jefe'),
            {
                'tipo': 'editar_empleado',
                'empleado_pk': str(self.empleado.pk),
                'editar-employee_id': 'EDIT-001',
                'editar-first_name': 'Cambio',
                'editar-last_name': 'Indebido',
            },
        )

        self.assertEqual(response.status_code, 403)

        self.empleado.refresh_from_db()
        self.assertEqual(self.empleado.first_name, 'Nombre')

    def test_edicion_no_modifica_estado(self):
        self.client.force_login(self.jefe)

        self.client.post(
            reverse('personal_jefe'),
            {
                'tipo': 'editar_empleado',
                'empleado_pk': str(self.empleado.pk),
                'editar-employee_id': 'EDIT-001',
                'editar-first_name': 'Nuevo',
                'editar-last_name': 'Nombre',
                'editar-is_active': 'False',
            },
        )

        self.empleado.refresh_from_db()
        self.assertTrue(self.empleado.is_active)
