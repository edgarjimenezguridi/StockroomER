"""Fase 23I: selectors remotos sin catálogos precargados y sin movimientos."""
from pathlib import Path
from django.test import TestCase, SimpleTestCase
from django.conf import settings
from stockroom.models import Article, Employee, QuantityStock, StockEntry
from stockroom.warehouse_forms import WarehouseStockEntryForm, WarehouseStockCorrectionForm
from stockroom.initial_stock_views import InitialStockForm

class IntegracionRemotaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empleado = Employee.objects.create(employee_id="LOOK23I", first_name="Prueba", last_name="Remota")
        cls.articulo = Article.objects.create(article_code="LOOK23I", name="Broca de prueba", is_active=True,
            tracking_mode=Article.TrackingMode.QUANTITY, return_mode=Article.ReturnMode.RETURNABLE)
        cls.stock = QuantityStock.objects.create(article=cls.articulo, available_quantity=2)
        cls.entrada = StockEntry.objects.create(stock=cls.stock, quantity=2)

    def test_get_no_carga_catalogos_completos(self):
        self.assertFalse(WarehouseStockEntryForm().fields["stock"].queryset.exists())
        self.assertFalse(WarehouseStockCorrectionForm().fields["entry"].queryset.exists())
        form = InitialStockForm()
        for campo in ("employee", "article", "tool"):
            self.assertFalse(form.fields[campo].queryset.exists())
            self.assertTrue(form.fields[campo].widget.attrs["data-sr-lookup-type"])

    def test_entrada_post_acepta_solo_stock_valido(self):
        valido = WarehouseStockEntryForm(data={"stock": self.stock.pk, "quantity": 1})
        self.assertTrue(valido.is_valid(), valido.errors)
        self.assertFalse(WarehouseStockEntryForm(data={"stock": 999999, "quantity": 1}).is_valid())

    def test_correccion_post_valida_entrada(self):
        valido = WarehouseStockCorrectionForm(data={"entry": self.entrada.pk, "quantity_delta": 1, "reason": "Prueba"})
        self.assertTrue(valido.is_valid(), valido.errors)
        self.assertFalse(WarehouseStockCorrectionForm(data={"entry": 999999, "quantity_delta": 1, "reason": "Prueba"}).is_valid())

    def test_stock_inicial_valida_eleccion_y_no_mueve_inventario(self):
        form = InitialStockForm(data={"employee": self.empleado.pk, "article": self.articulo.pk, "quantity": 1, "tool": ""})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertFalse(InitialStockForm(data={"employee": 999999, "article": self.articulo.pk, "quantity": 1}).is_valid())
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.available_quantity, 2)

class IntegracionArchivosTests(SimpleTestCase):
    def test_templates_conectan_api_js(self):
        base = Path(settings.BASE_DIR) / "stockroom/templates/stockroom/almacen"
        for nombre in ("registrar_entrada_almacen.html", "corregir_existencia_almacen.html", "asignar_stock_inicial.html"):
            with self.subTest(nombre=nombre):
                source = (base / nombre).read_text(encoding="utf-8")
                self.assertIn("data-api-url", source)
                self.assertIn("'buscar_almacen'", source)
    def test_js_consulta_sin_enviar_formulario(self):
        script = (Path(settings.BASE_DIR) / "stockroom/static/stockroom/js/busqueda_escaneo.js").read_text(encoding="utf-8")
        self.assertIn("fetch(", script)
        self.assertIn('method: "GET"', script)
        self.assertNotIn(".submit(", script)
