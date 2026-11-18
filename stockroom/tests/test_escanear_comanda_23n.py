"""Fase 23N: pruebas de escaneo seguro, sin movimientos reales.

Ejecutar con: python manage.py test stockroom.tests.test_escanear_comanda_23n -v 2
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee, MaterialRequest, QuantityIssue, QuantityReturn


class EscaneoComanda23NTests(TestCase):
    def setUp(self):
        self.employee = Employee.objects.create(
            employee_id="ESC23N", first_name="Prueba", last_name="Escaneo"
        )
        self.solicitud = MaterialRequest.objects.create(
            employee=self.employee, status=MaterialRequest.Status.SUBMITTED
        )
        self.ruta = reverse("escanear_comanda")
        self.usuario = get_user_model().objects.create_superuser(
            username="operador_23n", password="Prueba23N_segura!"
        )

    def escanear(self, codigo):
        return self.client.post(self.ruta, {"code": codigo})

    def test_codigo_valido_abre_solicitud_sin_modificarla(self):
        self.client.force_login(self.usuario)
        estado_anterior = self.solicitud.status
        respuesta = self.escanear(f"SOL-{self.solicitud.pk:06d}")
        self.assertRedirects(
            respuesta,
            reverse("detalle_solicitud_almacen", kwargs={"request_id": self.solicitud.pk}),
            fetch_redirect_response=False,
        )
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.status, estado_anterior)
        self.assertEqual(QuantityIssue.objects.count(), 0)
        self.assertEqual(QuantityReturn.objects.count(), 0)

    def test_escaneo_repetido_no_genera_entregas(self):
        self.client.force_login(self.usuario)
        codigo = f"SOL-{self.solicitud.pk:06d}"
        for _ in range(2):
            respuesta = self.escanear(codigo)
            self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(QuantityIssue.objects.count(), 0)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.status, MaterialRequest.Status.SUBMITTED)

    def test_folio_inexistente_muestra_error_y_no_redirige(self):
        self.client.force_login(self.usuario)
        respuesta = self.escanear("SOL-999999999")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No encontramos una solicitud enviada")
        self.assertEqual(QuantityIssue.objects.count(), 0)

    def test_carrito_borrador_no_se_puede_abrir_por_escaner(self):
        self.client.force_login(self.usuario)
        borrador = MaterialRequest.objects.create(employee=self.employee)
        respuesta = self.escanear(f"SOL-{borrador.pk:06d}")
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No encontramos una solicitud enviada")

    def test_codigo_malformado_es_rechazado(self):
        self.client.force_login(self.usuario)
        for codigo in ("SOL'000001", "HERR-000001", "SOL-ABC", "SOL-"):
            with self.subTest(codigo=codigo):
                respuesta = self.escanear(codigo)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].errors)
        self.assertEqual(QuantityIssue.objects.count(), 0)

    def test_sin_sesion_no_se_escanea(self):
        respuesta = self.escanear(f"SOL-{self.solicitud.pk:06d}")
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse("acceso_almacen"), respuesta["Location"])

    def test_usuario_sin_permiso_no_consulta_comandas(self):
        usuario = get_user_model().objects.create_user(
            username="sin_permiso_23n", password="Prueba23N_segura!"
        )
        self.client.force_login(usuario)
        respuesta = self.escanear(f"SOL-{self.solicitud.pk:06d}")
        self.assertEqual(respuesta.status_code, 403)
