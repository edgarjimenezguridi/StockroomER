"""24B: contrato del PDF corporativo del libro de códigos."""
import io
from datetime import datetime
from pathlib import Path

from django.test import SimpleTestCase
from pypdf import PdfReader

from stockroom.libro_codigos_pdf import generar_libro_codigos_pdf


class LibroCodigosDiseno24BTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.registros = [
            (('Medición', 'Calibradores', '0–150 mm'), {
                'codigo': 'PIEZA-000001', 'nombre': 'Vernier digital',
                'clase': 'Pieza individual', 'detalle': 'Artículo: VER-01',
                'ubicacion': 'Estante A2',
            }),
            (('Corte', 'Brocas', 'HSS'), {
                'codigo': 'ART-000023', 'nombre': 'Broca HSS',
                'clase': 'Artículo por cantidad', 'detalle': 'Disponibles: 4',
                'ubicacion': 'Gaveta 2',
            }),
        ]
        cls.contenido = generar_libro_codigos_pdf(
            registros=cls.registros, generado=datetime(2026, 11, 19, 10, 30),
        ).getvalue()
        cls.reader = PdfReader(io.BytesIO(cls.contenido))

    def test_pdf_tiene_portada_indice_y_categorias(self):
        self.assertTrue(self.contenido.startswith(b'%PDF-'))
        self.assertGreaterEqual(len(self.reader.pages), 4)
        self.assertIn('LIBRO DE', self.reader.pages[0].extract_text())
        self.assertIn('Índice por categoría', self.reader.pages[1].extract_text())
        indice = self.reader.pages[1].extract_text()
        self.assertIn('Corte', indice)
        self.assertIn('Medición', indice)

    def test_codigo_original_visible_y_no_se_modifica(self):
        texto = '\n'.join(page.extract_text() for page in self.reader.pages)
        self.assertIn('PIEZA-000001', texto)
        self.assertIn('ART-000023', texto)
        self.assertIn('Calibradores', texto)
        self.assertIn('0–150 mm', texto)
        self.assertIn('Gaveta 2', texto)

    def test_logo_original_esta_en_el_proyecto_y_en_pdf(self):
        ruta = (Path(__file__).resolve().parent.parent / 'static' / 'img' /
                'logo_empresa.png')
        self.assertTrue(ruta.is_file())
        imagenes = self.reader.pages[0].get('/Resources').get_object().get('/XObject')
        self.assertTrue(imagenes)

    def test_indice_tiene_numeros_de_pagina_reales(self):
        indice = self.reader.pages[1].extract_text()
        self.assertIn('3', indice)
        self.assertIn('4', indice)

    def test_sin_registros_genera_pdf_con_aviso(self):
        datos = generar_libro_codigos_pdf(
            registros=[], generado=datetime(2026, 11, 19, 10, 30)
        ).getvalue()
        texto = '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(datos)).pages)
        self.assertIn('No hay artículos ni piezas disponibles', texto)
