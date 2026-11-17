
"""Fase 20O: paginación del historial administrativo."""

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse

from stockroom.models import Employee


class PaginacionAuditoriaJefeTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.jefe = User.objects.create_superuser(
            username="jefe_paginacion_20o",
            password="ClaveTemporalSegura123!",
        )

        tipo = ContentType.objects.get_for_model(Employee)

        LogEntry.objects.bulk_create([
            LogEntry(
                user=cls.jefe,
                content_type=tipo,
                object_id=str(i),
                object_repr=f"TRABAJADOR_20O_{i}",
                action_flag=CHANGE,
                change_message=(
                    "Actualización de datos de trabajador"
                ),
            )
            for i in range(30)
        ])

    def setUp(self):
        self.client.force_login(self.jefe)

    def test_historial_se_divide_en_paginas(self):
        url = reverse("auditoria_jefe")

        primera = self.client.get(
            url,
            {"categoria": "datos"},
        )

        self.assertEqual(primera.status_code, 200)
        self.assertEqual(primera.context["total"], 30)
        self.assertEqual(
            len(primera.context["eventos"]),
            25,
        )

        segunda = self.client.get(
            url,
            {"categoria": "datos", "page": "2"},
        )

        self.assertEqual(segunda.status_code, 200)
        self.assertEqual(
            len(segunda.context["eventos"]),
            5,
        )
        self.assertEqual(
            segunda.context["pagina"].number,
            2,
        )

    def test_pagina_invalida_no_genera_error(self):
        response = self.client.get(
            reverse("auditoria_jefe"),
            {"categoria": "datos", "page": "invalida"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["pagina"].number,
            1,
        )
