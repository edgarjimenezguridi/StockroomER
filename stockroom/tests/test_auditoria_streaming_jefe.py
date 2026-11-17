"""Fase 20T: paginación con memoria limitada y filtros cronológicos."""
from datetime import timedelta

from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stockroom.boss_audit_views import audit_entries
from stockroom.models import Employee


class AuditoriaStreamingJefeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.jefe = User.objects.create_superuser(
            username='jefe_stream_20t',
            password='ClaveTemporalSegura123!',
        )
        cls.otro = User.objects.create_user(
            username='otro_stream_20t',
            password='ClaveTemporalSegura123!',
            is_staff=True,
        )
        tipo = ContentType.objects.get_for_model(Employee)
        momento = timezone.now()
        LogEntry.objects.bulk_create([
            LogEntry(
                user=cls.jefe if numero < 60 else cls.otro,
                content_type=tipo,
                object_id=str(numero),
                object_repr=f'TRABAJADOR_STREAM_{numero:03d}',
                action_flag=CHANGE,
                action_time=momento - timedelta(minutes=numero),
                change_message='Actualización de datos de trabajador',
            )
            for numero in range(75)
        ])

    def setUp(self):
        self.client.force_login(self.jefe)

    def test_paginas_y_total_con_75_eventos(self):
        url = reverse('auditoria_jefe')
        inicio = self.client.get(url, {'categoria': 'datos'})
        final = self.client.get(url, {'categoria': 'datos', 'page': 3})
        self.assertEqual(inicio.context['total'], 75)
        self.assertEqual(len(inicio.context['eventos']), 25)
        self.assertEqual(len(final.context['eventos']), 25)
        self.assertEqual(final.context['pagina'].number, 3)
        self.assertContains(final, 'TRABAJADOR_STREAM_074')

    def test_responsable_y_compatibilidad_de_audit_entries(self):
        response = self.client.get(
            reverse('auditoria_jefe'),
            {'categoria': 'datos', 'responsable': 'otro_stream_20t'},
        )
        self.assertEqual(response.context['total'], 15)
        self.assertEqual(len(response.context['eventos']), 15)
        self.assertNotContains(response, 'TRABAJADOR_STREAM_059')

        events = audit_entries(categoria='datos')
        self.assertEqual(len(events), 75)
        self.assertEqual(events[0]['subject'], 'TRABAJADOR_STREAM_000')
