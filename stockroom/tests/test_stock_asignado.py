from datetime import timedelta
from unittest import skipUnless
from importlib.util import find_spec

from django.contrib.auth.models import Permission, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stockroom.assigned_stock_views import _data
from stockroom.models import Article, Employee, QuantityIssue, QuantityStock


class StockAsignadoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("almacen-resguardos", password="ejemplo-no-real", is_staff=True)
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="stockroom", codename__in=[
                "view_employee", "view_quantityissue", "view_materialrequest", "add_quantityreturn"
            ]
        ))
        self.employee = Employee.objects.create(employee_id="PR-100", first_name="Trabajador", last_name="Resguardo")
        self.article = Article.objects.create(article_code="PR-HERR", name="Herramienta demo",
            tracking_mode=Article.TrackingMode.QUANTITY, return_mode=Article.ReturnMode.RETURNABLE)
        self.stock = QuantityStock.objects.create(article=self.article, available_quantity=3, loaned_quantity=2)
        self.issue = QuantityIssue.objects.create(employee=self.employee, stock=self.stock, quantity=2,
            returned_quantity=0, requires_return=True, is_initial_stock=True,
            issued_at=timezone.now() - timedelta(days=40))

    def test_stock_inicial_no_vence_y_se_muestra(self):
        rows = _data(self.employee)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["pending"], 2)
        self.assertIsNone(rows[0]["deadline"])
        self.assertEqual(rows[0]["status"], "stock_inicial")

    def test_prestamo_normal_muestra_vencimiento(self):
        other = Article.objects.create(article_code="PR-OTRA", name="Otra herramienta",
            tracking_mode=Article.TrackingMode.QUANTITY, return_mode=Article.ReturnMode.RETURNABLE)
        stock = QuantityStock.objects.create(article=other, available_quantity=0, loaned_quantity=1)
        QuantityIssue.objects.create(employee=self.employee, stock=stock, quantity=1, requires_return=True,
            is_initial_stock=False, issued_at=timezone.now() - timedelta(days=20))
        rows = _data(self.employee)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["status"] for r in rows if not r["issue"].is_initial_stock], ["vencido"])

    def test_sin_login_redirige(self):
        response = self.client.get(reverse("stock_asignado_almacen"))
        self.assertEqual(response.status_code, 302)

    def test_no_staff_denegado(self):
        otro = User.objects.create_user("externo-resguardo", password="ejemplo-no-real")
        self.client.force_login(otro)
        self.assertEqual(self.client.get(reverse("stock_asignado_almacen")).status_code, 403)
        self.assertEqual(self.client.get(reverse("resguardo_stock_pdf_almacen", args=[self.employee.pk])).status_code, 403)

    def test_consulta_autorizada_y_filtro(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("stock_asignado_almacen"), {"empleado": self.employee.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin vencimiento")
        self.assertContains(response, "PR-HERR")
        self.assertContains(response, reverse("registrar_devolucion_almacen", args=[self.issue.pk]))
        self.assertEqual(self.client.get(reverse("stock_asignado_almacen"), {"q":"Resguardo"}).status_code, 200)

    def test_consulta_no_modifica_inventario(self):
        self.client.force_login(self.user)
        before = (self.stock.available_quantity, self.stock.loaned_quantity, QuantityIssue.objects.count())
        self.client.get(reverse("stock_asignado_almacen"), {"empleado": self.employee.pk})
        self.stock.refresh_from_db()
        self.assertEqual(before, (self.stock.available_quantity, self.stock.loaned_quantity, QuantityIssue.objects.count()))

    @skipUnless(find_spec("reportlab") is not None, "ReportLab no instalado")
    def test_pdf_resguardo_valido_y_sin_mutaciones(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("resguardo_stock_pdf_almacen", args=[self.employee.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(QuantityIssue.objects.count(), 1)
