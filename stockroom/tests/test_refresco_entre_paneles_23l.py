"""Fase 23L: verificar que los paneles entregan datos nuevos en cada GET.

Las pruebas se ejecutan sobre la base de datos temporal de Django y no
registran movimientos en la base de datos del taller.
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee, EmployeeCredential, MaterialRequest
from stockroom.worker_session_security import SESSION_KEY, pin_session_version


class RefrescoEntrePaneles23LTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.almacenista = get_user_model().objects.create_superuser(
            username="almacen_refresco_23l",
            email="almacen-refresco@example.invalid",
            password="ClaveTemporal23L!",
        )
        cls.employee = Employee.objects.create(
            employee_id="REFRESCO-23L", first_name="Prueba", last_name="Refresco"
        )
        cls.credential = EmployeeCredential.objects.create(
            employee=cls.employee, pin_hash=make_password("439128")
        )

    def autenticar_trabajador(self):
        session = self.client.session
        session["worker_employee_id"] = self.employee.pk
        session["worker_credential_id"] = self.credential.pk
        session[SESSION_KEY] = pin_session_version(self.credential.pin_hash)
        session.save()

    def nueva_solicitud(self):
        return MaterialRequest.objects.create(
            employee=self.employee, status=MaterialRequest.Status.SUBMITTED
        )

    def test_almacen_ve_solicitud_nueva_en_siguiente_consulta(self):
        self.client.force_login(self.almacenista)
        url = reverse("panel_almacen")
        primero = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(primero.status_code, 200)
        self.assertContains(primero, 'data-sr-live="almacen-por-preparar"')
        solicitud = self.nueva_solicitud()
        segundo = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(segundo.status_code, 200)
        self.assertContains(segundo, f"Ver solicitud #{solicitud.pk}")
        self.assertNotIn(f"Ver solicitud #{solicitud.pk}".encode(), primero.content)

    def test_cambio_de_estado_actualiza_ambas_secciones_del_almacen(self):
        solicitud = self.nueva_solicitud()
        self.client.force_login(self.almacenista)
        url = reverse("panel_almacen")
        primero = self.client.get(url)
        self.assertContains(primero, f"Ver solicitud #{solicitud.pk}")
        solicitud.status = MaterialRequest.Status.PREPARED
        solicitud.save(update_fields=["status"])
        segundo = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(segundo.status_code, 200)
        self.assertContains(segundo, 'data-sr-live="almacen-por-confirmar"')
        # La solicitud sigue apareciendo, ahora entre las pendientes de confirmar.
        self.assertContains(segundo, f"Ver solicitud #{solicitud.pk}")
        self.assertNotEqual(primero.content, segundo.content)

    def test_trabajador_ve_solicitud_nueva_en_siguiente_consulta(self):
        self.autenticar_trabajador()
        url = reverse("panel_empleado")
        primero = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(primero.status_code, 200)
        solicitud = self.nueva_solicitud()
        segundo = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(segundo.status_code, 200)
        self.assertContains(segundo, 'data-sr-live="trabajador-solicitudes"')
        self.assertContains(segundo, f"Solicitud #{solicitud.pk}")
        self.assertNotIn(f"Solicitud #{solicitud.pk}".encode(), primero.content)

    def test_consultas_ajax_no_alteran_solicitudes(self):
        solicitud = self.nueva_solicitud()
        self.client.force_login(self.almacenista)
        antes = list(MaterialRequest.objects.values_list("pk", "status"))
        for _ in range(3):
            respuesta = self.client.get(
                reverse("panel_almacen"), HTTP_X_REQUESTED_WITH="XMLHttpRequest"
            )
            self.assertEqual(respuesta.status_code, 200)
        despues = list(MaterialRequest.objects.values_list("pk", "status"))
        self.assertEqual(antes, despues)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.status, MaterialRequest.Status.SUBMITTED)
