"""Fase 23E: cierre seguro de jefatura y actualización que no se bloquea."""
from pathlib import Path
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, SimpleTestCase
from django.urls import reverse


class CierreJefaturaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.jefe = get_user_model().objects.create_superuser(
            username="jefe_23e", password="TestPassword23e!"
        )

    def test_panel_principal_muestra_cerrar_sesion_post_con_csrf(self):
        self.client.force_login(self.jefe)
        respuesta = self.client.get(reverse("panel_jefe"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, reverse("salir_jefe"))
        self.assertContains(respuesta, "Cerrar sesión")
        self.assertContains(respuesta, 'method="post"')
        self.assertContains(respuesta, 'name="csrfmiddlewaretoken"')

    def test_cierre_post_finaliza_sesion_y_get_no_lo_hace(self):
        self.client.force_login(self.jefe)
        url = reverse("salir_jefe")
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertIn("_auth_user_id", self.client.session)
        respuesta = self.client.post(url)
        self.assertRedirects(respuesta, reverse("acceso_jefe"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_cierre_post_verifica_csrf(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.jefe)
        self.assertEqual(client.post(reverse("salir_jefe")).status_code, 403)
        self.assertIn("_auth_user_id", client.session)


class RefrescoYBotonJefaturaTests(SimpleTestCase):
    def test_js_no_se_detiene_por_foco_en_boton_o_hover(self):
        ruta = Path(settings.BASE_DIR) / "stockroom/static/stockroom/js/panel_actualizacion.js"
        codigo = ruta.read_text(encoding="utf-8")
        self.assertNotIn('actual.matches(":hover")', codigo)
        self.assertIn('actual.contains(activo)', codigo)
        self.assertIn('credentials: "same-origin"', codigo)
        self.assertIn('redirect: "manual"', codigo)
        self.assertIn('cache: "no-store"', codigo)
        self.assertIn('stockroom:panel-actualizado', codigo)

    def test_regreso_en_personal_es_boton(self):
        ruta = Path(settings.BASE_DIR) / "stockroom/templates/stockroom/jefe/personal.html"
        codigo = ruta.read_text(encoding="utf-8")
        self.assertIn('class="sr-btn sr-btn-secondary"', codigo)
        self.assertIn('Volver al panel directivo', codigo)
