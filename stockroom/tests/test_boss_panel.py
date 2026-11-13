from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from stockroom.models import (
    Article, DuplicateLoanAuthorization, Employee,
    MaterialRequest, MaterialRequestLine,
)


class PanelJefeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.jefe = User.objects.create_user(username="jefe-pruebas", password="test-pass-123", is_staff=True)
        self.jefe.groups.add(Group.objects.get_or_create(name="Jefes")[0])
        self.almacenista = User.objects.create_user(username="almacen-pruebas", password="test-pass-456", is_staff=True)
        self.employee = Employee.objects.create(employee_id="BOSS-TEST-1", first_name="Prueba", last_name="Empleado")
        self.article = Article.objects.create(article_code="BOSS-M8", name="Machuelo M8", tracking_mode="quantity", return_mode="returnable")
        self.request = MaterialRequest.objects.create(employee=self.employee, status=MaterialRequest.Status.SUBMITTED)
        MaterialRequestLine.objects.create(request=self.request, article=self.article, requested_quantity=1)
        self.authorization = DuplicateLoanAuthorization.objects.create(
            employee=self.employee, article=self.article, max_quantity=1, reason="Trabajo simultáneo"
        )

    def test_solo_jefe_consulta_panel(self):
        self.client.force_login(self.almacenista)
        self.assertEqual(self.client.get(reverse("panel_jefe")).status_code, 403)
        self.client.force_login(self.jefe)
        self.assertEqual(self.client.get(reverse("panel_jefe")).status_code, 200)

    def test_solo_jefe_puede_aprobar(self):
        url = reverse("resolver_autorizacion_jefe", args=[self.authorization.pk])
        self.client.force_login(self.almacenista)
        self.assertEqual(self.client.post(url, {"decision": "approve"}).status_code, 403)
        self.authorization.refresh_from_db()
        self.assertEqual(self.authorization.status, DuplicateLoanAuthorization.Status.PENDING)
        self.client.force_login(self.jefe)
        self.assertEqual(self.client.post(url, {"decision": "approve"}).status_code, 302)
        self.authorization.refresh_from_db()
        self.assertEqual(self.authorization.status, DuplicateLoanAuthorization.Status.APPROVED)
        self.assertEqual(self.authorization.decided_by_id, self.jefe.pk)

    def test_aprobacion_no_puede_revertirse(self):
        self.client.force_login(self.jefe)
        url = reverse("resolver_autorizacion_jefe", args=[self.authorization.pk])
        self.client.post(url, {"decision": "approve"})
        self.client.post(url, {"decision": "reject"})
        self.authorization.refresh_from_db()
        self.assertEqual(self.authorization.status, DuplicateLoanAuthorization.Status.APPROVED)

    def test_jefe_puede_rechazar(self):
        self.client.force_login(self.jefe)
        self.client.post(reverse("resolver_autorizacion_jefe", args=[self.authorization.pk]), {"decision": "reject"})
        self.authorization.refresh_from_db()
        self.assertEqual(self.authorization.status, DuplicateLoanAuthorization.Status.REJECTED)

    def test_solicitud_excepcion_exige_duplicado(self):
        self.client.force_login(self.jefe)
        new_article = Article.objects.create(article_code="BOSS-M6", name="Machuelo M6", tracking_mode="quantity", return_mode="returnable")
        response = self.client.post(reverse("panel_jefe"), {
            "employee": self.employee.pk, "article": new_article.pk,
            "max_quantity": 1, "reason": "Necesito otra herramienta",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(DuplicateLoanAuthorization.objects.filter(article=new_article).exists())
