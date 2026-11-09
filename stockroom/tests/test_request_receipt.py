from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.test import TestCase

from stockroom.fulfillment import (
    prepare_request_line,
    finish_request_preparation,
    confirm_request_receipt,
)
from stockroom.models import (
    Article,
    Employee,
    EmployeeCredential,
    MaterialRequest,
    MaterialRequestLine,
    QuantityIssue,
    QuantityStock,
)


class RequestReceiptTests(TestCase):
    def test_partial_receipt_cannot_be_confirmed_twice(self):
        operator = get_user_model().objects.create_superuser(
            username="almacen_prueba",
            password="solo-para-prueba",
        )
        employee = Employee.objects.create(
            employee_id="TEST-REC",
            first_name="Trabajador",
            last_name="De prueba",
        )
        credential = EmployeeCredential.objects.create(
            employee=employee,
            pin_hash=make_password("012345"),
        )
        article = Article.objects.create(
            article_code="TEST-MACHUELO",
            name="Machuelo de prueba",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        stock = QuantityStock.objects.create(
            article=article,
            available_quantity=10,
        )
        request = MaterialRequest.objects.create(
            employee=employee,
            status=MaterialRequest.Status.SUBMITTED,
        )
        line = MaterialRequestLine.objects.create(
            request=request,
            article=article,
            requested_quantity=5,
        )

        prepare_request_line(
            line_id=line.pk,
            quantity=3,
            operator=operator,
        )
        finish_request_preparation(
            request_id=request.pk,
            operator=operator,
        )

        # Preparar todavía no entrega ni descuenta piezas.
        stock.refresh_from_db()
        self.assertEqual(stock.available_quantity, 10)
        self.assertEqual(stock.loaned_quantity, 0)
        self.assertEqual(QuantityIssue.objects.count(), 0)

        confirm_request_receipt(
            request_id=request.pk,
            employee_id=employee.pk,
            credential_id=credential.pk,
            pin="012345",
        )

        request.refresh_from_db()
        line.refresh_from_db()
        stock.refresh_from_db()
        issue = QuantityIssue.objects.get(request_line=line)

        self.assertEqual(request.status, MaterialRequest.Status.CLOSED)
        self.assertIsNotNone(request.closed_at)
        self.assertEqual(line.requested_quantity, 5)
        self.assertEqual(line.prepared_quantity, 3)
        self.assertEqual(issue.quantity, 3)
        self.assertEqual(issue.returned_quantity, 0)
        self.assertTrue(issue.requires_return)
        self.assertEqual(issue.employee_id, employee.pk)
        self.assertEqual(stock.available_quantity, 7)
        self.assertEqual(stock.loaned_quantity, 3)

        # Repetir la confirmación debe rechazarse.
        with self.assertRaises(ValidationError):
            confirm_request_receipt(
                request_id=request.pk,
                employee_id=employee.pk,
                credential_id=credential.pk,
                pin="012345",
            )

        stock.refresh_from_db()
        self.assertEqual(QuantityIssue.objects.count(), 1)
        self.assertEqual(stock.available_quantity, 7)
        self.assertEqual(stock.loaned_quantity, 3)
        
    def crear_solicitud_preparada(self):
        employee = Employee.objects.create(
            employee_id="TEST-FAIL",
            first_name="Trabajador",
            last_name="De prueba",
        )
        credential = EmployeeCredential.objects.create(
            employee=employee,
            pin_hash=make_password("012345"),
        )
        request = MaterialRequest.objects.create(
            employee=employee,
            status=MaterialRequest.Status.PREPARED,
        )

        stocks = []
        for number in (1, 2):
            article = Article.objects.create(
                article_code=f"TEST-ART-{number}",
                name=f"Artículo de prueba {number}",
                tracking_mode=Article.TrackingMode.QUANTITY,
                return_mode=Article.ReturnMode.RETURNABLE,
            )
            stock = QuantityStock.objects.create(
                article=article,
                available_quantity=5,
            )
            MaterialRequestLine.objects.create(
                request=request,
                article=article,
                requested_quantity=2,
                prepared_quantity=2,
            )
            stocks.append(stock)

        return employee, credential, request, stocks

    def test_wrong_pin_does_not_create_deliveries(self):
        employee, credential, request, stocks = (
            self.crear_solicitud_preparada()
        )

        with self.assertRaisesMessage(ValidationError, "NIP incorrecto"):
            confirm_request_receipt(
                request_id=request.pk,
                employee_id=employee.pk,
                credential_id=credential.pk,
                pin="999999",
            )

        credential.refresh_from_db()
        request.refresh_from_db()

        self.assertEqual(credential.failed_pin_attempts, 1)
        self.assertEqual(request.status, MaterialRequest.Status.PREPARED)
        self.assertIsNone(request.closed_at)
        self.assertEqual(QuantityIssue.objects.count(), 0)

        for stock in stocks:
            stock.refresh_from_db()
            self.assertEqual(stock.available_quantity, 5)
            self.assertEqual(stock.loaned_quantity, 0)

    def test_shortage_rolls_back_the_entire_request(self):
        employee, credential, request, stocks = (
            self.crear_solicitud_preparada()
        )

        # Simulamos que el segundo artículo ya no alcanza.
        QuantityStock.objects.filter(pk=stocks[1].pk).update(
            available_quantity=1,
        )

        with self.assertRaises(ValidationError):
            confirm_request_receipt(
                request_id=request.pk,
                employee_id=employee.pk,
                credential_id=credential.pk,
                pin="012345",
            )

        request.refresh_from_db()
        self.assertEqual(request.status, MaterialRequest.Status.PREPARED)
        self.assertIsNone(request.closed_at)
        self.assertEqual(QuantityIssue.objects.count(), 0)

        stocks[0].refresh_from_db()
        stocks[1].refresh_from_db()

        # Tampoco debe quedar descontado el primer artículo.
        self.assertEqual(stocks[0].available_quantity, 5)
        self.assertEqual(stocks[0].loaned_quantity, 0)
        self.assertEqual(stocks[1].available_quantity, 1)
        self.assertEqual(stocks[1].loaned_quantity, 0)