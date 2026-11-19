"""Fase 23Y: ciclo de vida de piezas individuales en base temporal de Django."""
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
    Article, DamageResolution, Employee, EmployeeCredential,
    MaterialRequest, MaterialRequestLine, QuantityIssue, QuantityReturn, Tool,
)
from stockroom.services import (
    register_damage_resolution, register_quantity_issue,
    register_quantity_return,
)


class CicloPiezasIndividuales23YTests(TestCase):
    def setUp(self):
        self.operador = get_user_model().objects.create_superuser(
            username="almacen_23y", password="ClaveTemporal23Y!"
        )
        self.trabajador = Employee.objects.create(
            employee_id="TRAB-23Y-01", first_name="Trabajador", last_name="Uno"
        )
        self.otro = Employee.objects.create(
            employee_id="TRAB-23Y-02", first_name="Trabajador", last_name="Dos"
        )
        self.credencial = EmployeeCredential.objects.create(
            employee=self.trabajador, pin_hash=make_password("012345")
        )
        self.articulo = Article.objects.create(
            article_code="ART-23Y-001", name="Vernier de integración",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.pieza = Tool.objects.create(
            article=self.articulo, tool_code="PIEZA-23Y-001", name="Vernier individual"
        )
        self.solicitud = MaterialRequest.objects.create(
            employee=self.trabajador, status=MaterialRequest.Status.SUBMITTED
        )
        self.linea = MaterialRequestLine.objects.create(
            request=self.solicitud, article=self.articulo, requested_quantity=1
        )

    def preparar(self):
        prepare_request_line(
            line_id=self.linea.pk, quantity=1, operator=self.operador,
            tool_ids=[self.pieza.pk],
        )
        finish_request_preparation(
            request_id=self.solicitud.pk, operator=self.operador
        )
        self.solicitud.refresh_from_db()
        self.pieza.refresh_from_db()

    def confirmar(self, pin="012345", version=None):
        return confirm_request_receipt(
            request_id=self.solicitud.pk,
            employee_id=self.trabajador.pk,
            credential_id=self.credencial.pk,
            pin=pin,
            expected_version=(
                self.solicitud.preparation_version if version is None else version
            ),
        )

    def entregar(self):
        self.preparar()
        self.confirmar()
        self.pieza.refresh_from_db()
        return QuantityIssue.objects.get(request_line=self.linea)

    def devolver(self, issue, condition=QuantityReturn.Condition.GOOD):
        return register_quantity_return(QuantityReturn(
            issue=issue, quantity=1, condition=condition,
            reason="Revisión de prueba" if condition == QuantityReturn.Condition.DAMAGED else "",
        ))

    def test_preparar_y_nip_incorrecto_no_prestan_la_pieza(self):
        self.preparar()
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.AVAILABLE)
        self.assertFalse(QuantityIssue.objects.exists())
        with self.assertRaises(ValidationError):
            self.confirmar(pin="999999")
        self.pieza.refresh_from_db()
        self.solicitud.refresh_from_db()
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.AVAILABLE)
        self.assertEqual(self.solicitud.status, MaterialRequest.Status.PREPARED)
        self.assertFalse(QuantityIssue.objects.exists())

    def test_nip_correcto_entrega_exactamente_una_pieza(self):
        issue = self.entregar()
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.status, MaterialRequest.Status.CLOSED)
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.LOANED)
        self.assertEqual(issue.tool_id, self.pieza.pk)
        self.assertEqual(issue.employee_id, self.trabajador.pk)
        self.assertTrue(issue.requires_return)
        self.assertEqual(QuantityIssue.objects.count(), 1)

    def test_pieza_prestada_no_puede_entregarse_a_otro_trabajador(self):
        self.entregar()
        with self.assertRaises(ValidationError):
            register_quantity_issue(QuantityIssue(
                tool=self.pieza, employee=self.otro, quantity=1
            ))
        self.pieza.refresh_from_db()
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.LOANED)
        self.assertEqual(QuantityIssue.objects.count(), 1)

    def test_devolucion_buena_permite_nueva_entrega(self):
        issue = self.entregar()
        self.devolver(issue)
        self.pieza.refresh_from_db()
        issue.refresh_from_db()
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.AVAILABLE)
        self.assertEqual(issue.returned_quantity, 1)
        nueva = register_quantity_issue(QuantityIssue(
            tool=self.pieza, employee=self.otro, quantity=1
        ))
        self.pieza.refresh_from_db()
        self.assertEqual(nueva.employee_id, self.otro.pk)
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.LOANED)
        self.assertEqual(QuantityIssue.objects.count(), 2)

    def test_segunda_devolucion_es_rechazada_sin_cambiar_estado(self):
        issue = self.entregar()
        self.devolver(issue)
        with self.assertRaises(ValidationError):
            self.devolver(issue)
        issue.refresh_from_db()
        self.pieza.refresh_from_db()
        self.assertEqual(issue.returned_quantity, 1)
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.AVAILABLE)
        self.assertEqual(QuantityReturn.objects.count(), 1)

    def test_pieza_danada_en_cuarentena_no_se_presta(self):
        issue = self.entregar()
        self.devolver(issue, QuantityReturn.Condition.DAMAGED)
        self.pieza.refresh_from_db()
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.QUARANTINE)
        with self.assertRaises(ValidationError):
            register_quantity_issue(QuantityIssue(
                tool=self.pieza, employee=self.otro, quantity=1
            ))
        self.assertEqual(QuantityIssue.objects.count(), 1)

    def test_reparacion_registrada_libera_pieza_para_nueva_entrega(self):
        issue = self.entregar()
        retorno = self.devolver(issue, QuantityReturn.Condition.DAMAGED)
        register_damage_resolution(DamageResolution(
            source_return=retorno, quantity=1,
            outcome=DamageResolution.Outcome.RESTORED,
            reason="Reparación verificada en prueba",
        ))
        self.pieza.refresh_from_db()
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.AVAILABLE)
        nueva = register_quantity_issue(QuantityIssue(
            tool=self.pieza, employee=self.otro, quantity=1
        ))
        self.assertIsNotNone(nueva.pk)
        self.pieza.refresh_from_db()
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.LOANED)

    def test_baja_definitiva_bloquea_nuevas_entregas(self):
        issue = self.entregar()
        retorno = self.devolver(issue, QuantityReturn.Condition.DAMAGED)
        register_damage_resolution(DamageResolution(
            source_return=retorno, quantity=1,
            outcome=DamageResolution.Outcome.SCRAPPED,
            reason="Pieza irrecuperable en prueba",
        ))
        self.pieza.refresh_from_db()
        self.assertEqual(self.pieza.inventory_status, Tool.InventoryStatus.SCRAPPED)
        self.assertFalse(self.pieza.is_active)
        with self.assertRaises(ValidationError):
            register_quantity_issue(QuantityIssue(
                tool=self.pieza, employee=self.otro, quantity=1
            ))
        self.assertEqual(QuantityIssue.objects.count(), 1)
