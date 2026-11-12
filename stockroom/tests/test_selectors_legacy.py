
from django.test import TestCase

from stockroom.models import (
    Article,
    Employee,
    Loan,
    QuantityIssue,
    Tool,
)
from stockroom.selectors import (
    catalogo_articulos,
    piezas_individuales_disponibles,
)


class SelectorLegacyTests(TestCase):

    def setUp(self):
        self.empleado = Employee.objects.create(
            employee_id="TEST-SEL-001",
            first_name="Trabajador",
            last_name="Selector",
        )

        self.articulo = Article.objects.create(
            article_code="TEST-SEL-ART",
            name="Vernier para pruebas",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
        )

        self.libre = Tool.objects.create(
            article=self.articulo,
            tool_code="TEST-SEL-LIBRE",
            name="Vernier libre",
            inventory_status=Tool.InventoryStatus.AVAILABLE,
        )

        self.bloqueada = Tool.objects.create(
            article=self.articulo,
            tool_code="TEST-SEL-BLOQ",
            name="Vernier con adeudo",
            inventory_status=Tool.InventoryStatus.AVAILABLE,
        )

        prestamo = Loan.objects.create(
            tool=self.bloqueada,
            employee=self.empleado,
        )

        # Entrega unificada completamente devuelta,
        # pero el préstamo antiguo permanece abierto.
        QuantityIssue.objects.create(
            tool=self.bloqueada,
            employee=self.empleado,
            legacy_loan=prestamo,
            quantity=1,
            returned_quantity=1,
            requires_return=True,
        )

    def test_selector_excluye_legacy_vinculado_abierto(self):
        disponibles = set(
            piezas_individuales_disponibles()
            .values_list("tool_code", flat=True)
        )

        self.assertEqual(
            disponibles,
            {"TEST-SEL-LIBRE"},
        )

    def test_catalogo_no_cuenta_pieza_bloqueada(self):
        articulo = catalogo_articulos().get(
            pk=self.articulo.pk
        )

        self.assertEqual(
            articulo.available_quantity,
            1,
        )
