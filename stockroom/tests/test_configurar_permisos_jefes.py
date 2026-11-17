
"""Pruebas del comando de configuración del grupo Jefes."""

from io import StringIO

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase


class ConfigurarPermisosJefesTests(TestCase):

    def test_revision_no_modifica_grupos(self):
        salida = StringIO()

        call_command(
            "configurar_permisos_jefes",
            stdout=salida,
        )

        self.assertFalse(
            Group.objects.filter(name="Jefes").exists()
        )
        self.assertIn("Modo revisión", salida.getvalue())

    def test_aplicacion_configura_seis_permisos(self):
        call_command(
            "configurar_permisos_jefes",
            "--apply",
            stdout=StringIO(),
        )

        grupo = Group.objects.get(name="Jefes")

        permisos = set(
            grupo.permissions.values_list(
                "codename", flat=True
            )
        )

        esperados = {
            "view_materialrequest",
            "view_employee",
            "view_quantityissue",
            "view_article",
            "view_quantitystock",
            "view_tool",
        }

        self.assertEqual(permisos, esperados)

        # Ejecutar nuevamente no debe duplicar permisos.
        call_command(
            "configurar_permisos_jefes",
            "--apply",
            stdout=StringIO(),
        )

        self.assertEqual(
            grupo.permissions.count(),
            6,
        )
