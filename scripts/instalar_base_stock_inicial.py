"""Fase 15A: agrega marca de stock inicial y excluye el vencimiento.
No realiza movimientos de inventario. Ejecutar en la raiz de StockroomER.
"""
from pathlib import Path
from datetime import datetime
import re
import shutil
import sys

ROOT = Path.cwd()
MODELS = ROOT / 'stockroom' / 'models.py'
RULES = ROOT / 'stockroom' / 'loan_rules.py'
TESTS = ROOT / 'stockroom' / 'tests' / 'test_stock_inicial_rules.py'
if not (MODELS.is_file() and RULES.is_file() and (ROOT / 'manage.py').is_file()):
    sys.exit('ERROR: ejecuta este script desde la raiz del proyecto StockroomER.')
models = MODELS.read_text(encoding='utf-8-sig')
rules = RULES.read_text(encoding='utf-8-sig')

# Solo tocar la definicion de QuantityIssue.
start = models.find('class QuantityIssue(models.Model):')
if start < 0:
    sys.exit('ERROR: no se encontro class QuantityIssue. No se modifico nada.')
end = models.find('\nclass ', start + 1)
if end < 0: end = len(models)
issue = models[start:end]
if 'is_initial_stock = models.BooleanField(' not in issue:
    needle = '    requires_return = models.BooleanField('
    if issue.count(needle) != 1:
        sys.exit('ERROR: estructura QuantityIssue inesperada. No se modifico nada.')
    issue = issue.replace(needle, '''    # Entrega permanente inicial: conserva adeudo y control de duplicados,
    # pero no vence a los 15 dias.
    is_initial_stock = models.BooleanField(
        "Asignacion de stock inicial",
        default=False,
        editable=False,
        db_index=True,
    )

''' + needle, 1)
    models = models[:start] + issue + models[end:]

# La funcion de vencidos filtra los normales; duplicados siguen contando todos.
old = '''        employee_id=employee_id,
        requires_return=True,
        returned_quantity__lt=F("quantity"),
        issued_at__lt=ahora - timedelta(days=PLAZO_PRESTAMO_DIAS),'''
new = '''        employee_id=employee_id,
        requires_return=True,
        is_initial_stock=False,
        returned_quantity__lt=F("quantity"),
        issued_at__lt=ahora - timedelta(days=PLAZO_PRESTAMO_DIAS),'''
if old in rules:
    rules = rules.replace(old, new, 1)
elif new not in rules:
    sys.exit('ERROR: estructura entregas_vencidas inesperada. No se modifico nada.')

old_limit = '''def fecha_limite(issue):
    if not issue.requires_return:
        return None'''
new_limit = '''def fecha_limite(issue):
    if not issue.requires_return or issue.is_initial_stock:
        return None'''
if old_limit in rules:
    rules = rules.replace(old_limit, new_limit, 1)
elif new_limit not in rules:
    sys.exit('ERROR: funcion fecha_limite inesperada. No se modifico nada.')

old_status = '''    if not issue.requires_return:
        return "consumible"
    if issue.returned_quantity >= issue.quantity:
        return "devuelto"'''
new_status = '''    if not issue.requires_return:
        return "consumible"
    if issue.returned_quantity >= issue.quantity:
        return "devuelto"
    if issue.is_initial_stock:
        return "stock_inicial"'''
if old_status in rules:
    rules = rules.replace(old_status, new_status, 1)
elif new_status not in rules:
    sys.exit('ERROR: funcion estado_prestamo inesperada. No se modifico nada.')

# Asegura que no se haya excluido por error stock inicial de duplicados.
dup_start = rules.find('def motivo_duplicado(')
dup_end = rules.find('\ndef ', dup_start + 1)
if dup_start < 0 or 'QuantityIssue.objects.filter(' not in rules[dup_start:dup_end]:
    sys.exit('ERROR: regla de duplicados no identificada. No se modifico nada.')

stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
backup = ROOT / 'backups' / f'stock_inicial_base_{stamp}'
backup.mkdir(parents=True, exist_ok=True)
shutil.copy2(MODELS, backup / 'models.py')
shutil.copy2(RULES, backup / 'loan_rules.py')
MODELS.write_text(models, encoding='utf-8')
RULES.write_text(rules, encoding='utf-8')

TESTS.write_text('''from datetime import timedelta
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from stockroom.models import Article, Employee, QuantityIssue, QuantityStock
from stockroom.loan_rules import (
    entregas_vencidas, tiene_adeudos_vencidos, fecha_limite,
    estado_prestamo, motivo_duplicado, validar_bloqueo_vencimiento,
)

class StockInicialReglasTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            employee_id="FASE15-001", first_name="Prueba", last_name="Inicial"
        )
        self.article = Article.objects.create(
            article_code="FASE15-ART", name="Herramienta inicial",
            tracking_mode=Article.TrackingMode.QUANTITY,
            return_mode=Article.ReturnMode.RETURNABLE,
        )
        self.stock = QuantityStock.objects.create(
            article=self.article, available_quantity=5,
        )

    def nueva_entrega(self, *, initial):
        return QuantityIssue.objects.create(
            employee=self.employee, stock=self.stock, quantity=1,
            requires_return=True, is_initial_stock=initial,
            issued_at=timezone.now() - timedelta(days=40),
        )

    def test_stock_inicial_no_vence_ni_bloquea(self):
        entrega = self.nueva_entrega(initial=True)
        self.assertIsNone(fecha_limite(entrega))
        self.assertEqual(estado_prestamo(entrega), "stock_inicial")
        self.assertFalse(entregas_vencidas(self.employee.pk).exists())
        self.assertFalse(tiene_adeudos_vencidos(self.employee.pk))
        validar_bloqueo_vencimiento(self.employee.pk)

    def test_stock_inicial_si_detecta_duplicado(self):
        self.nueva_entrega(initial=True)
        self.assertIsNotNone(motivo_duplicado(
            employee_id=self.employee.pk, article_id=self.article.pk,
        ))

    def test_entrega_normal_sigue_venciendo(self):
        entrega = self.nueva_entrega(initial=False)
        self.assertIsNotNone(fecha_limite(entrega))
        self.assertEqual(estado_prestamo(entrega), "vencido")
        self.assertTrue(entregas_vencidas(self.employee.pk).exists())
        with self.assertRaises(ValidationError):
            validar_bloqueo_vencimiento(self.employee.pk)

    def test_stock_inicial_devuelto_es_devuelto(self):
        entrega = self.nueva_entrega(initial=True)
        entrega.returned_quantity = 1
        entrega.save(update_fields=["returned_quantity"])
        self.assertEqual(estado_prestamo(entrega), "devuelto")
        self.assertIsNone(motivo_duplicado(
            employee_id=self.employee.pk, article_id=self.article.pk,
        ))
''', encoding='utf-8')
print('OK: base de stock inicial instalada (sin registrar movimientos).')
print('Respaldo de codigo:', backup)
print('SIGUIENTE: python manage.py makemigrations stockroom')
print('SIGUIENTE: python manage.py migrate')
print('SIGUIENTE: python manage.py test stockroom.tests.test_stock_inicial_rules')
print('SIGUIENTE: python manage.py test stockroom.tests')
