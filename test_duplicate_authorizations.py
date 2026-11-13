from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from stockroom.duplicate_authorization_admin import es_jefe
from stockroom.loan_rules import (
    validar_bloqueo_vencimiento,
    validar_sin_duplicado,
    vincular_autorizacion_si_necesaria,
)
from stockroom.models import (
    Article, DuplicateLoanAuthorization, Employee,
    MaterialRequest, QuantityIssue, QuantityStock,
)


class DuplicateAuthorizationTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            employee_id='AUT-TEST-001', first_name='Prueba', last_name='Autorización'
        )
        self.article = Article.objects.create(
            article_code='AUT-M8-001', name='Machuelo M8',
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.cart = MaterialRequest.objects.create(
            employee=self.employee, status=MaterialRequest.Status.DRAFT
        )

    def create_approved(self, quantity=1):
        return DuplicateLoanAuthorization.objects.create(
            employee=self.employee, article=self.article,
            max_quantity=quantity, reason='Trabajo simultáneo',
            status=DuplicateLoanAuthorization.Status.APPROVED,
        )

    @patch('stockroom.loan_rules.motivo_duplicado', return_value='Duplicado')
    def test_denies_without_approval(self, _motivo):
        with self.assertRaises(ValidationError):
            validar_sin_duplicado(
                employee_id=self.employee.pk, article_id=self.article.pk,
                excluir_solicitud_id=self.cart.pk, quantity=1,
            )

    @patch('stockroom.loan_rules.motivo_duplicado', return_value='Duplicado')
    def test_approval_is_quantity_bounded(self, _motivo):
        self.create_approved(quantity=1)
        with self.assertRaises(ValidationError):
            validar_sin_duplicado(
                employee_id=self.employee.pk, article_id=self.article.pk,
                excluir_solicitud_id=self.cart.pk, quantity=2,
            )

    @patch('stockroom.loan_rules.motivo_duplicado', return_value='Duplicado')
    def test_approval_bound_to_one_request(self, _motivo):
        approval = self.create_approved()
        vincular_autorizacion_si_necesaria(
            employee_id=self.employee.pk, article_id=self.article.pk,
            quantity=1, request_id=self.cart.pk,
        )
        approval.refresh_from_db()
        self.assertEqual(approval.used_request_id, self.cart.pk)
        other = MaterialRequest.objects.create(
            employee=self.employee, status=MaterialRequest.Status.SUBMITTED
        )
        with self.assertRaises(ValidationError):
            validar_sin_duplicado(
                employee_id=self.employee.pk, article_id=self.article.pk,
                excluir_solicitud_id=other.pk, quantity=1,
            )

    def test_overdue_blocks_even_with_approval(self):
        self.create_approved()
        stock = QuantityStock.objects.create(article=self.article, available_quantity=0)
        QuantityIssue.objects.create(
            employee=self.employee, stock=stock, quantity=1,
            requires_return=True,
            issued_at=timezone.now() - timedelta(days=16),
        )
        with self.assertRaises(ValidationError):
            validar_bloqueo_vencimiento(self.employee.pk)

    def test_only_boss_role_can_approve(self):
        user_model = get_user_model()
        staff = user_model.objects.create_user(
            username='test_staff_approval', password='unused', is_staff=True
        )
        boss = user_model.objects.create_superuser(
            username='test_boss_approval', password='unused'
        )
        self.assertFalse(es_jefe(staff))
        self.assertTrue(es_jefe(boss))
