"""Fase 23J: verificaciones del buscador remoto sin registrar inventario."""
from pathlib import Path
from django.conf import settings
from django.test import SimpleTestCase

BASE = Path(settings.BASE_DIR) / "stockroom" / "static" / "stockroom"


class ExperienciaBusqueda23JTests(SimpleTestCase):
    def test_buscador_es_remoto_y_no_envia_formulario(self):
        js = (BASE / "js" / "busqueda_escaneo.js").read_text(encoding="utf-8")
        for fragmento in ('fetch(', 'method: "GET"', 'credentials: "same-origin"',
                          'redirect: "manual"', 'cache: "no-store"',
                          'event.preventDefault()', 'AbortController', 'data.results'):
            with self.subTest(fragmento=fragmento):
                self.assertIn(fragmento, js)
        self.assertNotIn('.submit(', js)
        self.assertNotIn('method: "POST"', js)

    def test_limpiar_seleccion_e_invalidar_peticiones(self):
        js = (BASE / "js" / "busqueda_escaneo.js").read_text(encoding="utf-8")
        for fragmento in ('clearButton.type = "button"', 'clearButton.addEventListener("click", clear)',
                          'resetOptions()', '++requestId', 'controller.abort()',
                          'input.value.trim().slice(0, 80) !== q', 'ticket !== requestId'):
            with self.subTest(fragmento=fragmento):
                self.assertIn(fragmento, js)

    def test_avisos_y_estilos_accesibles(self):
        js = (BASE / "js" / "busqueda_escaneo.js").read_text(encoding="utf-8")
        css = (BASE / "css" / "busqueda_escaneo.css").read_text(encoding="utf-8")
        self.assertIn('aria-live', js)
        self.assertIn('Sin coincidencias', js)
        self.assertIn('entradas_correccion', js)
        self.assertIn('.sr-scan-clear', css)
        self.assertIn('[data-state="error"]', css)
