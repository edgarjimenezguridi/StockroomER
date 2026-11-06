from django.core.exceptions import ValidationError
from django.test import TestCase

from stockroom.models import(
    Tool,
    Article,
    Employee,
    QuantityStock,
    QuantityIssue,
    QuantityReturn,
)
from stockroom.services import (
    register_quantity_issue,
    register_return_and_exchange,
    register_quantity_return,
)


class ExchangeTests(TestCase):
    def test_consumable_issue_does_not_create_return_obligation(self):
        employee = Employee.objects.create(
            employee_id="TEST-003",
            first_name="Trabajador",
            last_name="De prueba",
        )
        article = Article.objects.create(
            article_code="TEST-CONSUMIBLE",
            name="Consumible de prueba",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.CONSUMABLE,
        )
        stock = QuantityStock.objects.create(
            article=article,
            available_quantity=5,
        )

        issue = QuantityIssue(
            stock=stock,
            employee=employee,
            quantity=2,
        )
        register_quantity_issue(issue)

        stock.refresh_from_db()
        issue.refresh_from_db()

        self.assertEqual(stock.available_quantity, 3)
        self.assertEqual(stock.loaned_quantity, 0)
        self.assertEqual(stock.quarantine_quantity, 0)
        self.assertFalse(issue.requires_return)
        self.assertEqual(issue.employee_id, employee.pk)
        self.assertEqual(issue.quantity, 2)

        # Una salida sin devolución no admite este flujo de retorno.
        returned = QuantityReturn(
            issue=issue,
            quantity=1,
            condition=QuantityReturn.Condition.GOOD,
        )

        with self.assertRaises(ValidationError):
            register_quantity_return(returned)

        stock.refresh_from_db()
        issue.refresh_from_db()

        self.assertEqual(stock.available_quantity, 3)
        self.assertEqual(stock.loaned_quantity, 0)
        self.assertEqual(stock.quarantine_quantity, 0)
        self.assertEqual(issue.returned_quantity, 0)
        self.assertEqual(QuantityReturn.objects.count(), 0)
        self.assertEqual(QuantityIssue.objects.count(), 1)

    def test_individual_exchange_links_replacement(self):
        employee = Employee.objects.create(
            employee_id="TEST-002",
            first_name="Trabajador",
            last_name="De prueba",
        )
        article = Article.objects.create(
            article_code="TEST-VERNIER",
            name="Vernier de prueba",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        original_tool = Tool.objects.create(
            article=article,
            tool_code="TEST-TOOL-1",
            name="Vernier original",
        )
        replacement_tool = Tool.objects.create(
            article=article,
            tool_code="TEST-TOOL-2",
            name="Vernier de reemplazo",
        )

        original_issue = QuantityIssue(
            tool=original_tool,
            employee=employee,
            quantity=1,
        )
        register_quantity_issue(original_issue)

        returned = QuantityReturn(
            issue=original_issue,
            quantity=1,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Daño de prueba",
        )
        replacement_issue = register_return_and_exchange(
            returned,
            replacement_tool_id=replacement_tool.pk,
        )

        original_tool.refresh_from_db()
        replacement_tool.refresh_from_db()
        original_issue.refresh_from_db()
        replacement_issue.refresh_from_db()

        self.assertEqual(
            original_tool.inventory_status,
            Tool.InventoryStatus.QUARANTINE,
        )
        self.assertEqual(
            replacement_tool.inventory_status,
            Tool.InventoryStatus.LOANED,
        )
        self.assertEqual(original_issue.returned_quantity, 1)
        self.assertEqual(replacement_issue.returned_quantity, 0)
        self.assertEqual(replacement_issue.quantity, 1)
        self.assertTrue(replacement_issue.requires_return)
        self.assertEqual(replacement_issue.employee_id, employee.pk)
        self.assertEqual(
            replacement_issue.tool_id,
            replacement_tool.pk,
        )
        self.assertEqual(
            replacement_issue.replacement_for_id,
            returned.pk,
        )
        self.assertEqual(QuantityReturn.objects.count(), 1)
        self.assertEqual(QuantityIssue.objects.count(), 2)

    def test_exchange_without_stock_rolls_back_everything(self):
        employee = Employee.objects.create(
            employee_id="TEST-001",
            first_name="Trabajador",
            last_name="De prueba",
        )
        article = Article.objects.create(
            article_code="TEST-ART",
            name="Machuelo de prueba",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        stock = QuantityStock.objects.create(
            article=article,
            available_quantity=1,
        )

        issue = QuantityIssue(
            stock=stock,
            employee=employee,
            quantity=1,
        )
        register_quantity_issue(issue)

        # La única pieza está prestada: no hay otra para reemplazarla.
        stock.refresh_from_db()
        self.assertEqual(stock.available_quantity, 0)
        self.assertEqual(stock.loaned_quantity, 1)

        returned = QuantityReturn(
            issue=issue,
            quantity=1,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Rotura durante la prueba",
        )

        with self.assertRaises(ValidationError):
            register_return_and_exchange(returned)

        stock.refresh_from_db()
        issue.refresh_from_db()

        # El intento fallido debe dejar todo como estaba.
        self.assertEqual(stock.available_quantity, 0)
        self.assertEqual(stock.loaned_quantity, 1)
        self.assertEqual(stock.quarantine_quantity, 0)
        self.assertEqual(issue.returned_quantity, 0)
        self.assertEqual(QuantityReturn.objects.count(), 0)
        self.assertEqual(QuantityIssue.objects.count(), 1)
        self.assertFalse(
            QuantityIssue.objects.filter(
                replacement_for__isnull=False
            ).exists()
        )