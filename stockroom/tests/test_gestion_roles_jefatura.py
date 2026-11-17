
"""Fase 20I: administración segura de cuentas y roles."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse


class GestionRolesJefaturaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        # Configuramos los permisos únicamente en la BD de pruebas.
        call_command(
            "configurar_permisos_jefes",
            "--apply",
            verbosity=0,
        )

        cls.grupo_jefes = Group.objects.get(name="Jefes")

        cls.jefe = User.objects.create_user(
            username="jefe_roles_20i",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )
        cls.jefe.groups.add(cls.grupo_jefes)

        cls.cuenta = User.objects.create_user(
            username="cuenta_roles_20i",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )

    def setUp(self):
        self.client.force_login(self.jefe)

    def test_crear_cuenta_con_rol_jefatura(self):
        response = self.client.post(
            reverse("personal_jefe"),
            {
                "tipo": "cuenta",
                "cuenta-username": "nuevo_jefe_20i",
                "cuenta-first_name": "Nuevo",
                "cuenta-last_name": "Responsable",
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
        nuevo = User.objects.get(username="nuevo_jefe_20i")

        self.assertTrue(nuevo.is_staff)
        self.assertTrue(nuevo.is_active)
        self.assertFalse(nuevo.is_superuser)
        self.assertTrue(nuevo.groups.filter(name="Jefes").exists())

        self.assertTrue(
            nuevo.has_perm("stockroom.view_quantitystock")
        )
        self.assertFalse(
            nuevo.has_perm("stockroom.add_damageresolution")
        )

    def test_cambiar_cuenta_a_jefatura(self):
        response = self.client.post(
            reverse("estado_cuenta_jefe", args=[self.cuenta.pk]),
            {"accion": "boss"},
        )

        self.assertRedirects(
            response,
            reverse("personal_jefe"),
        )

        self.cuenta.refresh_from_db()

        self.assertTrue(self.cuenta.is_staff)
        self.assertTrue(
            self.cuenta.groups.filter(name="Jefes").exists()
        )
        self.assertFalse(self.cuenta.is_superuser)

    def test_no_puede_modificar_su_propia_cuenta(self):
        response = self.client.post(
            reverse("estado_cuenta_jefe", args=[self.jefe.pk]),
            {"accion": "desactivar"},
        )

        self.assertEqual(response.status_code, 403)

        self.jefe.refresh_from_db()
        self.assertTrue(self.jefe.is_active)

    def test_no_puede_modificar_superusuario(self):
        User = get_user_model()

        superusuario = User.objects.create_superuser(
            username="superusuario_protegido_20i",
            password="ClaveTemporalSegura123!",
        )

        response = self.client.post(
            reverse("estado_cuenta_jefe", args=[superusuario.pk]),
            {"accion": "warehouse"},
        )

        self.assertEqual(response.status_code, 403)

        superusuario.refresh_from_db()
        self.assertTrue(superusuario.is_superuser)
