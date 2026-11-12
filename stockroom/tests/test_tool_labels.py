
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Article, Tool


class ToolLabelTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.admin = User.objects.create_superuser(
            username="test_etiquetas_admin",
            email="etiquetas@example.com",
            password="ClaveTemporal123!",
        )

        articulo = Article.objects.create(
            article_code="TEST-ETQ-ART",
            name="Vernier de prueba",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
        )

        cls.pieza = Tool.objects.create(
            article=articulo,
            tool_code="TEST-ETQ-001",
            name="Vernier",
        )

    def setUp(self):
        self.url = reverse(
            "imprimir_etiqueta_pieza_almacen",
            kwargs={"tool_id": self.pieza.pk},
        )

    def test_etiqueta_contiene_codigo_real(self):
        self.client.force_login(self.admin)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "TEST-ETQ-001")
        self.assertContains(
            respuesta,
            "data:image/svg+xml;base64,",
        )

    def test_usuario_anonimo_no_puede_ver_etiqueta(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 302)

    def test_usuario_sin_permiso_recibe_403(self):
        User = get_user_model()

        usuario = User.objects.create_user(
            username="test_etiqueta_sin_permiso",
            password="ClaveTemporal456!",
            is_staff=True,
        )

        self.client.force_login(usuario)

        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 403)

    def test_herramienta_inexistente_devuelve_404(self):
        self.client.force_login(self.admin)

        url = reverse(
            "imprimir_etiqueta_pieza_almacen",
            kwargs={"tool_id": 999999},
        )

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 404)
