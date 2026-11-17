"""Pruebas de autorización de bajas: almacén solicita y jefe decide."""
from datetime import timedelta
from django.contrib.auth.models import Group, Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from stockroom.models import Employee, Article, QuantityStock, QuantityIssue, EmployeeOffboardingRequest


class BajaTrabajadoresTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(employee_id='BAJA-1', first_name='Prueba', last_name='Baja')
        self.almacenista = User.objects.create_user('almacen-prueba', password='clave-ficticia', is_staff=True)
        self.almacenista.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='stockroom', codename__in=['view_employee', 'view_quantityissue']
        ))
        self.jefe = User.objects.create_user('jefe-prueba', password='clave-ficticia', is_staff=True)
        group, _ = Group.objects.get_or_create(name='Jefes')
        self.jefe.groups.add(group)
        self.url = reverse('baja_trabajador_almacen')
        self.boss_url = reverse('solicitudes_baja_jefe')

    def solicitar(self):
        self.client.force_login(self.almacenista)
        return self.client.post(self.url, {'empleado': self.employee.pk, 'confirmacion': 'SOLICITAR'})

    def test_sin_login_redirige(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_sin_permisos_denegado(self):
        self.client.force_login(User.objects.create_user('sin-permisos', password='prueba'))
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_almacen_solicita_pero_no_desactiva(self):
        self.assertEqual(self.solicitar().status_code, 302)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertEqual(EmployeeOffboardingRequest.objects.filter(employee=self.employee, status='pending').count(), 1)

    def test_confirmacion_anterior_no_desactiva(self):
        self.client.force_login(self.almacenista)
        self.client.post(self.url, {'empleado': self.employee.pk, 'confirmacion': 'BAJA'})
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertFalse(EmployeeOffboardingRequest.objects.exists())

    def test_no_duplica_solicitudes_pendientes(self):
        self.solicitar()
        self.solicitar()
        self.assertEqual(EmployeeOffboardingRequest.objects.count(), 1)

    def test_solo_jefe_puede_decidir(self):
        self.solicitar()
        item = EmployeeOffboardingRequest.objects.get()
        self.client.force_login(self.almacenista)
        self.assertEqual(self.client.post(self.boss_url, {'solicitud': item.pk, 'accion': 'aprobar'}).status_code, 403)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_jefe_aprueba_y_registra_auditoria(self):
        self.solicitar()
        item = EmployeeOffboardingRequest.objects.get()
        self.client.force_login(self.jefe)
        self.assertEqual(self.client.post(self.boss_url, {'solicitud': item.pk, 'accion': 'aprobar'}).status_code, 302)
        self.employee.refresh_from_db()
        item.refresh_from_db()
        self.assertFalse(self.employee.is_active)
        self.assertEqual(item.status, 'approved')
        self.assertEqual(item.decided_by, self.jefe)
        self.assertIsNotNone(item.decided_at)

    def test_jefe_rechaza_sin_desactivar(self):
        self.solicitar()
        item = EmployeeOffboardingRequest.objects.get()
        self.client.force_login(self.jefe)
        self.client.post(self.boss_url, {'solicitud': item.pk, 'accion': 'rechazar'})
        self.employee.refresh_from_db()
        item.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertEqual(item.status, 'rejected')

    def test_adeudo_de_stock_inicial_impide_aprobacion(self):
        self.solicitar()
        article = Article.objects.create(article_code='BAJA-MART', name='Martillo', tracking_mode='quantity', return_mode='returnable')
        stock = QuantityStock.objects.create(article=article, available_quantity=5, loaned_quantity=1)
        QuantityIssue.objects.create(employee=self.employee, stock=stock, quantity=1, requires_return=True,
                                     is_initial_stock=True, issued_at=timezone.now()-timedelta(days=80))
        item = EmployeeOffboardingRequest.objects.get()
        self.client.force_login(self.jefe)
        self.client.post(self.boss_url, {'solicitud': item.pk, 'accion': 'aprobar'})
        self.employee.refresh_from_db()
        stock.refresh_from_db()
        item.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertEqual(item.status, 'pending')
        self.assertEqual((stock.available_quantity, stock.loaned_quantity), (5, 1))

    def test_consulta_no_modifica_inventario(self):
        self.client.force_login(self.almacenista)
        self.assertEqual(self.client.get(self.url, {'empleado': self.employee.pk}).status_code, 200)
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)
