"""Fase 23T: mejora de la captura de comandas sin alterar inventario."""
from pathlib import Path

from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase

TEMPLATE_NAME = "stockroom/almacen/escanear_comanda.html"
ARCHIVO = Path(settings.BASE_DIR) / "stockroom/templates/stockroom/almacen/escanear_comanda.html"


class ExperienciaEscaneo23TTests(SimpleTestCase):
    def setUp(self):
        self.html = ARCHIVO.read_text(encoding="utf-8")

    def test_plantilla_compila_y_extends_primero(self):
        self.assertTrue(self.html.lstrip().startswith('{% extends "stockroom/base.html" %}'))
        get_template(TEMPLATE_NAME)

    def test_boton_limpiar_no_envia_formulario(self):
        self.assertIn('type="button" class="boton-empresa boton-limpiar" id="limpiar-escaneo"', self.html)
        self.assertIn('limpiar.addEventListener("click"', self.html)
        self.assertIn('campo.value = ""', self.html)
        self.assertIn('enfocarCampo()', self.html)

    def test_prepara_lector_y_controla_doble_envio(self):
        self.assertIn('campo.setAttribute("autocomplete", "off")', self.html)
        self.assertIn('formulario.addEventListener("submit"', self.html)
        self.assertIn('event.preventDefault()', self.html)
        self.assertIn('boton.disabled = true', self.html)
        self.assertIn('limpiar.disabled = true', self.html)
        self.assertIn('campo.value.trim().toUpperCase()', self.html)

    def test_regreso_historial_rehabilita_botones(self):
        self.assertIn('window.addEventListener("pageshow"', self.html)
        self.assertIn('if (event.persisted)', self.html)
        self.assertIn('restablecerEnvio()', self.html)
        self.assertIn('boton.disabled = false', self.html)
        self.assertIn('limpiar.disabled = false', self.html)

    def test_escaneo_no_genera_movimientos(self):
        self.assertIn('method="post" id="formulario-escaneo"', self.html)
        self.assertIn('El escaneo solamente abre la solicitud.', self.html)
        self.assertNotIn('fetch(', self.html)
        self.assertNotIn('formulario.submit()', self.html)
