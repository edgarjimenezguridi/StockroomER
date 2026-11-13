from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError, PermissionDenied
from django.test import TestCase
from django.urls import reverse
from stockroom.initial_stock_views import registrar_stock_inicial
from stockroom.loan_rules import motivo_duplicado
from stockroom.models import Employee, Article, QuantityStock, QuantityIssue, Tool


class AsignacionInicialTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="almacen-fase15", password="test-123", is_staff=True)
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="stockroom", codename__in=[
                "add_quantityissue", "view_employee", "view_materialrequest",
            ]
        ))
        self.worker = Employee.objects.create(employee_id="F15-EMP", first_name="Prueba", last_name="Inicial")
        self.article = Article.objects.create(
            article_code="F15-MART", name="Martillo de prueba",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.stock = QuantityStock.objects.create(article=self.article, available_quantity=4)

    def asignar(self, **kw):
        args = dict(employee_id=self.worker.pk, article_id=self.article.pk, quantity=2, user=self.user)
        args.update(kw)
        return registrar_stock_inicial(**args)

    def test_descuenta_y_marca_como_inicial(self):
        issue = self.asignar()
        self.stock.refresh_from_db()
        self.assertTrue(issue.is_initial_stock)
        self.assertTrue(issue.requires_return)
        self.assertEqual((self.stock.available_quantity, self.stock.loaned_quantity), (2, 2))
        self.assertIsNotNone(motivo_duplicado(employee_id=self.worker.pk, article_id=self.article.pk))

    def test_impide_duplicado_y_no_hace_segunda_salida(self):
        self.asignar()
        with self.assertRaises(ValidationError): self.asignar()
        self.assertEqual(QuantityIssue.objects.count(), 1)

    def test_rechaza_salida_sin_existencias(self):
        with self.assertRaises(ValidationError): self.asignar(quantity=8)
        self.stock.refresh_from_db()
        self.assertEqual(self.stock.available_quantity, 4)
        self.assertFalse(QuantityIssue.objects.exists())

    def test_solo_personal_autorizado(self):
        otro = User.objects.create_user(username="no-autorizado", password="test-123")
        with self.assertRaises(PermissionDenied): self.asignar(user=otro)

    def test_vista_exige_autenticacion(self):
        res = self.client.get(reverse("asignar_stock_inicial_almacen"))
        self.assertEqual(res.status_code, 302)

    def test_vista_autorizada(self):
        self.client.force_login(self.user)
        res = self.client.get(reverse("asignar_stock_inicial_almacen"))
        self.assertEqual(res.status_code, 200)

    def test_vista_asigna_por_post(self):
        self.client.force_login(self.user)
        res = self.client.post(reverse("asignar_stock_inicial_almacen"), {
            "employee":self.worker.pk, "article":self.article.pk, "quantity":1, "tool":"",
        })
        self.assertEqual(res.status_code, 302)
        self.assertEqual(QuantityIssue.objects.filter(is_initial_stock=True).count(),1)

    def test_pieza_individual(self):
        a = Article.objects.create(article_code="F15-IND", name="Vernier",
                                   tracking_mode=Article.TrackingMode.INDIVIDUAL,
                                   return_mode=Article.ReturnMode.RETURNABLE)
        t = Tool.objects.create(article=a, tool_code="F15-T1", name="Vernier")
        issue = self.asignar(article_id=a.pk, quantity=1, tool_id=t.pk)
        t.refresh_from_db()
        self.assertTrue(issue.is_initial_stock)
        self.assertEqual(t.inventory_status, Tool.InventoryStatus.LOANED)
