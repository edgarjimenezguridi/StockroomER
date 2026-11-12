
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from stockroom.models import (
    Article,
    Employee,
    QuantityIssue,
    QuantityReturn,
    Tool,
)


class WarehouseToolScanTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.almacenista = User.objects.create_superuser(
            username="test_escaneo_almacen",
            email="escaneo@example.com",
            password="ClaveTemporal123!",
        )

        cls.empleado = Employee.objects.create(
            employee_id="TEST-SCAN-001",
            first_name="Trabajador",
            last_name="Escaneo",
            is_active=True,
        )

        cls.articulo = Article.objects.create(
            article_code="TEST-SCAN-ART",
            name="Vernier de prueba",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
            is_active=True,
        )

        cls.pieza = Tool.objects.create(
            article=cls.articulo,
            tool_code="TEST-SCAN-TOOL",
            name="Vernier individual",
            inventory_status=Tool.InventoryStatus.LOANED,
            is_active=True,
        )

        cls.entrega = QuantityIssue.objects.create(
            tool=cls.pieza,
            employee=cls.empleado,
            quantity=1,
            returned_quantity=0,
            requires_return=True,
        )

    def setUp(self):
        self.client.force_login(self.almacenista)
        self.url = reverse("adeudos_almacen")

    def escanear(self, codigo):
        return self.client.get(
            self.url,
            {"scan": codigo},
        )

    def test_codigo_valido_abre_devolucion(self):
        respuesta = self.escanear("TEST-SCAN-TOOL")

        self.assertRedirects(
            respuesta,
            reverse(
                "registrar_devolucion_almacen",
                kwargs={"issue_id": self.entrega.pk},
            ),
        )

    def test_codigo_inexistente_no_abre_devolucion(self):
        respuesta = self.escanear("NO-EXISTE-999")

        self.assertRedirects(
            respuesta,
            self.url,
        )

        self.assertEqual(
            QuantityReturn.objects.count(),
            0,
        )

    def test_entrega_devuelta_no_se_puede_escanear(self):
        QuantityIssue.objects.filter(
            pk=self.entrega.pk,
        ).update(returned_quantity=1)

        respuesta = self.escanear("TEST-SCAN-TOOL")

        self.assertRedirects(
            respuesta,
            self.url,
        )

    def test_escaneo_no_modifica_inventario(self):
        respuesta = self.escanear("TEST-SCAN-TOOL")

        self.assertEqual(respuesta.status_code, 302)

        self.entrega.refresh_from_db()
        self.pieza.refresh_from_db()

        self.assertEqual(
            self.entrega.returned_quantity,
            0,
        )

        self.assertEqual(
            self.pieza.inventory_status,
            Tool.InventoryStatus.LOANED,
        )

        self.assertEqual(
            QuantityReturn.objects.count(),
            0,
        )

    def test_usuario_sin_permiso_no_puede_escanear(self):
        User = get_user_model()

        usuario = User.objects.create_user(
            username="test_escaneo_sin_devolucion",
            password="ClaveTemporal456!",
            is_staff=True,
        )

        permisos = Permission.objects.filter(
            content_type__app_label="stockroom",
            codename__in=[
                "view_employee",
                "view_quantityissue",
            ],
        )

        usuario.user_permissions.add(*permisos)
        self.client.force_login(usuario)

        respuesta = self.escanear("TEST-SCAN-TOOL")

        self.assertEqual(
            respuesta.status_code,
            403,
        )
