"""Fase 23X: seguridad del servidor al preparar piezas individuales.

Ejecutar con manage.py test; Django crea una base de datos temporal.
No hay operaciones contra el inventario del taller.
"""
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from stockroom.fulfillment import prepare_request_line
from stockroom.models import (
    Article, Employee, MaterialRequest, MaterialRequestLine,
    MaterialRequestPiece, Tool,
)


class SeguridadPreparacionIndividual23XTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.operator = get_user_model().objects.create_superuser(
            username="almacen_23x", password="PruebaSegura23X!"
        )
        cls.employee = Employee.objects.create(
            employee_id="TRAB-23X", first_name="Prueba", last_name="Inventario"
        )
        cls.article = Article.objects.create(
            article_code="ART-23X-A", name="Herramienta individual A",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        cls.other_article = Article.objects.create(
            article_code="ART-23X-B", name="Herramienta individual B",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        cls.tool_one = Tool.objects.create(
            article=cls.article, tool_code="TOOL-23X-01", name="Pieza uno",
        )
        cls.tool_two = Tool.objects.create(
            article=cls.article, tool_code="TOOL-23X-02", name="Pieza dos",
        )
        cls.loaned = Tool.objects.create(
            article=cls.article, tool_code="TOOL-23X-03", name="Pieza prestada",
            inventory_status=Tool.InventoryStatus.LOANED,
        )
        cls.other_tool = Tool.objects.create(
            article=cls.other_article, tool_code="TOOL-23X-B1", name="Otra pieza",
        )
        cls.request = MaterialRequest.objects.create(
            employee=cls.employee, status=MaterialRequest.Status.SUBMITTED,
        )
        cls.line = MaterialRequestLine.objects.create(
            request=cls.request, article=cls.article, requested_quantity=2,
        )

    def preparar(self, quantity, tools):
        return prepare_request_line(
            line_id=self.line.pk, quantity=quantity,
            operator=self.operator, tool_ids=tools,
        )

    def afirmar_sin_cambios(self):
        self.line.refresh_from_db()
        self.assertEqual(self.line.prepared_quantity, 0)
        self.assertFalse(MaterialRequestPiece.objects.filter(line=self.line).exists())
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, MaterialRequest.Status.SUBMITTED)

    def test_prepara_dos_piezas_correctas_sin_entregar(self):
        self.preparar(2, [self.tool_one.pk, self.tool_two.pk])
        self.line.refresh_from_db()
        self.assertEqual(self.line.prepared_quantity, 2)
        self.assertSetEqual(
            set(self.line.selected_pieces.values_list("tool_id", flat=True)),
            {self.tool_one.pk, self.tool_two.pk},
        )
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, MaterialRequest.Status.SUBMITTED)
        for tool in (self.tool_one, self.tool_two):
            tool.refresh_from_db()
            self.assertEqual(tool.inventory_status, Tool.InventoryStatus.AVAILABLE)

    def test_cero_piezas_es_valido(self):
        self.preparar(0, [])
        self.afirmar_sin_cambios()

    def test_cantidad_no_coincide_con_piezas(self):
        with self.assertRaises(ValidationError):
            self.preparar(2, [self.tool_one.pk])
        self.afirmar_sin_cambios()

    def test_no_acepta_la_misma_pieza_dos_veces(self):
        with self.assertRaises(ValidationError):
            self.preparar(2, [self.tool_one.pk, self.tool_one.pk])
        self.afirmar_sin_cambios()

    def test_no_acepta_pieza_de_otro_articulo(self):
        with self.assertRaises(ValidationError):
            self.preparar(1, [self.other_tool.pk])
        self.afirmar_sin_cambios()

    def test_no_acepta_pieza_prestada(self):
        with self.assertRaises(ValidationError):
            self.preparar(1, [self.loaned.pk])
        self.afirmar_sin_cambios()

    def test_solicitud_ya_preparada_no_admite_cambios(self):
        self.request.status = MaterialRequest.Status.PREPARED
        self.request.save(update_fields=["status"])
        with self.assertRaises(ValidationError):
            self.preparar(1, [self.tool_one.pk])
        self.line.refresh_from_db()
        self.assertEqual(self.line.prepared_quantity, 0)
        self.assertFalse(self.line.selected_pieces.exists())

    def test_usuario_sin_permiso_no_prepara(self):
        from django.core.exceptions import PermissionDenied
        unauthorized = get_user_model().objects.create_user(
            username="sin_permiso_23x", password="PruebaSinPermiso23X!"
        )
        with self.assertRaises(PermissionDenied):
            prepare_request_line(
                line_id=self.line.pk, quantity=1,
                operator=unauthorized, tool_ids=[self.tool_one.pk],
            )
        self.afirmar_sin_cambios()
