
from django.test import SimpleTestCase

from stockroom.employee_history_summary import (
    calcular_resumen_devoluciones,
)


class ResumenDevolucionesTests(SimpleTestCase):

    def test_devoluciones_parciales_y_danos(self):
        resumen = calcular_resumen_devoluciones(
            total_devueltas=6,
            total_danadas=2,
            total_danos_resueltos=1,
        )

        self.assertEqual(resumen["total_devueltas"], 6)
        self.assertEqual(resumen["total_buen_estado"], 4)
        self.assertEqual(resumen["total_danadas"], 2)
        self.assertEqual(resumen["total_danos_resueltos"], 1)
        self.assertEqual(resumen["total_danos_sin_resolver"], 1)

    def test_resolucion_no_duplica_devoluciones(self):
        resumen = calcular_resumen_devoluciones(
            total_devueltas=5,
            total_danadas=3,
            total_danos_resueltos=3,
        )

        self.assertEqual(resumen["total_devueltas"], 5)
        self.assertEqual(resumen["total_buen_estado"], 2)
        self.assertEqual(resumen["total_danos_sin_resolver"], 0)

    def test_detecta_resoluciones_inconsistentes(self):
        with self.assertRaises(ValueError):
            calcular_resumen_devoluciones(
                total_devueltas=2,
                total_danadas=1,
                total_danos_resueltos=3,
            )
