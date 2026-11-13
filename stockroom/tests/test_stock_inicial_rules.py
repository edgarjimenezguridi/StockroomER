from datetime import timedelta
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from stockroom.models import Article, Employee, QuantityIssue, QuantityStock
from stockroom.loan_rules import (
    entregas_vencidas, tiene_adeudos_vencidos, fecha_limite,
    estado_prestamo, motivo_duplicado, validar_bloqueo_vencimiento,
)

class StockInicialReglasTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            employee_id="FASE15-001", first_name="Prueba", last_name="Inicial"
        )
        self.article = Article.objects.create(
            article_code="FASE15-ART", name="Herramienta inicial",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.stock = QuantityStock.objects.create(
            article=self.article, available_quantity=5,
        )

    def nueva_entrega(self, *, initial):
        return QuantityIssue.objects.create(
            employee=self.employee, stock=self.stock, quantity=1,
            requires_return=True, is_initial_stock=initial,
            issued_at=timezone.now() - timedelta(days=40),
        )

    def test_stock_inicial_no_vence_ni_bloquea(self):
        entrega = self.nueva_entrega(initial=True)
        self.assertIsNone(fecha_limite(entrega))
        self.assertEqual(estado_prestamo(entrega), "stock_inicial")
        self.assertFalse(entregas_vencidas(self.employee.pk).exists())
        self.assertFalse(tiene_adeudos_vencidos(self.employee.pk))
        validar_bloqueo_vencimiento(self.employee.pk)

    def test_stock_inicial_si_detecta_duplicado(self):
        self.nueva_entrega(initial=True)
        self.assertIsNotNone(motivo_duplicado(
            employee_id=self.employee.pk, article_id=self.article.pk,
        ))

    def test_entrega_normal_sigue_venciendo(self):
        entrega = self.nueva_entrega(initial=False)
        self.assertIsNotNone(fecha_limite(entrega))
        self.assertEqual(estado_prestamo(entrega), "vencido")
        self.assertTrue(entregas_vencidas(self.employee.pk).exists())
        with self.assertRaises(ValidationError):
            validar_bloqueo_vencimiento(self.employee.pk)

    def test_stock_inicial_devuelto_es_devuelto(self):
        entrega = self.nueva_entrega(initial=True)
        entrega.returned_quantity = 1
        entrega.save(update_fields=["returned_quantity"])
        self.assertEqual(estado_prestamo(entrega), "devuelto")
        self.assertIsNone(motivo_duplicado(
            employee_id=self.employee.pk, article_id=self.article.pk,
        ))
