from django.core.exceptions import ValidationError
from django.test import TestCase

from .models import (
    Article,
    DamageResolution,
    Employee,
    QuantityIssue,
    QuantityReturn,
    QuantityStock,
    Tool,
)
from .services import (
    register_damage_resolution,
    register_quantity_issue,
    register_quantity_return,
)


class DamageResolutionTests(TestCase):
    def test_scrapped_individual_tool_cannot_be_issued_again(self):
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
        tool = Tool.objects.create(
            article=article,
            tool_code="TEST-TOOL",
            name="Vernier de prueba",
        )

        issue = QuantityIssue(
            tool=tool,
            employee=employee,
            quantity=1,
        )
        register_quantity_issue(issue)

        returned = QuantityReturn(
            issue=issue,
            quantity=1,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Daño irreparable de prueba",
        )
        register_quantity_return(returned)

        resolution = DamageResolution(
            source_return=returned,
            quantity=1,
            outcome=DamageResolution.Outcome.SCRAPPED,
            reason="Pieza no recuperable",
        )
        register_damage_resolution(resolution)

        tool.refresh_from_db()
        returned.refresh_from_db()
        issue.refresh_from_db()

        self.assertEqual(
            tool.inventory_status,
            Tool.InventoryStatus.SCRAPPED,
        )
        self.assertFalse(tool.is_active)
        self.assertEqual(returned.resolved_quantity, 1)
        self.assertEqual(issue.returned_quantity, 1)

        new_issue = QuantityIssue(
            tool=tool,
            employee=employee,
            quantity=1,
        )

        with self.assertRaises(ValidationError):
            register_quantity_issue(new_issue)

        tool.refresh_from_db()

        self.assertEqual(
            tool.inventory_status,
            Tool.InventoryStatus.SCRAPPED,
        )
        self.assertFalse(tool.is_active)
        self.assertEqual(QuantityIssue.objects.count(), 1)
        self.assertEqual(QuantityReturn.objects.count(), 1)
        self.assertEqual(DamageResolution.objects.count(), 1)

    def test_cannot_resolve_same_piece_twice(self):
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

        returned = QuantityReturn(
            issue=issue,
            quantity=1,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Daño de prueba",
        )
        register_quantity_return(returned)

        recovery = DamageResolution(
            source_return=returned,
            quantity=1,
            outcome=DamageResolution.Outcome.RESTORED,
            reason="Pieza recuperada",
        )
        register_damage_resolution(recovery)

        duplicate = DamageResolution(
            source_return=returned,
            quantity=1,
            outcome=DamageResolution.Outcome.SCRAPPED,
            reason="Intento de resolver otra vez",
        )

        with self.assertRaises(ValidationError):
            register_damage_resolution(duplicate)

        stock.refresh_from_db()
        returned.refresh_from_db()

        self.assertEqual(stock.available_quantity, 1)
        self.assertEqual(stock.loaned_quantity, 0)
        self.assertEqual(stock.quarantine_quantity, 0)
        self.assertEqual(stock.scrapped_quantity, 0)
        self.assertEqual(returned.resolved_quantity, 1)
        self.assertEqual(DamageResolution.objects.count(), 1)
        self.assertEqual(
            DamageResolution.objects.get().outcome,
            DamageResolution.Outcome.RESTORED,
        )