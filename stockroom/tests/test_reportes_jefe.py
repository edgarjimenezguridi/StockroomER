from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse


class ReportesJefeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.jefe = User.objects.create_user('jefe_pdf', password='ClaveDePrueba123!', is_staff=True)
        cls.jefe.groups.add(Group.objects.get_or_create(name='Jefes')[0])
        cls.almacen = User.objects.create_user('almacen_pdf', password='ClaveDePrueba123!', is_staff=True)

    def test_no_autenticado_se_redirige_a_acceso_jefe(self):
        response = self.client.get(reverse('reportes_jefe'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('acceso_jefe'), response.url)

    def test_almacenista_no_puede_ver_ni_descargar(self):
        self.client.force_login(self.almacen)
        self.assertEqual(self.client.get(reverse('reportes_jefe')).status_code, 403)
        self.assertEqual(self.client.get(reverse('descargar_reporte_jefe'), {'tipo': 'auditoria'}).status_code, 403)

    def test_jefe_descarga_pdf_valido_sin_datos(self):
        self.client.force_login(self.jefe)
        for tipo in ('auditoria', 'vencidos', 'desechos', 'minimos'):
            with self.subTest(tipo=tipo):
                response = self.client.get(reverse('descargar_reporte_jefe'), {'tipo': tipo})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assertTrue(response.content.startswith(b'%PDF-'))
                self.assertIn(
                    "no-store",
                    response["Cache-Control"].split(", "),
                )

    def test_filtros_invalidos_son_rechazados(self):
        self.client.force_login(self.jefe)
        for filtros in ({'tipo':'desconocido'}, {'tipo':'desechos','periodo':'999'},
                        {'tipo':'auditoria','desde':'2026-14-99'},
                        {'tipo':'auditoria','desde':'2026-09-10','hasta':'2026-08-10'}):
            with self.subTest(filtros=filtros):
                self.assertEqual(self.client.get(reverse('descargar_reporte_jefe'), filtros).status_code, 400)

    def test_no_permite_generar_por_post(self):
        self.client.force_login(self.jefe)
        self.assertEqual(self.client.post(reverse('descargar_reporte_jefe'), {'tipo':'desechos'}).status_code, 405)
