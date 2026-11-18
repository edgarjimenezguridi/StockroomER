from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class ConsultasIndependientesJefeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.jefe = User.objects.create_superuser(
            username="jefe_consultas_23a", password="Temporal_23A_123!",
        )
        cls.no_jefe = User.objects.create_user(
            username="usuario_consultas_23a", password="Temporal_23A_123!",
        )

    def test_tres_consultas_son_independientes_y_de_solo_lectura(self):
        self.client.force_login(self.jefe)
        for seccion in ("adeudos", "reabastecimiento", "solicitudes"):
            with self.subTest(seccion=seccion):
                url = reverse("consultas_operativas_jefe", args=[seccion])
                respuesta = self.client.get(url)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, "Regresar al panel directivo")
                self.assertNotContains(respuesta, 'href="/almacen/')
                self.assertNotContains(respuesta, 'href="/admin/')
                self.assertEqual(self.client.post(url).status_code, 405)

    def test_usuarios_no_jefes_no_pueden_consultar(self):
        self.client.force_login(self.no_jefe)
        for seccion in ("adeudos", "reabastecimiento", "solicitudes"):
            self.assertEqual(self.client.get(
                reverse("consultas_operativas_jefe", args=[seccion])
            ).status_code, 403)

    def test_panel_jefe_no_ofrece_enlaces_a_almacen_ni_admin(self):
        self.client.force_login(self.jefe)
        respuesta = self.client.get(reverse("panel_jefe"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, 'href="/almacen/')
        self.assertNotContains(respuesta, 'href="/admin/')
        for seccion in ("adeudos", "reabastecimiento", "solicitudes"):
            self.assertContains(respuesta, reverse("consultas_operativas_jefe", args=[seccion]))
