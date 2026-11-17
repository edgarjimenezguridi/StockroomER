
"""Fase 20R: filtros combinados y seguridad del historial."""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee


class FiltrosHistorialJefeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_superuser(
            username="jefe_filtros_20r",
            password="ClaveTemporalSegura123!",
        )

        cls.otro = User.objects.create_user(
            username="otro_auditor_20r",
            password="ClaveTemporalSegura123!",
            is_staff=True,
        )

        tipo = ContentType.objects.get_for_model(Employee)

        registros = []

        for numero in range(35):
            registros.append(
                LogEntry(
                    user=cls.jefe,
                    content_type=tipo,
                    object_id=str(numero + 1),
                    object_repr=f"TRABAJADOR_20R_{numero:03d}",
                    action_flag=CHANGE,
                    change_message=(
                        "Actualización de datos de trabajador"
                    ),
                )
            )

        registros.append(
            LogEntry(
                user=cls.otro,
                content_type=tipo,
                object_id="999",
                object_repr="TRABAJADOR_OTRO_20R",
                action_flag=CHANGE,
                change_message=(
                    "Actualización de datos de trabajador"
                ),
            )
        )

        LogEntry.objects.bulk_create(registros)

    def setUp(self):
        self.client.force_login(self.jefe)
        self.url = reverse("auditoria_jefe")

    def test_filtros_combinados(self):
        response = self.client.get(
            self.url,
            {
                "categoria": "datos",
                "q": "TRABAJADOR_20R",
                "responsable": "jefe_filtros_20r",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 35)
        self.assertEqual(
            len(response.context["eventos"]),
            25,
        )

        self.assertNotContains(
            response,
            "TRABAJADOR_OTRO_20R",
        )

    def test_segunda_pagina_conserva_resultados(self):
        response = self.client.get(
            self.url,
            {
                "categoria": "datos",
                "q": "TRABAJADOR_20R",
                "responsable": "jefe_filtros_20r",
                "page": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 35)
        self.assertEqual(
            len(response.context["eventos"]),
            10,
        )
        self.assertEqual(
            response.context["pagina"].number,
            2,
        )

    def test_historial_no_acepta_post(self):
        response = self.client.post(
            self.url,
            {"categoria": "datos"},
        )

        self.assertEqual(response.status_code, 405)
