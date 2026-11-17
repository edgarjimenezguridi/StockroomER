
"""Fase 19H: integración de inventario, expediente web y PDF."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from stockroom.employee_history_summary import (
    calcular_resumen_devoluciones,
)
from stockroom.models import (
    Article,
    DamageResolution,
    Employee,
    QuantityIssue,
    QuantityReturn,
    QuantityStock,
)
from stockroom.services import (
    register_damage_resolution,
    register_quantity_issue,
    register_quantity_return,
)


class IntegracionExpedienteTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_user(
            username="jefe_integracion_19h",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )

        cls.jefe.groups.add(
            Group.objects.get_or_create(name="Jefes")[0]
        )

        cls.empleado = Employee.objects.create(
            employee_id="INTEG-19H",
            first_name="Trabajador",
            last_name="Integracion",
        )

        cls.articulo = Article.objects.create(
            article_code="INTEG-ART-19H",
            name="Machuelo de integracion",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )

        cls.stock = QuantityStock.objects.create(
            article=cls.articulo,
            available_quantity=10,
        )

    def setUp(self):
        self.client.force_login(self.jefe)

        # Registrar una entrega mediante el servicio real.
        self.issue = QuantityIssue(
            stock=self.stock,
            employee=self.empleado,
            quantity=10,
        )
        register_quantity_issue(self.issue)

        # Devolver cuatro piezas en buen estado.
        self.devolucion_buena = QuantityReturn(
            issue=self.issue,
            quantity=4,
            condition=QuantityReturn.Condition.GOOD,
            reason="Devolucion de prueba",
        )
        register_quantity_return(self.devolucion_buena)

        # Devolver dos piezas dañadas.
        self.devolucion_danada = QuantityReturn(
            issue=self.issue,
            quantity=2,
            condition=QuantityReturn.Condition.DAMAGED,
            reason="Dano de prueba",
        )
        register_quantity_return(self.devolucion_danada)

        # Recuperar una de las piezas dañadas.
        self.resolucion = DamageResolution(
            source_return=self.devolucion_danada,
            quantity=1,
            outcome=DamageResolution.Outcome.RESTORED,
            reason="Pieza reparada",
        )
        register_damage_resolution(self.resolucion)

        self.issue.refresh_from_db()
        self.stock.refresh_from_db()

    def test_movimientos_generan_existencias_correctas(self):
        self.assertEqual(self.issue.quantity, 10)
        self.assertEqual(self.issue.returned_quantity, 6)

        self.assertEqual(
            self.issue.quantity - self.issue.returned_quantity,
            4,
        )

        self.assertEqual(self.stock.available_quantity, 5)
        self.assertEqual(self.stock.loaned_quantity, 4)
        self.assertEqual(self.stock.quarantine_quantity, 1)
        self.assertEqual(self.stock.scrapped_quantity, 0)

        self.devolucion_danada.refresh_from_db()
        self.assertEqual(
            self.devolucion_danada.resolved_quantity,
            1,
        )

    def test_expediente_web_calcula_totales_correctos(self):
        response = self.client.get(
            reverse(
                "expediente_trabajador_jefe",
                args=[self.empleado.pk],
            )
        )

        self.assertEqual(response.status_code, 200)

        contexto = response.context

        self.assertEqual(contexto["total_piezas"], 4)
        self.assertEqual(contexto["total_inicial"], 0)
        self.assertEqual(contexto["total_normales"], 4)

        self.assertEqual(contexto["total_devueltas"], 6)
        self.assertEqual(contexto["total_buen_estado"], 4)
        self.assertEqual(contexto["total_danadas"], 2)
        self.assertEqual(contexto["total_danos_resueltos"], 1)
        self.assertEqual(contexto["total_danos_sin_resolver"], 1)

        self.assertContains(
            response,
            "Machuelo de integracion",
        )

    def test_pdf_utiliza_mismos_totales_y_no_altera_inventario(self):
        # Obtenemos los resultados reales del expediente web.
        response_web = self.client.get(
            reverse(
                "expediente_trabajador_jefe",
                args=[self.empleado.pk],
            )
        )

        self.assertEqual(response_web.status_code, 200)

        campos = (
            "total_devueltas",
            "total_buen_estado",
            "total_danadas",
            "total_danos_resueltos",
            "total_danos_sin_resolver",
        )

        resumen_web = {
            campo: response_web.context[campo]
            for campo in campos
        }

        # Capturamos los valores que utiliza el generador PDF.
        with patch(
            "stockroom.employee_profile_pdf_views."
            "calcular_resumen_devoluciones",
            wraps=calcular_resumen_devoluciones,
        ) as calcular_pdf:
            response_pdf = self.client.get(
                reverse(
                    "expediente_pdf_jefe",
                    args=[self.empleado.pk],
                )
            )

        self.assertEqual(response_pdf.status_code, 200)
        self.assertTrue(response_pdf.content.startswith(b"%PDF-"))

        
        calcular_pdf.assert_called_once()

        # Recuperamos los argumentos reales utilizados por el PDF.
        argumentos_pdf = calcular_pdf.call_args.kwargs

        # Calculamos el resumen con los mismos datos que recibió
        # el generador del documento.
        resumen_pdf = calcular_resumen_devoluciones(
            **argumentos_pdf
        )

        for campo in campos:
            self.assertEqual(
                resumen_web[campo],
                resumen_pdf[campo],
                f"Diferencia detectada en el indicador: {campo}",
            )


        # La generación del PDF no altera existencias.
        self.stock.refresh_from_db()
        self.issue.refresh_from_db()

        self.assertEqual(self.stock.available_quantity, 5)
        self.assertEqual(self.stock.loaned_quantity, 4)
        self.assertEqual(self.stock.quarantine_quantity, 1)
        self.assertEqual(self.stock.scrapped_quantity, 0)

        self.assertEqual(self.issue.returned_quantity, 6)

        self.assertEqual(
            QuantityReturn.objects.filter(
                issue=self.issue,
            ).count(),
            2,
        )

        self.assertEqual(
            DamageResolution.objects.filter(
                source_return=self.devolucion_danada,
            ).count(),
            1,
        )
    
    def test_resumen_ejecutivo_con_movimientos(self):
        response = self.client.get(
            reverse(
                "expediente_trabajador_jefe",
                args=[self.empleado.pk],
            )
        )

        self.assertEqual(response.status_code, 200)

        contexto = response.context

        self.assertEqual(contexto["total_piezas"], 4)
        self.assertEqual(contexto["total_inicial"], 0)
        self.assertEqual(contexto["total_normales"], 4)
        self.assertEqual(contexto["total_devueltas"], 6)
        self.assertEqual(contexto["total_danadas"], 2)
        self.assertEqual(
            contexto["total_danos_sin_resolver"], 1
        )

    def test_pdf_se_genera_con_resumen_ejecutivo(self):
        response = self.client.get(
            reverse(
                "expediente_pdf_jefe",
                args=[self.empleado.pk],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/pdf",
        )
        self.assertTrue(
            response.content.startswith(b"%PDF-")
        )

        self.stock.refresh_from_db()
        self.issue.refresh_from_db()

        self.assertEqual(self.stock.available_quantity, 5)
        self.assertEqual(self.stock.loaned_quantity, 4)
        self.assertEqual(self.stock.quarantine_quantity, 1)
        self.assertEqual(self.issue.returned_quantity, 6)

