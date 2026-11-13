from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from stockroom.models import (
    Article, DamageResolution, Employee, QuantityIssue,
    QuantityReturn, QuantityStock,
)
from stockroom.templatetags.jefe_dashboard import indicadores_jefe


class DashboardJefeTests(TestCase):
    def setUp(self):
        self.empleado = Employee.objects.create(employee_id='T-901', first_name='Ana', last_name='Prueba')
        articulo = Article.objects.create(article_code='T-901', name='Pieza prueba', tracking_mode=Article.TrackingMode.QUANTITY)
        stock = QuantityStock.objects.create(article=articulo, available_quantity=10)
        issue = QuantityIssue.objects.create(stock=stock, employee=self.empleado, quantity=5, requires_return=True)
        self.retorno = QuantityReturn.objects.create(issue=issue, quantity=5, condition=QuantityReturn.Condition.DAMAGED, reason='Prueba de daño')

    def crear_resolucion(self, outcome, qty, dias=0):
        return DamageResolution.objects.create(
            source_return=self.retorno, quantity=qty, outcome=outcome,
            reason='Prueba de clasificación', resolved_at=timezone.now()-timedelta(days=dias),
        )

    def test_solo_cuenta_baja_definitiva(self):
        self.crear_resolucion(DamageResolution.Outcome.SCRAPPED, 2)
        self.crear_resolucion(DamageResolution.Outcome.RESTORED, 3)
        data = indicadores_jefe('30')
        self.assertEqual(data['bajas_total'], 2)
        self.assertEqual(data['recuperadas_total'], 3)
        self.assertEqual(data['filas_desechos'][0]['porcentaje'], 40)

    def test_periodo_excluye_resoluciones_antiguas(self):
        self.crear_resolucion(DamageResolution.Outcome.SCRAPPED, 2, dias=40)
        self.assertEqual(indicadores_jefe('30')['bajas_total'], 0)
        self.assertEqual(indicadores_jefe('todo')['bajas_total'], 2)

    def test_periodo_invalido_usa_treinta_dias(self):
        self.assertEqual(indicadores_jefe('incorrecto')['periodo'], '30')
