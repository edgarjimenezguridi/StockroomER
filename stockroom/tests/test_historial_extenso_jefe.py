
"""Fase 20P: historial administrativo sin límite de 200 eventos."""

from datetime import timedelta

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stockroom.models import Employee


class HistorialExtensoJefeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_superuser(
            username="jefe_historial_20p",
            password="ClaveTemporalSegura123!",
        )

        tipo = ContentType.objects.get_for_model(Employee)

        cls.base = timezone.now()

        registros = []

        for i in range(250):
            registros.append(
                LogEntry(
                    user=cls.jefe,
                    content_type=tipo,
                    object_id=str(i + 1),
                    object_repr=f"TRABAJADOR_20P_{i:03d}",
                    action_flag=CHANGE,
                    change_message=(
                        "Actualización de datos de trabajador"
                    ),
                    action_time=cls.base - timedelta(minutes=i),
                )
            )

        LogEntry.objects.bulk_create(registros)

    def setUp(self):
        self.client.force_login(self.jefe)

    def test_historial_conserva_250_eventos(self):
        response = self.client.get(
            reverse("auditoria_jefe"),
            {"categoria": "datos"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 250)

        self.assertEqual(
            response.context["pagina"].paginator.num_pages,
            10,
        )

    def test_ultima_pagina_muestra_eventos_antiguos(self):
        response = self.client.get(
            reverse("auditoria_jefe"),
            {"categoria": "datos", "page": "10"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.context["eventos"]),
            25,
        )

        self.assertContains(
            response,
            "TRABAJADOR_20P_249",
        )

    def test_busqueda_encuentra_evento_antiguo(self):
        response = self.client.get(
            reverse("auditoria_jefe"),
            {"q": "TRABAJADOR_20P_249"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["total"], 1)

        self.assertContains(
            response,
            "TRABAJADOR_20P_249",
        )
