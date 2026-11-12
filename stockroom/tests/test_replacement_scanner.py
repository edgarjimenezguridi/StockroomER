
from django.test import TestCase

from stockroom.models import (
    Article,
    Employee,
    Loan,
    QuantityIssue,
    QuantityReturn,
    Tool,
)
from stockroom.warehouse_forms import WarehouseReturnForm


class ReplacementScannerTests(TestCase):

    def setUp(self):
        self.employee = Employee.objects.create(
            employee_id="TEST-REPL-001",
            first_name="Trabajador",
            last_name="Escaner",
        )

        self.article = Article.objects.create(
            article_code="TEST-REPL-ART",
            name="Vernier",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
        )

        self.other_article = Article.objects.create(
            article_code="TEST-REPL-OTHER",
            name="Micrometro",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
        )

        def crear_pieza(code, article, status):
            return Tool.objects.create(
                article=article,
                tool_code=code,
                name=article.name,
                inventory_status=status,
            )

        self.original = crear_pieza(
            "TEST-REPL-ORIG",
            self.article,
            Tool.InventoryStatus.LOANED,
        )

        self.available = crear_pieza(
            "TEST-REPL-FREE",
            self.article,
            Tool.InventoryStatus.AVAILABLE,
        )

        self.other = crear_pieza(
            "TEST-REPL-OTHER-TOOL",
            self.other_article,
            Tool.InventoryStatus.AVAILABLE,
        )

        self.blocked = crear_pieza(
            "TEST-REPL-BLOCKED",
            self.article,
            Tool.InventoryStatus.AVAILABLE,
        )

        Loan.objects.create(
            tool=self.blocked,
            employee=self.employee,
        )

        self.issue = QuantityIssue.objects.create(
            tool=self.original,
            employee=self.employee,
            quantity=1,
            requires_return=True,
        )

    def formulario(self, codigo, operation="exchange"):
        return WarehouseReturnForm(
            data={
                "operation": operation,
                "quantity": 1,
                "condition": QuantityReturn.Condition.DAMAGED,
                "replacement_code": codigo,
                "reason": "Pieza dañada",
                "notes": "",
            },
            issue=self.issue,
            pending_quantity=1,
        )

    def test_acepta_codigo_valido(self):
        form = self.formulario("TEST-REPL-FREE")

        self.assertTrue(form.is_valid(), form.errors)

        self.assertEqual(
            form.cleaned_data["replacement_tool"].pk,
            self.available.pk,
        )

    def test_acepta_codigo_en_minusculas(self):
        form = self.formulario("test-repl-free")

        self.assertTrue(form.is_valid(), form.errors)

        self.assertEqual(
            form.cleaned_data["replacement_tool"].pk,
            self.available.pk,
        )

    def test_rechaza_prestamo_antiguo_pendiente(self):
        form = self.formulario("TEST-REPL-BLOCKED")

        self.assertFalse(form.is_valid())

        self.assertIn(
            "replacement_code",
            form.errors,
        )

    def test_rechaza_herramienta_de_otro_articulo(self):
        form = self.formulario("TEST-REPL-OTHER-TOOL")

        self.assertFalse(form.is_valid())

        self.assertIn(
            "replacement_code",
            form.errors,
        )

    def test_no_permite_reemplazo_en_devolucion_normal(self):
        form = self.formulario(
            "TEST-REPL-FREE",
            operation="return_only",
        )

        self.assertFalse(form.is_valid())

        self.assertIn(
            "replacement_code",
            form.errors,
        )
