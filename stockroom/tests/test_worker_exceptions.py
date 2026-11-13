from stockroom.worker_session_security import pin_session_version
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stockroom.models import (
    Article, DuplicateLoanAuthorization, Employee, EmployeeCredential,
    MaterialRequest, MaterialRequestLine, QuantityIssue, QuantityStock,
)


class WorkerDuplicateExceptionTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(employee_id='WORKER-EX1', first_name='Prueba', last_name='Uno')
        self.credential = EmployeeCredential.objects.create(employee=self.employee, pin_hash='test-hash')
        self.article = Article.objects.create(
            article_code='WORKER-M8', name='Machuelo M8',
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.url = reverse('solicitar_duplicado_empleado')

    def login_worker(self):
        session = self.client.session
        session['worker_employee_id'] = self.employee.pk
        session['worker_credential_id'] = self.credential.pk
        session["worker_pin_version"] = pin_session_version(self.credential.pin_hash)
        session.save()

    def make_duplicate(self):
        solicitud = MaterialRequest.objects.create(employee=self.employee, status=MaterialRequest.Status.SUBMITTED)
        MaterialRequestLine.objects.create(request=solicitud, article=self.article, requested_quantity=1)

    def payload(self):
        return {'article': self.article.pk, 'max_quantity': '1', 'reason': 'Se requiere otro machuelo para dos trabajos simultáneos.'}

    def test_sin_sesion_no_puede_consultar(self):
        self.assertRedirects(self.client.get(self.url), reverse('acceso_empleado'), fetch_redirect_response=False)

    def test_trabajador_solo_ve_sus_peticiones(self):
        other = Employee.objects.create(employee_id='WORKER-EX2', first_name='Otro', last_name='Empleado')
        DuplicateLoanAuthorization.objects.create(employee=other, article=self.article, max_quantity=1, reason='Razón privada del otro trabajador')
        self.login_worker()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Razón privada del otro trabajador')

    def test_no_crea_excepcion_si_no_es_duplicado(self):
        self.login_worker()
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DuplicateLoanAuthorization.objects.exists())

    def test_trabajador_crea_peticion_pendiente(self):
        self.make_duplicate()
        self.login_worker()
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 302)
        auth = DuplicateLoanAuthorization.objects.get()
        self.assertEqual(auth.employee_id, self.employee.pk)
        self.assertEqual(auth.status, DuplicateLoanAuthorization.Status.PENDING)
        self.assertIsNone(auth.decided_by_id)

    def test_no_duplica_peticion_pendiente(self):
        self.make_duplicate()
        self.login_worker()
        self.client.post(self.url, self.payload())
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(DuplicateLoanAuthorization.objects.count(), 1)

    def test_prestamo_vencido_bloquea_peticion(self):
        self.make_duplicate()
        stock = QuantityStock.objects.create(article=self.article, available_quantity=0, loaned_quantity=1)
        QuantityIssue.objects.create(
            employee=self.employee, stock=stock, quantity=1, returned_quantity=0,
            requires_return=True, issued_at=timezone.now() - timedelta(days=16),
        )
        self.login_worker()
        response = self.client.post(self.url, self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DuplicateLoanAuthorization.objects.exists())

    def test_no_puede_elegir_otro_trabajador(self):
        self.make_duplicate()
        other = Employee.objects.create(employee_id='WORKER-EX3', first_name='Otro', last_name='Empleado')
        self.login_worker()
        data = self.payload()
        data['employee'] = other.pk
        self.client.post(self.url, data)
        self.assertEqual(DuplicateLoanAuthorization.objects.get().employee_id, self.employee.pk)
