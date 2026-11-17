
"""Fase 20M: protecciones de cuentas administrativas."""

from unittest.mock import patch

from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase
from django.urls import reverse


class SeguridadCuentasJefaturaTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.grupo_jefes = Group.objects.create(
            name="Jefes"
        )

        cls.jefe = User.objects.create_user(
            username="jefe_seguridad_20m",
            password="ClaveTemporalSegura123!",
            is_staff=True,
            is_active=True,
        )
        cls.jefe.groups.add(cls.grupo_jefes)

        cls.operador = User.objects.create_user(
            username="operador_seguridad_20m",
            password="ClaveTemporalSegura123!",
            is_staff=True,
            is_active=True,
        )

    def test_no_desactivar_ultimo_jefe(self):
        User = get_user_model()

        administrador = User.objects.create_superuser(
            username="admin_ultimo_jefe_20m",
            password="ClaveTemporalSegura123!",
        )

        self.client.force_login(administrador)

        # Simulamos que solo queda un jefe activo.
        with patch(
            "stockroom.boss_personnel_views._jefes_activos",
            return_value=1,
        ):
            for accion in ("desactivar", "warehouse"):
                with self.subTest(accion=accion):
                    response = self.client.post(
                        reverse(
                            "estado_cuenta_jefe",
                            args=[self.jefe.pk],
                        ),
                        {"accion": accion},
                    )

                    self.assertEqual(
                        response.status_code,
                        403,
                    )

                    self.jefe.refresh_from_db()

                    self.assertTrue(
                        self.jefe.is_active
                    )
                    self.assertTrue(
                        self.jefe.groups.filter(
                            name="Jefes"
                        ).exists()
                    )

    def test_no_cambiar_su_propio_rol(self):
        self.client.force_login(self.jefe)

        response = self.client.post(
            reverse(
                "estado_cuenta_jefe",
                args=[self.jefe.pk],
            ),
            {"accion": "warehouse"},
        )

        self.assertEqual(response.status_code, 403)

        self.assertTrue(
            self.jefe.groups.filter(
                name="Jefes"
            ).exists()
        )

    def test_no_modificar_cuenta_con_permisos_avanzados(self):
        User = get_user_model()

        administrador = User.objects.create_superuser(
            username="admin_avanzados_20m",
            password="ClaveTemporalSegura123!",
        )

        self.client.force_login(administrador)

        permiso = Permission.objects.get(
            content_type__app_label="auth",
            codename="change_user",
        )

        self.operador.user_permissions.add(permiso)

        response = self.client.post(
            reverse(
                "estado_cuenta_jefe",
                args=[self.operador.pk],
            ),
            {"accion": "boss"},
        )

        self.assertEqual(response.status_code, 403)

        self.assertFalse(
            self.operador.groups.filter(
                name="Jefes"
            ).exists()
        )

    def test_usuario_no_autorizado_no_gestiona_cuentas(self):
        self.client.force_login(self.operador)

        auditorias_antes = LogEntry.objects.count()

        response = self.client.post(
            reverse(
                "estado_cuenta_jefe",
                args=[self.jefe.pk],
            ),
            {"accion": "desactivar"},
        )

        self.assertEqual(response.status_code, 403)

        self.jefe.refresh_from_db()

        self.assertTrue(self.jefe.is_active)

        self.assertEqual(
            LogEntry.objects.count(),
            auditorias_antes,
        )
