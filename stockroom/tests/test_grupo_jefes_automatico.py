
"""Fase 20J: permisos automáticos para cuentas de jefatura."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse


class GrupoJefesAutomaticoTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.admin = User.objects.create_superuser(
            username="admin_roles_20j",
            password="ClaveTemporalSegura123!",
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def test_crear_jefe_configura_grupo_desde_cero(self):
        self.assertFalse(
            Group.objects.filter(name="Jefes").exists()
        )

        response = self.client.post(
            reverse("personal_jefe"),
            {
                "tipo": "cuenta",
                "cuenta-username": "nuevo_jefe_20j",
                "cuenta-first_name": "Nuevo",
                "cuenta-last_name": "Jefe",
                "cuenta-email": "",
                "cuenta-role": "boss",
                "cuenta-password": "ClaveSeguraProyecto2026!",
            },
        )

        self.assertRedirects(
            response,
            reverse("personal_jefe"),
        )

        User = get_user_model()
        jefe = User.objects.get(username="nuevo_jefe_20j")

        self.assertTrue(
            jefe.groups.filter(name="Jefes").exists()
        )
        self.assertTrue(
            jefe.has_perm("stockroom.view_quantitystock")
        )
        self.assertFalse(
            jefe.has_perm("stockroom.add_damageresolution")
        )
        self.assertFalse(jefe.is_superuser)

    def test_cambiar_rol_completa_permisos_faltantes(self):
        grupo = Group.objects.create(name="Jefes")

        self.assertEqual(grupo.permissions.count(), 0)

        User = get_user_model()
        cuenta = User.objects.create_user(
            username="cambio_rol_20j",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )

        response = self.client.post(
            reverse("estado_cuenta_jefe", args=[cuenta.pk]),
            {"accion": "boss"},
        )

        self.assertRedirects(
            response,
            reverse("personal_jefe"),
        )

        grupo.refresh_from_db()
        cuenta.refresh_from_db()

        self.assertEqual(grupo.permissions.count(), 6)
        self.assertTrue(
            cuenta.groups.filter(name="Jefes").exists()
        )
        self.assertTrue(
            cuenta.has_perm("stockroom.view_materialrequest")
        )
        self.assertFalse(
            cuenta.has_perm("stockroom.add_damageresolution")
        )
