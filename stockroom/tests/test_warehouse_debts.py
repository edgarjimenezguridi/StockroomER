
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from stockroom.models import (
    Article,
    Employee,
    QuantityIssue,
    QuantityReturn,
    QuantityStock,
)

from stockroom.services import (
    register_quantity_issue,
    register_quantity_return,
    register_return_and_exchange,
)


class WarehouseDebtsTests(TestCase):

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="almacenista_adeudos",
            password="PruebaSegura123!",
            is_staff=True,
        )

        permissions = Permission.objects.filter(
            content_type__app_label="stockroom",
            codename__in=[
                "view_employee",
                "view_quantityissue",
            ],
        )

        self.user.user_permissions.add(*permissions)
        self.client.force_login(self.user)

        self.employee = Employee.objects.create(
            employee_id="TEST-ADEUDOS",
            first_name="Ana",
            last_name="Prueba",
        )

        self.article = Article.objects.create(
            article_code="TEST-ADEUDOS-ART",
            name="Herramienta retornable",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )

        self.stock = QuantityStock.objects.create(
            article=self.article,
            available_quantity=20,
        )

        self.url = reverse("adeudos_almacen")

    def crear_entrega(self, quantity):
        return register_quantity_issue(
            QuantityIssue(
                stock=self.stock,
                employee=self.employee,
                quantity=quantity,
            )
        )

    def devolver(self, issue, quantity):
        return register_quantity_return(
            QuantityReturn(
                issue=issue,
                quantity=quantity,
                condition=QuantityReturn.Condition.GOOD,
            )
        )

    def test_devolucion_parcial_muestra_adeudo_correcto(self):
        issue = self.crear_entrega(10)
        self.devolver(issue, 6)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_piezas"], 4)
        self.assertEqual(response.context["total_entregas"], 1)

        entregas = list(response.context["entregas"])

        self.assertEqual(len(entregas), 1)
        self.assertEqual(entregas[0].pk, issue.pk)
        self.assertEqual(entregas[0].pending_quantity, 4)

    def test_entrega_completamente_devuelta_desaparece(self):
        issue = self.crear_entrega(5)
        self.devolver(issue, 5)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_piezas"], 0)
        self.assertEqual(response.context["total_entregas"], 0)

        self.assertEqual(
            list(response.context["entregas"]),
            [],
        )

        # La entrega permanece en la base de datos
        # para conservar el historial.
        self.assertTrue(
            QuantityIssue.objects.filter(pk=issue.pk).exists()
        )

    def test_cambio_muestra_adeudos_sin_duplicarlos(self):
        original = self.crear_entrega(4)

        damaged_return = QuantityReturn(
            issue=original,
            quantity=2,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Daño durante el uso",
        )

        replacement = register_return_and_exchange(
            damaged_return
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)

        # Original: 4 entregadas - 2 devueltas = 2.
        # Reemplazo: 2 entregadas - 0 devueltas = 2.
        # Adeudo total: 4 piezas.
        self.assertEqual(response.context["total_piezas"], 4)
        self.assertEqual(response.context["total_entregas"], 2)

        entregas = {
            item.pk: item.pending_quantity
            for item in response.context["entregas"]
        }

        self.assertEqual(entregas[original.pk], 2)
        self.assertEqual(entregas[replacement.pk], 2)

    def test_busqueda_por_trabajador_filtra_adeudos(self):
        self.crear_entrega(3)

        otro = Employee.objects.create(
            employee_id="TEST-OTRO",
            first_name="Luis",
            last_name="Prueba",
        )

        register_quantity_issue(
            QuantityIssue(
                stock=self.stock,
                employee=otro,
                quantity=2,
            )
        )

        response = self.client.get(
            self.url,
            {"employee_id": self.employee.employee_id},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total_piezas"], 3)
        self.assertEqual(response.context["total_entregas"], 1)
