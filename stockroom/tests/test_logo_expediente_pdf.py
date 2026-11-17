
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase
from PIL import Image as PILImage

from stockroom.employee_profile_pdf_views import (
    obtener_logo_empresa_pdf,
)


class LogoExpedientePDFTests(SimpleTestCase):

    def test_sin_archivo_no_interrumpe_generacion(self):
        with patch(
            "stockroom.employee_profile_pdf_views.finders.find",
            return_value=None,
        ):
            logo = obtener_logo_empresa_pdf()

        self.assertIsNone(logo)

    def test_logo_conserva_proporciones_originales(self):
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "logo_prueba.png"

            PILImage.new(
                "RGB",
                (400, 100),
                "white",
            ).save(ruta)

            with patch(
                "stockroom.employee_profile_pdf_views.finders.find",
                return_value=str(ruta),
            ):
                logo = obtener_logo_empresa_pdf()

            self.assertIsNotNone(logo)
            self.assertLessEqual(logo.drawWidth, 210)
            self.assertLessEqual(logo.drawHeight, 65)

            proporcion = logo.drawWidth / logo.drawHeight

            self.assertAlmostEqual(
                proporcion,
                4.0,
                places=4,
            )
