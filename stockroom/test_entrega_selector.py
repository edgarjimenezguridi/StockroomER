from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Article, Employee, Loan, QuantityIssue, Tool


class EntregaSelectorTests(TestCase):
    def test_selector_solo_ofrece_piezas_libres(self):
        usuario = get_user_model().objects.create_superuser(
            username="admin_prueba",
            password="solo-para-prueba",
        )
        self.client.force_login(usuario)

        trabajador = Employee.objects.create(
            employee_id="TEST-001",
            first_name="Trabajador",
            last_name="De prueba",
        )
        articulo = Article.objects.create(
            article_code="TEST-VERNIER",
            name="Vernier de prueba",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
        )

        def crear_pieza(codigo):
            return Tool.objects.create(
                article=articulo,
                tool_code=codigo,
                name="Vernier",
                inventory_status=Tool.InventoryStatus.AVAILABLE,
            )

        libre = crear_pieza("TEST-LIBRE")
        con_entrega = crear_pieza("TEST-ENTREGA")
        con_prestamo_antiguo = crear_pieza("TEST-ANTIGUO")

        # Reproducimos la discrepancia: la ficha sigue en "Disponible".
        QuantityIssue.objects.create(
            tool=con_entrega,
            employee=trabajador,
            quantity=1,
            requires_return=True,
        )
        Loan.objects.create(
            tool=con_prestamo_antiguo,
            employee=trabajador,
        )

        respuesta = self.client.get(
            reverse("admin:stockroom_quantityissue_add")
        )
        self.assertEqual(respuesta.status_code, 200)

        formulario = respuesta.context["adminform"].form
        opciones = formulario.fields["tool"].queryset
        self.assertSetEqual(
            set(opciones.values_list("pk", flat=True)),
            {libre.pk},
        )