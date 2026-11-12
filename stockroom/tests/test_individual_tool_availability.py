
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from stockroom.models import (
    Article,
    Employee,
    Loan,
    QuantityIssue,
    Tool,
)


class IndividualToolAvailabilityTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()

        cls.usuario = User.objects.create_superuser(
            username="test_almacen_disponibilidad",
            email="test@example.com",
            password="ClaveTemporalDePrueba123!",
        )

        cls.empleado = Employee.objects.create(
            employee_id="TEST-900",
            first_name="Trabajador",
            last_name="Prueba",
            is_active=True,
        )

        cls.articulo = Article.objects.create(
            article_code="TEST-CAL-001",
            name="Calibrador digital de prueba",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            return_mode=Article.ReturnMode.RETURNABLE,
            is_active=True,
        )

        def crear_pieza(codigo, estado, activa=True):
            return Tool.objects.create(
                article=cls.articulo,
                tool_code=codigo,
                name="Calibrador de prueba",
                inventory_status=estado,
                is_active=activa,
            )

        cls.disponible = crear_pieza(
            "TEST-DISP-001",
            Tool.InventoryStatus.AVAILABLE,
        )

        cls.prestada = crear_pieza(
            "TEST-PREST-001",
            Tool.InventoryStatus.LOANED,
        )

        cls.revision = crear_pieza(
            "TEST-REV-001",
            Tool.InventoryStatus.QUARANTINE,
        )

        cls.consumida = crear_pieza(
            "TEST-CONS-001",
            Tool.InventoryStatus.CONSUMED,
        )

        cls.baja = crear_pieza(
            "TEST-BAJA-001",
            Tool.InventoryStatus.SCRAPPED,
        )

        cls.inactiva = crear_pieza(
            "TEST-INACT-001",
            Tool.InventoryStatus.AVAILABLE,
            activa=False,
        )

        # Simular una inconsistencia: la pieza aparece
        # disponible, pero tiene una entrega abierta.
        cls.entrega_pendiente = crear_pieza(
            "TEST-PEND-001",
            Tool.InventoryStatus.AVAILABLE,
        )

        QuantityIssue.objects.create(
            tool=cls.entrega_pendiente,
            employee=cls.empleado,
            quantity=1,
            returned_quantity=0,
            requires_return=True,
            issued_at=timezone.now(),
        )

        # Simular un préstamo antiguo que sigue abierto.
        cls.prestamo_legacy = crear_pieza(
            "TEST-LEG-001",
            Tool.InventoryStatus.AVAILABLE,
        )

        Loan.objects.create(
            tool=cls.prestamo_legacy,
            employee=cls.empleado,
            borrowed_at=timezone.now(),
        )

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse(
            "consultar_piezas_individuales_almacen"
        )

    def obtener_piezas(self, parametros=None):
        respuesta = self.client.get(
            self.url,
            parametros or {},
        )

        self.assertEqual(respuesta.status_code, 200)

        return respuesta, list(
            respuesta.context["piezas"]
        )

    def test_todos_los_estados_se_muestran_correctamente(self):
        respuesta, piezas = self.obtener_piezas()

        estados = {
            pieza.tool_code: pieza.estado_clave
            for pieza in piezas
        }

        esperados = {
            "TEST-DISP-001": "disponible",
            "TEST-PREST-001": "prestada",
            "TEST-REV-001": "revision",
            "TEST-CONS-001": "consumida",
            "TEST-BAJA-001": "baja",
            "TEST-INACT-001": "inactiva",
            "TEST-PEND-001": "prestada",
            "TEST-LEG-001": "prestada",
        }

        self.assertEqual(estados, esperados)

        self.assertEqual(
            respuesta.context["total_piezas"],
            8,
        )

    def test_disponibles_excluye_prestadas_y_danadas(self):
        _, piezas = self.obtener_piezas({
            "estado": "disponible",
        })

        codigos = {
            pieza.tool_code
            for pieza in piezas
        }

        self.assertEqual(
            codigos,
            {"TEST-DISP-001"},
        )

    def test_prestadas_incluye_entregas_y_legacy(self):
        _, piezas = self.obtener_piezas({
            "estado": "prestada",
        })

        codigos = {
            pieza.tool_code
            for pieza in piezas
        }

        self.assertEqual(
            codigos,
            {
                "TEST-PREST-001",
                "TEST-PEND-001",
                "TEST-LEG-001",
            },
        )

    def test_filtros_de_estados_especiales(self):
        casos = {
            "revision": "TEST-REV-001",
            "consumida": "TEST-CONS-001",
            "baja": "TEST-BAJA-001",
            "inactiva": "TEST-INACT-001",
        }

        for filtro, codigo_esperado in casos.items():
            with self.subTest(estado=filtro):
                _, piezas = self.obtener_piezas({
                    "estado": filtro,
                })

                codigos = {
                    pieza.tool_code
                    for pieza in piezas
                }

                self.assertEqual(
                    codigos,
                    {codigo_esperado},
                )

    def test_muestra_trabajador_de_entrega_unificada(self):
        _, piezas = self.obtener_piezas({
            "q": "TEST-PEND-001",
        })

        self.assertEqual(len(piezas), 1)

        pieza = piezas[0]

        self.assertEqual(
            pieza.estado_clave,
            "prestada",
        )

        self.assertEqual(
            pieza.trabajador_responsable.pk,
            self.empleado.pk,
        )

        self.assertIsNotNone(
            pieza.fecha_prestamo,
        )

    def test_busqueda_por_codigo_funciona(self):
        _, piezas = self.obtener_piezas({
            "q": "TEST-REV-001",
        })

        self.assertEqual(len(piezas), 1)

        self.assertEqual(
            piezas[0].tool_code,
            "TEST-REV-001",
        )

    def test_usuario_sin_permiso_no_puede_consultar(self):
        User = get_user_model()

        usuario = User.objects.create_user(
            username="test_sin_permiso",
            password="ClaveTemporalDePrueba456!",
            is_staff=True,
        )

        self.client.force_login(usuario)

        respuesta = self.client.get(self.url)

        self.assertEqual(
            respuesta.status_code,
            403,
        )
