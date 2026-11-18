"""Pruebas aisladas de permisos y comportamiento de la API de búsqueda."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse


class BusquedaDinamica23HTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.jefe = User.objects.create_user(username="jefe_lookup_23h", password="clavePrueba!23", is_staff=True)
        cls.almacenista = User.objects.create_user(username="almacen_lookup_23h", password="clavePrueba!23", is_staff=True)
        cls.almacenista.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="stockroom", codename__in=[
                "add_stockentry", "add_stockentrycorrection", "add_quantityissue",
                "view_employee", "view_materialrequest",
            ]
        ))
        cls.url = reverse("buscar_almacen")

    def test_sin_sesion_no_entrega_datos(self):
        respuesta = self.client.get(self.url, {"tipo": "trabajadores_stock", "q": "0001"})
        self.assertEqual(respuesta.status_code, 302)

    def test_sin_permisos_rechazado(self):
        self.client.force_login(self.jefe)
        respuesta = self.client.get(self.url, {"tipo": "trabajadores_stock", "q": "0001"})
        self.assertEqual(respuesta.status_code, 403)

    def test_consultas_solo_lectura_y_parametros_limitados(self):
        self.client.force_login(self.almacenista)
        for tipo in ("articulos_entrada", "entradas_correccion", "trabajadores_stock", "articulos_stock", "piezas_stock"):
            with self.subTest(tipo=tipo):
                respuesta = self.client.get(self.url, {"tipo": tipo, "q": "prueba"})
                self.assertEqual(respuesta.status_code, 200)
                self.assertIsInstance(respuesta.json()["results"], list)
                self.assertLessEqual(len(respuesta.json()["results"]), 20)
        self.assertEqual(self.client.get(self.url, {"tipo": "desconocido", "q": "x"}).status_code, 400)
        self.assertEqual(self.client.post(self.url, {"tipo": "articulos_entrada"}).status_code, 405)

    def test_busqueda_vacia_no_carga_catalogos(self):
        self.client.force_login(self.almacenista)
        respuesta = self.client.get(self.url, {"tipo": "articulos_stock", "q": " "})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.json(), {"results": []})
