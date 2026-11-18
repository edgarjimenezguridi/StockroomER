"""Fase 23M: recorrido de comanda y devolución en BD temporal.

No ejecutar como script independiente: usar `python manage.py test`.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.test import TestCase

from stockroom.fulfillment import (
    confirm_request_receipt,
    finish_request_preparation,
    prepare_request_line,
)
from stockroom.models import (
    Article, Employee, EmployeeCredential, MaterialRequest,
    MaterialRequestLine, QuantityIssue, QuantityReturn, QuantityStock,
)
from stockroom.services import register_quantity_return


class FlujoComanda23MTests(TestCase):
    """Integra preparación, NIP, existencias, adeudos y devoluciones."""

    def setUp(self):
        self.operator = get_user_model().objects.create_superuser(
            username="almacen_flujo_23m", password="SoloPrueba23M!"
        )
        self.employee = Employee.objects.create(
            employee_id="FLUJO-23M", first_name="Prueba", last_name="Comanda"
        )
        self.credential = EmployeeCredential.objects.create(
            employee=self.employee, pin_hash=make_password("012345")
        )
        self.article = Article.objects.create(
            article_code="FLUJO-23M-ART", name="Herramienta retornable prueba",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.stock = QuantityStock.objects.create(
            article=self.article, available_quantity=10
        )
        self.request = MaterialRequest.objects.create(
            employee=self.employee, status=MaterialRequest.Status.SUBMITTED
        )
        self.line = MaterialRequestLine.objects.create(
            request=self.request, article=self.article, requested_quantity=5
        )

    def preparar(self, cantidad=3):
        prepare_request_line(
            line_id=self.line.pk, quantity=cantidad, operator=self.operator
        )
        finish_request_preparation(
            request_id=self.request.pk, operator=self.operator
        )
        self.request.refresh_from_db()

    def confirmar(self, pin="012345"):
        return confirm_request_receipt(
            expected_version=self.request.preparation_version,
            request_id=self.request.pk,
            employee_id=self.employee.pk,
            credential_id=self.credential.pk,
            pin=pin,
        )

    def test_recorrido_preparar_confirmar_y_devolver_total(self):
        self.preparar(cantidad=3)
        self.stock.refresh_from_db()
        self.assertEqual(self.request.status, MaterialRequest.Status.PREPARED)
        self.assertEqual(self.stock.available_quantity, 10)
        self.assertEqual(QuantityIssue.objects.count(), 0)

        self.confirmar()
        self.request.refresh_from_db()
        self.stock.refresh_from_db()
        issue = QuantityIssue.objects.get(request_line=self.line)
        self.assertEqual(self.request.status, MaterialRequest.Status.CLOSED)
        self.assertEqual(issue.quantity, 3)
        self.assertTrue(issue.requires_return)
        self.assertEqual((self.stock.available_quantity, self.stock.loaned_quantity), (7, 3))

        register_quantity_return(QuantityReturn(
            issue=issue, quantity=1, condition=QuantityReturn.Condition.GOOD
        ))
        issue.refresh_from_db()
        self.stock.refresh_from_db()
        self.assertEqual(issue.quantity - issue.returned_quantity, 2)
        self.assertEqual((self.stock.available_quantity, self.stock.loaned_quantity), (8, 2))

        register_quantity_return(QuantityReturn(
            issue=issue, quantity=2, condition=QuantityReturn.Condition.GOOD
        ))
        issue.refresh_from_db()
        self.stock.refresh_from_db()
        self.assertEqual(issue.quantity - issue.returned_quantity, 0)
        self.assertEqual((self.stock.available_quantity, self.stock.loaned_quantity), (10, 0))
        self.assertEqual(QuantityReturn.objects.filter(issue=issue).count(), 2)

    def test_no_permite_confirmar_comanda_dos_veces(self):
        self.preparar()
        self.confirmar()
        with self.assertRaises(ValidationError):
            self.confirmar()
        self.stock.refresh_from_db()
        self.assertEqual(QuantityIssue.objects.filter(request_line=self.line).count(), 1)
        self.assertEqual((self.stock.available_quantity, self.stock.loaned_quantity), (7, 3))

    def test_nip_incorrecto_no_entrega_material(self):
        self.preparar()
        with self.assertRaises(ValidationError):
            self.confirmar(pin="999999")
        self.request.refresh_from_db()
        self.stock.refresh_from_db()
        self.assertEqual(self.request.status, MaterialRequest.Status.PREPARED)
        self.assertEqual(QuantityIssue.objects.count(), 0)
        self.assertEqual((self.stock.available_quantity, self.stock.loaned_quantity), (10, 0))

    def test_devolucion_excesiva_no_modifica_existencias(self):
        self.preparar()
        self.confirmar()
        issue = QuantityIssue.objects.get(request_line=self.line)
        with self.assertRaises(ValidationError):
            register_quantity_return(QuantityReturn(
                issue=issue, quantity=4, condition=QuantityReturn.Condition.GOOD
            ))
        issue.refresh_from_db()
        self.stock.refresh_from_db()
        self.assertEqual(issue.returned_quantity, 0)
        self.assertEqual(QuantityReturn.objects.count(), 0)
        self.assertEqual((self.stock.available_quantity, self.stock.loaned_quantity), (7, 3))
