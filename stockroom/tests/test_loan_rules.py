from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from stockroom.loan_rules import (
    estado_prestamo,
    fecha_limite,
    motivo_duplicado,
    tiene_adeudos_vencidos,
    validar_bloqueo_vencimiento,
    validar_sin_duplicado,
)
from stockroom.models import (
    Article, Employee, MaterialRequest, MaterialRequestLine,
    QuantityIssue, QuantityStock,
)


class LoanRulesTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            employee_id="REGLAS-TEST-001", first_name="Ana", last_name="Prueba",
        )
        self.article = Article.objects.create(
            article_code="REGLAS-M8", name="Machuelo M8",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.stock = QuantityStock.objects.create(article=self.article, available_quantity=10)

    def issue(self, *, days=1, quantity=1, returned=0):
        return QuantityIssue.objects.create(
            employee=self.employee, stock=self.stock,
            quantity=quantity, returned_quantity=returned,
            requires_return=True,
            issued_at=timezone.now() - timedelta(days=days),
        )

    def test_vencimiento_bloquea_todas_las_comandas(self):
        self.issue(days=16)
        self.assertTrue(tiene_adeudos_vencidos(self.employee.pk))
        with self.assertRaisesMessage(ValidationError, "préstamos vencidos"):
            validar_bloqueo_vencimiento(self.employee.pk)

    def test_prestamo_dentro_del_plazo_no_bloquea_globalmente(self):
        self.issue(days=14)
        validar_bloqueo_vencimiento(self.employee.pk)

    def test_devolucion_parcial_no_desbloquea(self):
        self.issue(days=16, quantity=3, returned=2)
        self.assertTrue(tiene_adeudos_vencidos(self.employee.pk))

    def test_devolucion_completa_desbloquea(self):
        self.issue(days=16, quantity=3, returned=3)
        validar_bloqueo_vencimiento(self.employee.pk)
        self.assertIsNone(motivo_duplicado(
            employee_id=self.employee.pk, article_id=self.article.pk,
        ))

    def test_adeudo_vigente_impide_articulo_duplicado(self):
        self.issue(days=1)
        with self.assertRaisesMessage(
                ValidationError,
                "autorización aprobada del jefe",
            ):
            validar_sin_duplicado(
                employee_id=self.employee.pk, article_id=self.article.pk,
            )

    def test_solicitud_activa_impide_duplicado(self):
        req = MaterialRequest.objects.create(
            employee=self.employee, status=MaterialRequest.Status.SUBMITTED,
        )
        MaterialRequestLine.objects.create(
            request=req, article=self.article, requested_quantity=1,
        )
        self.assertIsNotNone(motivo_duplicado(
            employee_id=self.employee.pk, article_id=self.article.pk,
        ))
        self.assertIsNone(motivo_duplicado(
            employee_id=self.employee.pk,
            article_id=self.article.pk,
            excluir_solicitud_id=req.pk,
        ))

    def test_fecha_limite(self):
        issue = self.issue(days=16)
        self.assertEqual(fecha_limite(issue), issue.issued_at + timedelta(days=15))
        self.assertEqual(estado_prestamo(issue), "vencido")
