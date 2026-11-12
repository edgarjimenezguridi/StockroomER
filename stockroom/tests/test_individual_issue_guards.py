
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from stockroom.models import (
    Article,
    Employee,
    Loan,
    QuantityIssue,
    Tool,
)
from stockroom.services import register_individual_issue


class IndividualIssueGuardTests(TestCase):

    def setUp(self):
        self.empleado = Employee.objects.create(
            employee_id="TEST-SEG-001",
            first_name="Trabajador",
            last_name="Seguridad",
            is_active=True,
        )

        self.articulo = Article.objects.create(
            article_code="TEST-SEG-ART",
            name="Vernier de seguridad",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
            is_active=True,
        )

        self.pieza = Tool.objects.create(
            article=self.articulo,
            tool_code="TEST-SEG-TOOL",
            name="Vernier de prueba",
            inventory_status=Tool.InventoryStatus.AVAILABLE,
            is_active=True,
        )

    def nueva_entrega(self):
        return QuantityIssue(
            tool=self.pieza,
            employee=self.empleado,
            quantity=1,
        )

    def comprobar_rechazo_sin_cambios(self):
        cantidad_anterior = QuantityIssue.objects.count()

        with self.assertRaises(ValidationError):
            register_individual_issue(
                self.nueva_entrega()
            )

        self.pieza.refresh_from_db()

        self.assertEqual(
            QuantityIssue.objects.count(),
            cantidad_anterior,
        )

        self.assertEqual(
            self.pieza.inventory_status,
            Tool.InventoryStatus.AVAILABLE,
        )

    def test_rechaza_prestamo_antiguo_sin_vincular(self):
        Loan.objects.create(
            tool=self.pieza,
            employee=self.empleado,
        )

        self.comprobar_rechazo_sin_cambios()

    def test_rechaza_entrega_unificada_pendiente(self):
        QuantityIssue.objects.create(
            tool=self.pieza,
            employee=self.empleado,
            quantity=1,
            returned_quantity=0,
            requires_return=True,
        )

        self.comprobar_rechazo_sin_cambios()

    def test_rechaza_prestamo_antiguo_vinculado_abierto(self):
        prestamo = Loan.objects.create(
            tool=self.pieza,
            employee=self.empleado,
            borrowed_at=timezone.now(),
        )

        # La entrega unificada ya figura completamente
        # devuelta, pero el préstamo antiguo sigue abierto.
        QuantityIssue.objects.create(
            legacy_loan=prestamo,
            tool=self.pieza,
            employee=self.empleado,
            quantity=1,
            returned_quantity=1,
            requires_return=True,
        )

        # Reproducimos el estado inconsistente:
        # pieza disponible + préstamo antiguo abierto.
        self.comprobar_rechazo_sin_cambios()

    def test_pieza_realmente_libre_puede_entregarse(self):
        entrega = register_individual_issue(
            self.nueva_entrega()
        )

        self.pieza.refresh_from_db()

        self.assertIsNotNone(entrega.pk)

        self.assertEqual(
            self.pieza.inventory_status,
            Tool.InventoryStatus.LOANED,
        )

        self.assertTrue(entrega.requires_return)

