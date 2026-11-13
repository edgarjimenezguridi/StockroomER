from stockroom.worker_session_security import pin_session_version
"""Pruebas de integración: duplicado -> jefe -> comanda -> entrega y vencimiento.

Django crea una base de pruebas; ninguna operación toca el inventario real.
Solo se sustituye la comprobación criptográfica del NIP: se comprueba
por separado en las pruebas existentes de credenciales.
"""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stockroom.cart import set_cart_quantity, submit_cart
from stockroom.fulfillment import (
    confirm_request_receipt,
    finish_request_preparation,
    prepare_request_line,
)
from stockroom.loan_rules import tiene_adeudos_vencidos
from stockroom.models import (
    Article, DuplicateLoanAuthorization, Employee, EmployeeCredential,
    MaterialRequest, MaterialRequestLine, QuantityIssue, QuantityReturn,
    QuantityStock,
)
from stockroom.services import register_quantity_issue, register_quantity_return


class FlujoIntegralAutorizacionesTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            employee_id="INT-001", first_name="Prueba", last_name="Integral"
        )
        self.credential = EmployeeCredential.objects.create(
            employee=self.employee, pin_hash="hash-ficticio-para-prueba"
        )
        self.article = Article.objects.create(
            article_code="INT-M8", name="Machuelo M8",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.other_article = Article.objects.create(
            article_code="INT-M6", name="Machuelo M6",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.stock = QuantityStock.objects.create(
            article=self.article, available_quantity=8
        )
        QuantityStock.objects.create(article=self.other_article, available_quantity=5)

        User = get_user_model()
        self.boss = User.objects.create_user(
            username="int-jefe", password="no-usar", is_staff=True
        )
        self.boss.groups.add(Group.objects.get_or_create(name="Jefes")[0])
        self.operator = User.objects.create_user(
            username="int-almacenista", password="no-usar", is_staff=True
        )
        permission = Permission.objects.get(
            content_type__app_label="stockroom",
            codename="change_materialrequest",
        )
        self.operator.user_permissions.add(permission)

        # Entrega previa real, aún pendiente: provoca conflicto de duplicidad.
        self.original = register_quantity_issue(QuantityIssue(
            employee=self.employee, stock=self.stock, quantity=1,
        ))

    def entrar_como_trabajador(self):
        session = self.client.session
        session["worker_employee_id"] = self.employee.pk
        session["worker_credential_id"] = self.credential.pk
        session["worker_pin_version"] = pin_session_version(self.credential.pin_hash)
        session.save()

    def pedir_y_aprobar(self):
        self.entrar_como_trabajador()
        response = self.client.post(reverse("solicitar_duplicado_empleado"), {
            "article": self.article.pk,
            "max_quantity": 1,
            "reason": "Se requieren dos machuelos para trabajos simultáneos.",
        })
        self.assertEqual(response.status_code, 302)
        approval = DuplicateLoanAuthorization.objects.get(
            employee=self.employee, article=self.article,
        )
        self.assertEqual(approval.status, DuplicateLoanAuthorization.Status.PENDING)
        self.assertIsNone(approval.used_request_id)
        self.assertEqual(QuantityIssue.objects.count(), 1)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.available_quantity, 7)

        self.client.force_login(self.boss)
        response = self.client.post(
            reverse("resolver_autorizacion_jefe", args=[approval.pk]),
            {"decision": "approve"},
        )
        self.assertEqual(response.status_code, 302)
        approval.refresh_from_db()
        self.assertEqual(approval.status, DuplicateLoanAuthorization.Status.APPROVED)
        self.assertEqual(approval.decided_by_id, self.boss.pk)
        return approval

    def test_recorrido_completo_aprobacion_comanda_entrega_y_uso_unico(self):
        with self.assertRaises(ValidationError):
            set_cart_quantity(
                employee_id=self.employee.pk, article_id=self.article.pk, quantity=1
            )

        approval = self.pedir_y_aprobar()
        line = set_cart_quantity(
            employee_id=self.employee.pk, article_id=self.article.pk, quantity=1
        )
        request = submit_cart(employee_id=self.employee.pk, cart_id=line.request_id)
        self.assertEqual(request.status, MaterialRequest.Status.SUBMITTED)
        approval.refresh_from_db()
        self.assertEqual(approval.used_request_id, request.pk)
        # Generar la comanda no equivale a entregar inventario.
        self.assertEqual(QuantityIssue.objects.count(), 1)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.available_quantity, 7)

        # Una aprobación vinculada a la primera solicitud no sirve para otra.
        with self.assertRaises(ValidationError):
            set_cart_quantity(
                employee_id=self.employee.pk, article_id=self.article.pk, quantity=1
            )

        prepare_request_line(line_id=line.pk, quantity=1, operator=self.operator)
        prepared = finish_request_preparation(
            request_id=request.pk, operator=self.operator
        )
        self.assertEqual(prepared.status, MaterialRequest.Status.PREPARED)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.available_quantity, 7)

        # La validación del NIP está cubierta por pruebas de credenciales;
        # aquí probamos el servicio real de confirmación e inventario.
        with patch(
            "stockroom.fulfillment.verify_employee_pin", return_value=self.employee
        ) as verifier:
            closed = confirm_request_receipt(
                request_id=request.pk,
                employee_id=self.employee.pk,
                credential_id=self.credential.pk,
                pin="000000",
                expected_version=prepared.preparation_version,
            )
            verifier.assert_called_once()

        self.assertEqual(closed.status, MaterialRequest.Status.CLOSED)
        deliveries = QuantityIssue.objects.filter(request_line=line)
        self.assertEqual(deliveries.count(), 1)
        self.assertEqual(deliveries.get().quantity, 1)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.available_quantity, 6)
        self.assertEqual(self.stock.loaned_quantity, 2)
        approval.refresh_from_db()
        self.assertEqual(approval.used_request_id, request.pk)

        # No es posible confirmar dos veces y descontar otras piezas.
        with patch(
            "stockroom.fulfillment.verify_employee_pin", return_value=self.employee
        ):
            with self.assertRaises(ValidationError):
                confirm_request_receipt(
                    request_id=request.pk,
                    employee_id=self.employee.pk,
                    credential_id=self.credential.pk,
                    pin="000000",
                    expected_version=prepared.preparation_version,
                )
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.available_quantity, 6)
        self.assertEqual(deliveries.count(), 1)

    def test_vencimiento_bloquea_todos_los_articulos_y_devolucion_desbloquea(self):
        QuantityIssue.objects.filter(pk=self.original.pk).update(
            issued_at=timezone.now() - timedelta(days=16)
        )
        self.original.refresh_from_db()
        self.assertTrue(tiene_adeudos_vencidos(self.employee.pk))
        with self.assertRaises(ValidationError):
            set_cart_quantity(
                employee_id=self.employee.pk,
                article_id=self.other_article.pk,
                quantity=1,
            )
        # Una aprobación no elimina el bloqueo general.
        DuplicateLoanAuthorization.objects.create(
            employee=self.employee, article=self.article, max_quantity=1,
            reason="Prueba de excepción", status=DuplicateLoanAuthorization.Status.APPROVED,
        )
        with self.assertRaises(ValidationError):
            set_cart_quantity(
                employee_id=self.employee.pk,
                article_id=self.article.pk,
                quantity=1,
            )

        register_quantity_return(QuantityReturn(
            issue=self.original, quantity=1,
            condition=QuantityReturn.Condition.GOOD,
        ))
        self.assertFalse(tiene_adeudos_vencidos(self.employee.pk))
        line = set_cart_quantity(
            employee_id=self.employee.pk,
            article_id=self.other_article.pk,
            quantity=1,
        )
        self.assertEqual(line.article_id, self.other_article.pk)

    def test_rechazo_no_habilita_el_duplicado(self):
        self.entrar_como_trabajador()
        response = self.client.post(reverse("solicitar_duplicado_empleado"), {
            "article": self.article.pk, "max_quantity": 1,
            "reason": "Necesito dos piezas durante el mismo turno.",
        })
        self.assertEqual(response.status_code, 302)
        approval = DuplicateLoanAuthorization.objects.get()
        self.client.force_login(self.boss)
        self.client.post(
            reverse("resolver_autorizacion_jefe", args=[approval.pk]),
            {"decision": "reject"},
        )
        approval.refresh_from_db()
        self.assertEqual(approval.status, DuplicateLoanAuthorization.Status.REJECTED)
        with self.assertRaises(ValidationError):
            set_cart_quantity(
                employee_id=self.employee.pk, article_id=self.article.pk, quantity=1
            )
