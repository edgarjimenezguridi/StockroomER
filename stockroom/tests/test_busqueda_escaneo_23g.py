from django.test import SimpleTestCase, TestCase
from django.db.models import F
from stockroom.models import Article, Employee, QuantityStock, QuantityIssue
from stockroom.worker_exception_views import WorkerExceptionForm
from stockroom.initial_stock_views import InitialStockForm
from stockroom.warehouse_forms import WarehouseStockEntryForm, WarehouseStockCorrectionForm

class DuplicadoSoloAdeudosTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(employee_id="SCAN23-001", first_name="Trabajador", last_name="Prueba")
        self.otro = Employee.objects.create(employee_id="SCAN23-002", first_name="Otro", last_name="Prueba")
        self.adeudado = Article.objects.create(article_code="SCAN23-A", name="Vernier", tracking_mode=Article.TrackingMode.QUANTITY, return_mode=Article.ReturnMode.RETURNABLE)
        self.sin_deuda = Article.objects.create(article_code="SCAN23-B", name="Martillo", tracking_mode=Article.TrackingMode.QUANTITY, return_mode=Article.ReturnMode.RETURNABLE)
        self.stock = QuantityStock.objects.create(article=self.adeudado, available_quantity=0)
        self.issue = QuantityIssue.objects.create(employee=self.employee, stock=self.stock, quantity=2, returned_quantity=0, requires_return=True)

    def test_solo_articulos_adeudados(self):
        ids = set(WorkerExceptionForm(employee=self.employee).fields["article"].queryset.values_list("pk", flat=True))
        self.assertEqual(ids, {self.adeudado.pk})
        self.assertFalse(WorkerExceptionForm(employee=self.otro).fields["article"].queryset.exists())

    def test_devolucion_total_retira_opcion(self):
        self.issue.returned_quantity = 2
        self.issue.save(update_fields=["returned_quantity"])
        self.assertFalse(WorkerExceptionForm(employee=self.employee).fields["article"].queryset.exists())

    def test_post_no_acepta_articulo_sin_deuda(self):
        form = WorkerExceptionForm(data={"article":self.sin_deuda.pk,"max_quantity":1,"reason":"Necesito esta herramienta otra vez"}, employee=self.employee)
        self.assertFalse(form.is_valid())
        self.assertIn("article", form.errors)

class BusquedaAlmacenTests(SimpleTestCase):
    def test_campos_tienen_escaneo(self):
        self.assertEqual(InitialStockForm.base_fields["employee"].widget.attrs["data-sr-scan"], "1")
        self.assertEqual(InitialStockForm.base_fields["article"].widget.attrs["data-sr-scan"], "1")
        self.assertEqual(WarehouseStockEntryForm.base_fields["stock"].widget.attrs["data-sr-scan"], "1")
        self.assertEqual(WarehouseStockCorrectionForm.base_fields["entry"].widget.attrs["data-sr-scan"], "1")
