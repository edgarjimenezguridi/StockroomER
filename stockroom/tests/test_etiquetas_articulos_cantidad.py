"""Fase 23D: generación de etiquetas por artículo y controles de acceso."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Article


class EtiquetasArticulosCantidadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.jefe_tecnico = get_user_model().objects.create_superuser(
            username="etiqueta_23d_super", password="ClaveTemporal123!"
        )
        cls.operador = get_user_model().objects.create_user(
            username="etiqueta_23d_almacen", password="ClaveTemporal123!", is_staff=True
        )
        cls.operador.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="stockroom",
            codename__in=("view_article", "view_quantitystock", "view_tool"),
        ))
        cls.sin_permiso = get_user_model().objects.create_user(
            username="etiqueta_23d_no", password="ClaveTemporal123!", is_staff=True
        )
        cls.articulo = Article.objects.create(
            article_code="ABC-23D-001", name="Broca de prueba",
            location="Estante A2", tracking_mode=Article.TrackingMode.QUANTITY,
        )
        cls.individual = Article.objects.create(
            article_code="IND-23D-001", name="Pieza individual",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
        )

    def setUp(self):
        self.url = reverse("imprimir_etiqueta_articulo_almacen", args=[self.articulo.pk])

    def test_etiqueta_generada_con_codigo_real_y_sin_movimientos(self):
        self.client.force_login(self.operador)
        antes = Article.objects.get(pk=self.articulo.pk)
        respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "ABC-23D-001")
        self.assertContains(respuesta, "Broca de prueba")
        self.assertContains(respuesta, "Estante A2")
        self.assertContains(respuesta, "data:image/svg+xml;base64,")
        self.assertEqual(Article.objects.get(pk=self.articulo.pk).article_code, antes.article_code)

    def test_no_permitir_anonymous_ni_sin_permisos(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.sin_permiso)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_rechaza_articulo_individual_e_inexistente(self):
        self.client.force_login(self.operador)
        url_individual = reverse("imprimir_etiqueta_articulo_almacen", args=[self.individual.pk])
        self.assertEqual(self.client.get(url_individual).status_code, 404)
        self.assertEqual(self.client.get(reverse("imprimir_etiqueta_articulo_almacen", args=[999999])).status_code, 404)

    def test_tabla_consultar_existencias_ofrece_etiqueta_cantidad(self):
        self.client.force_login(self.operador)
        respuesta = self.client.get(reverse("consultar_existencias_almacen"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.url)
        self.assertContains(respuesta, "Etiqueta")
        self.assertNotContains(
            respuesta,
            reverse("imprimir_etiqueta_articulo_almacen", args=[self.individual.pk]),
        )

    def test_no_admite_post(self):
        self.client.force_login(self.operador)
        self.assertEqual(self.client.post(self.url).status_code, 405)
