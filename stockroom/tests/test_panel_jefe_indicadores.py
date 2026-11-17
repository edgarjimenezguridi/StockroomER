
"""Pruebas de los indicadores operativos de jefatura."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
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
)


class PanelJefeIndicadoresTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_user(
            username="jefe_kpis_20a",
            password="ClaveTemporal123!",
            is_staff=True,
        )
        cls.jefe.groups.add(
            Group.objects.get_or_create(name="Jefes")[0]
        )

        cls.otro_usuario = User.objects.create_user(
            username="usuario_kpis_20a",
            password="ClaveTemporal123!",
            is_staff=True,
        )

    def test_jefe_consulta_indicadores(self):
        self.client.force_login(self.jefe)

        response = self.client.get(reverse("panel_jefe"))

        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context["solicitudes_activas"], 0)
        self.assertEqual(response.context["piezas_pendientes"], 0)
        self.assertEqual(response.context["danos_sin_resolver"], 0)

        self.assertContains(
            response,
            "Piezas pendientes de devolución",
        )

    def test_usuario_sin_permiso_no_puede_ver_indicadores(self):
        self.client.force_login(self.otro_usuario)

        response = self.client.get(reverse("panel_jefe"))

        self.assertEqual(response.status_code, 403)
    
    def test_panel_muestra_dashboard_ejecutivo(self):
        self.client.force_login(self.jefe)

        response = self.client.get(
            reverse("panel_jefe")
        )

        self.assertEqual(response.status_code, 200)

        self.assertContains(response, "Resumen ejecutivo")
        self.assertContains(response, "Trabajadores activos")
        self.assertContains(response, "Artículos activos")
        self.assertContains(response, "Piezas desechadas")
        self.assertContains(response, "Operación del almacén")

    def test_dashboard_respeta_filtro_de_periodo(self):
        self.client.force_login(self.jefe)

        for periodo in ("7", "30", "90", "todo"):
            with self.subTest(periodo=periodo):
                response = self.client.get(
                    reverse("panel_jefe"),
                    {"periodo": periodo},
                )

                self.assertEqual(response.status_code, 200)

                self.assertContains(
                    response,
                    f'value="{periodo}" selected',
                )
    
    def test_centro_alertas_sin_pendientes(self):
        self.client.force_login(self.jefe)

        response = self.client.get(reverse("panel_jefe"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Centro de alertas")
        self.assertContains(
            response,
            "Sin alertas operativas pendientes",
        )

    def test_alertas_con_prestamo_y_dano_real(self):
        empleado = Employee.objects.create(
            employee_id="ALERTA-20C",
            first_name="Prueba",
            last_name="Alertas",
        )

        articulo = Article.objects.create(
            article_code="ART-ALERTA-20C",
            name="Herramienta de prueba",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )

        stock = QuantityStock.objects.create(
            article=articulo,
            available_quantity=3,
        )

        entrega = QuantityIssue(
            stock=stock,
            employee=empleado,
            quantity=2,
        )
        register_quantity_issue(entrega)

        devolucion = QuantityReturn(
            issue=entrega,
            quantity=1,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Daño de prueba",
        )
        register_quantity_return(devolucion)

        self.client.force_login(self.jefe)
        response = self.client.get(reverse("panel_jefe"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["piezas_pendientes"], 1)
        self.assertEqual(response.context["danos_sin_resolver"], 1)

        self.assertContains(
            response,
            "Daños pendientes de resolución",
        )
        self.assertContains(
            response,
            "Piezas pendientes de devolución",
        )
        self.assertNotContains(
            response,
            "Sin alertas operativas pendientes",
        )


