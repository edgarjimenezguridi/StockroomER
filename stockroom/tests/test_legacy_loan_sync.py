
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from stockroom.models import (
    Article,
    Employee,
    Loan,
    QuantityIssue,
    QuantityReturn,
    Tool,
)
from stockroom.services import (
    register_quantity_return,
    register_return_and_exchange,
)


class LegacyLoanSynchronizationTests(TestCase):

    def setUp(self):
        self.fecha_entrega = timezone.now()
        self.fecha_devolucion = (
            self.fecha_entrega + timedelta(minutes=15)
        )

        self.empleado = Employee.objects.create(
            employee_id="TEST-001",
            first_name="Trabajador",
            last_name="Prueba",
            is_active=True,
        )

        self.articulo = Article.objects.create(
            article_code="TEST-LEGACY-001",
            name="Vernier de prueba",
            brand="Mitutoyo",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
            is_active=True,
        )

        self.herramienta = Tool.objects.create(
            article=self.articulo,
            tool_code="TEST-TOOL-001",
            name="Vernier de prueba",
            brand="Mitutoyo",
            is_active=True,
            inventory_status=Tool.InventoryStatus.LOANED,
        )

        self.prestamo = Loan.objects.create(
            employee=self.empleado,
            tool=self.herramienta,
            borrowed_at=self.fecha_entrega,
        )

        self.entrega = QuantityIssue.objects.create(
            legacy_loan=self.prestamo,
            tool=self.herramienta,
            employee=self.empleado,
            quantity=1,
            returned_quantity=0,
            requires_return=True,
            issued_at=self.fecha_entrega,
            notes="Préstamo antiguo vinculado para prueba.",
        )

    def test_devolucion_completa_cierra_prestamo_legacy(self):
        devolucion = QuantityReturn(
            issue=self.entrega,
            quantity=1,
            condition=QuantityReturn.Condition.GOOD,
            returned_at=self.fecha_devolucion,
        )

        register_quantity_return(devolucion)

        self.entrega.refresh_from_db()
        self.prestamo.refresh_from_db()
        self.herramienta.refresh_from_db()

        self.assertEqual(
            self.entrega.returned_quantity,
            1,
        )

        self.assertEqual(
            self.prestamo.returned_at,
            self.fecha_devolucion,
        )

        self.assertEqual(
            self.herramienta.inventory_status,
            Tool.InventoryStatus.AVAILABLE,
        )

        self.assertEqual(
            QuantityReturn.objects.filter(
                issue=self.entrega
            ).count(),
            1,
        )

    def test_devolucion_danada_cierra_legacy_y_envia_a_revision(self):
        devolucion = QuantityReturn(
            issue=self.entrega,
            quantity=1,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Herramienta dañada durante su uso.",
            returned_at=self.fecha_devolucion,
        )

        register_quantity_return(devolucion)

        self.entrega.refresh_from_db()
        self.prestamo.refresh_from_db()
        self.herramienta.refresh_from_db()

        self.assertEqual(
            self.entrega.returned_quantity,
            1,
        )

        self.assertEqual(
            self.prestamo.returned_at,
            self.fecha_devolucion,
        )

        self.assertEqual(
            self.herramienta.inventory_status,
            Tool.InventoryStatus.QUARANTINE,
        )

    def test_prestamo_incorrecto_revierte_toda_la_operacion(self):
        otro_empleado = Employee.objects.create(
            employee_id="TEST-002",
            first_name="Otro",
            last_name="Trabajador",
            is_active=True,
        )

        # Simulamos una entrega incorrectamente vinculada.
        self.entrega.employee = otro_empleado
        self.entrega.save(update_fields=["employee"])

        devolucion = QuantityReturn(
            issue=self.entrega,
            quantity=1,
            condition=QuantityReturn.Condition.GOOD,
            returned_at=self.fecha_devolucion,
        )

        with self.assertRaises(ValidationError):
            register_quantity_return(devolucion)

        self.entrega.refresh_from_db()
        self.prestamo.refresh_from_db()
        self.herramienta.refresh_from_db()

        # Ningún movimiento debe quedar parcialmente aplicado.
        self.assertEqual(
            self.entrega.returned_quantity,
            0,
        )

        self.assertIsNone(
            self.prestamo.returned_at
        )

        self.assertEqual(
            self.herramienta.inventory_status,
            Tool.InventoryStatus.LOANED,
        )

        self.assertFalse(
            QuantityReturn.objects.filter(
                issue=self.entrega
            ).exists()
        )

    def test_entrega_sin_legacy_se_devuelve_normalmente(self):
        # Una entrega nueva no necesita un préstamo Loan.
        self.entrega.legacy_loan = None
        self.entrega.save(update_fields=["legacy_loan"])

        # Cerramos el registro legacy de prueba para no
        # dejar un préstamo antiguo abierto artificialmente.
        self.prestamo.returned_at = self.fecha_entrega
        self.prestamo.save(update_fields=["returned_at"])

        devolucion = QuantityReturn(
            issue=self.entrega,
            quantity=1,
            condition=QuantityReturn.Condition.GOOD,
            returned_at=self.fecha_devolucion,
        )

        register_quantity_return(devolucion)

        self.entrega.refresh_from_db()
        self.herramienta.refresh_from_db()

        self.assertEqual(
            self.entrega.returned_quantity,
            1,
        )

        self.assertEqual(
            self.herramienta.inventory_status,
            Tool.InventoryStatus.AVAILABLE,
        )

    def test_cambio_individual_cierra_prestamo_legacy(self):
        reemplazo = Tool.objects.create(
            article=self.articulo,
            tool_code="TEST-TOOL-002",
            name="Vernier de reemplazo",
            brand="Mitutoyo",
            is_active=True,
            inventory_status=Tool.InventoryStatus.AVAILABLE,
        )

        devolucion = QuantityReturn(
            issue=self.entrega,
            quantity=1,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Herramienta dañada durante el uso.",
            returned_at=self.fecha_devolucion,
        )

        nueva_entrega = register_return_and_exchange(
            devolucion,
            replacement_tool_id=reemplazo.pk,
        )

        self.entrega.refresh_from_db()
        self.prestamo.refresh_from_db()
        self.herramienta.refresh_from_db()
        reemplazo.refresh_from_db()

        # La entrega anterior quedó completamente devuelta.
        self.assertEqual(
            self.entrega.returned_quantity,
            1,
        )

        # El préstamo antiguo quedó cerrado.
        self.assertEqual(
            self.prestamo.returned_at,
            self.fecha_devolucion,
        )

        # La pieza dañada pasó a revisión.
        self.assertEqual(
            self.herramienta.inventory_status,
            Tool.InventoryStatus.QUARANTINE,
        )

        # La herramienta de reemplazo quedó prestada.
        self.assertEqual(
            reemplazo.inventory_status,
            Tool.InventoryStatus.LOANED,
        )

        # Ambas operaciones quedaron relacionadas.
        self.assertEqual(
            nueva_entrega.replacement_for_id,
            devolucion.pk,
        )

        self.assertEqual(
            nueva_entrega.tool_id,
            reemplazo.pk,
        )

        self.assertEqual(
            nueva_entrega.employee_id,
            self.empleado.pk,
        )

        # Solo existe una devolución del préstamo original.
        self.assertEqual(
            QuantityReturn.objects.filter(
                issue=self.entrega
            ).count(),
            1,
        )

    def test_cambio_fallido_no_cierra_prestamo_legacy(self):
        reemplazo = Tool.objects.create(
            article=self.articulo,
            tool_code="TEST-TOOL-003",
            name="Vernier no disponible",
            brand="Mitutoyo",
            is_active=True,
            inventory_status=Tool.InventoryStatus.LOANED,
        )

        devolucion = QuantityReturn(
            issue=self.entrega,
            quantity=1,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Herramienta dañada durante el uso.",
            returned_at=self.fecha_devolucion,
        )

        with self.assertRaises(ValidationError):
            register_return_and_exchange(
                devolucion,
                replacement_tool_id=reemplazo.pk,
            )

        self.entrega.refresh_from_db()
        self.prestamo.refresh_from_db()
        self.herramienta.refresh_from_db()
        reemplazo.refresh_from_db()

        # La entrega original debe seguir pendiente.
        self.assertEqual(
            self.entrega.returned_quantity,
            0,
        )

        # El préstamo antiguo NO debe cerrarse.
        self.assertIsNone(
            self.prestamo.returned_at
        )

        # La herramienta original sigue prestada.
        self.assertEqual(
            self.herramienta.inventory_status,
            Tool.InventoryStatus.LOANED,
        )

        # El reemplazo no se modificó.
        self.assertEqual(
            reemplazo.inventory_status,
            Tool.InventoryStatus.LOANED,
        )

        # No se registraron devoluciones ni reemplazos.
        self.assertFalse(
            QuantityReturn.objects.filter(
                issue=self.entrega
            ).exists()
        )

        self.assertFalse(
            QuantityIssue.objects.filter(
                replacement_for__issue=self.entrega
            ).exists()
        )
