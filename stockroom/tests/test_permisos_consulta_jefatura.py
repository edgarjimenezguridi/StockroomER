
"""Fase 20F: permisos de consulta para jefatura."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse


class PermisosConsultaJefaturaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.grupo = Group.objects.create(
            name="Jefes"
        )

        cls.jefe = User.objects.create_user(
            username="jefe_consulta_20f",
            password="ClaveTemporalSegura123!",
            is_staff=True,
            is_superuser=False,
        )
        cls.jefe.groups.add(cls.grupo)

        cls.permisos_lectura = (
            "view_materialrequest",
            "view_employee",
            "view_quantityissue",
            "view_article",
            "view_quantitystock",
            "view_tool",
        )

    def asignar_permisos_consulta(self):
        permisos = Permission.objects.filter(
            content_type__app_label="stockroom",
            codename__in=self.permisos_lectura,
        )

        self.assertEqual(
            permisos.count(),
            len(self.permisos_lectura),
        )

        self.grupo.permissions.add(*permisos)

        # Evitar usar caché de permisos del usuario.
        self.jefe = type(self.jefe).objects.get(
            pk=self.jefe.pk
        )

    def test_jefe_con_permisos_puede_consultar_alertas(self):
        self.asignar_permisos_consulta()
        self.client.force_login(self.jefe)

        rutas = (
            "panel_almacen",
            "adeudos_almacen",
            "reabastecimiento_almacen",
            "danos_pendientes_jefe",
        )

        for nombre in rutas:
            with self.subTest(ruta=nombre):
                response = self.client.get(reverse(nombre))
                self.assertEqual(response.status_code, 200)

    def test_permisos_consulta_no_autorizan_resolver_danos(self):
        self.asignar_permisos_consulta()
        self.client.force_login(self.jefe)

        self.assertFalse(
            self.jefe.has_perm(
                "stockroom.add_damageresolution"
            )
        )

        response = self.client.get(
            reverse("resolver_dano_almacen")
        )

        self.assertEqual(response.status_code, 403)

    def test_jefe_sin_permisos_extra_no_consulta_almacen(self):
        self.client.force_login(self.jefe)

        for nombre in (
            "panel_almacen",
            "adeudos_almacen",
            "reabastecimiento_almacen",
        ):
            with self.subTest(ruta=nombre):
                response = self.client.get(reverse(nombre))
                self.assertEqual(response.status_code, 403)

        # La consulta exclusiva de jefatura sí está autorizada.
        response = self.client.get(
            reverse("danos_pendientes_jefe")
        )
        self.assertEqual(response.status_code, 200)
