from datetime import timedelta
from django.contrib.auth.models import User, Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from stockroom.models import Employee, Article, QuantityStock, QuantityIssue


class BajaTrabajadoresTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(employee_id="BAJA-1", first_name="Prueba", last_name="Baja")
        self.user = User.objects.create_user("almacen-baja", password="clave-ficticia", is_staff=True)
        self.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="stockroom", codename__in=[
                "change_employee", "view_employee", "view_quantityissue", "add_quantityreturn",
            ]))
        self.url = reverse("baja_trabajador_almacen")

    def test_sin_login_redirige(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_sin_permisos_denegado(self):
        outsider = User.objects.create_user("sin-permisos", password="clave-ficticia")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_sin_herramientas_se_puede_desactivar(self):
        self.client.force_login(self.user)
        result = self.client.post(self.url, {"empleado": self.employee.pk, "confirmacion": "BAJA"})
        self.assertEqual(result.status_code, 302)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)

    def test_requiere_confirmacion_literal(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {"empleado": self.employee.pk, "confirmacion": "SI"})
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_stock_inicial_viejo_impide_baja_y_no_cambia_saldos(self):
        article = Article.objects.create(article_code="BAJA-MART", name="Martillo", tracking_mode="quantity", return_mode="returnable")
        stock = QuantityStock.objects.create(article=article, available_quantity=5, loaned_quantity=1)
        issue = QuantityIssue.objects.create(employee=self.employee, stock=stock, quantity=1,
                                            requires_return=True, is_initial_stock=True,
                                            issued_at=timezone.now()-timedelta(days=80))
        self.client.force_login(self.user)
        res = self.client.post(self.url, {"empleado": self.employee.pk, "confirmacion": "BAJA"})
        self.assertEqual(res.status_code, 302)
        self.employee.refresh_from_db()
        stock.refresh_from_db()
        self.assertTrue(self.employee.is_active)
        self.assertEqual((stock.available_quantity, stock.loaned_quantity), (5, 1))
        self.assertEqual(QuantityIssue.objects.count(), 1)
        self.assertTrue(QuantityIssue.objects.filter(pk=issue.pk).exists())

    def test_prestamo_normal_impide_baja(self):
        article = Article.objects.create(article_code="BAJA-VERN", name="Vernier", tracking_mode="quantity", return_mode="returnable")
        stock = QuantityStock.objects.create(article=article, available_quantity=0, loaned_quantity=1)
        QuantityIssue.objects.create(employee=self.employee, stock=stock, quantity=1, requires_return=True)
        self.client.force_login(self.user)
        self.client.post(self.url, {"empleado": self.employee.pk, "confirmacion": "BAJA"})
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_consulta_no_mueve_existencias(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url, {"empleado": self.employee.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sin herramientas pendientes")
        self.employee.refresh_from_db()
        self.assertTrue(self.employee.is_active)

    def test_no_puede_desactivar_dos_veces(self):
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])
        self.client.force_login(self.user)
        response = self.client.post(self.url, {"empleado": self.employee.pk, "confirmacion": "BAJA"})
        self.assertEqual(response.status_code, 302)
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.is_active)
