from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from stockroom.models import (
    Article, Employee, QuantityIssue, QuantityStock,
    StockEntry, StockEntryCorrection,
)
from stockroom.services import (
    register_quantity_issue,
    register_stock_entry,
    register_stock_entry_correction,
)


class StockEntryCorrectionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username="almacenista")
        article = Article.objects.create(
            article_code="TEST-M6",
            name="Machuelo M6",
            tracking_mode=Article.TrackingMode.QUANTITY,
        )
        self.stock = QuantityStock.objects.create(article=article)
        self.entry = register_stock_entry(
            StockEntry(stock=self.stock, quantity=10)
        )

    def corregir(self, delta):
        correction = StockEntryCorrection(
            entry=self.entry,
            quantity_delta=delta,
            reason="Diferencia en el conteo de recepción",
        )
        return register_stock_entry_correction(correction, user=self.user)

    def test_corrige_de_10_a_8_y_conserva_el_historial(self):
        self.corregir(-2)

        self.entry.refresh_from_db()
        self.stock.refresh_from_db()
        correction = self.entry.corrections.get()

        self.assertEqual(self.entry.quantity, 10)
        self.assertEqual(self.stock.available_quantity, 8)
        self.assertEqual(correction.quantity_delta, -2)
        self.assertEqual(correction.recorded_by_id, self.user.pk)

    def test_rechaza_descuento_si_solo_queda_una_disponible(self):
        employee = Employee.objects.create(
            employee_id="TEST-001", first_name="Ana", last_name="Prueba"
        )
        register_quantity_issue(
            QuantityIssue(stock=self.stock, employee=employee, quantity=9)
        )

        with self.assertRaisesMessage(ValidationError, "piezas disponibles"):
            self.corregir(-2)

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.available_quantity, 1)
        self.assertEqual(self.stock.loaned_quantity, 9)
        self.assertFalse(self.entry.corrections.exists())

    def test_otra_entrada_no_permite_descontar_de_mas(self):
        self.corregir(-2)  # A la entrada original le quedan 8.
        register_stock_entry(StockEntry(stock=self.stock, quantity=10))

        # Hay 18 disponibles en total, pero solo 8 corresponden a esta entrada.
        with self.assertRaisesMessage(ValidationError, "por debajo de cero"):
            self.corregir(-9)

        self.stock.refresh_from_db()
        self.assertEqual(self.stock.available_quantity, 18)
        self.assertEqual(self.entry.corrections.count(), 1)
        self.assertEqual(self.entry.corrections.get().quantity_delta, -2)

    
    def test_correcciones_sucesivas_no_superan_entrada_original(self):
        # Entrada original de 10 piezas.
        self.corregir(-3)
        self.corregir(-4)

        self.stock.refresh_from_db()

        self.assertEqual(self.stock.available_quantity, 3)
        self.assertEqual(self.entry.corrections.count(), 2)

        # Intentar descontar otras 4 debe rechazarse.
        # En este caso, la validación de existencias
        # disponibles se ejecuta primero.
        with self.assertRaisesMessage(
            ValidationError,
            "No hay suficientes piezas disponibles",
        ):
            self.corregir(-4)

        # Comprobar que el intento fallido
        # no modificó las existencias.
        self.stock.refresh_from_db()
        self.entry.refresh_from_db()

        self.assertEqual(self.stock.available_quantity, 3)
        self.assertEqual(self.entry.quantity, 10)
        self.assertEqual(self.entry.corrections.count(), 2)


    def test_correccion_positiva_aumenta_existencias(self):
        correction = self.corregir(5)

        self.stock.refresh_from_db()
        self.entry.refresh_from_db()

        self.assertEqual(self.stock.available_quantity, 15)
        self.assertEqual(self.entry.quantity, 10)

        self.assertEqual(correction.quantity_delta, 5)
        self.assertEqual(correction.recorded_by_id, self.user.pk)
        self.assertEqual(self.entry.corrections.count(), 1)

    def test_rechaza_correccion_de_cero(self):
        with self.assertRaises(ValidationError):
            self.corregir(0)

        self.stock.refresh_from_db()

        self.assertEqual(self.stock.available_quantity, 10)
        self.assertFalse(self.entry.corrections.exists())


