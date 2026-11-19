"""Libro de códigos de barras: clasificación, disponibilidad y permisos."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from stockroom.libro_codigos_pdf import registros_disponibles
from stockroom.models import (
    Article, QuantityStock, Tool, ToolCategory, ToolSpecification, ToolType,
)


class LibroCodigos24ATests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.categoria = ToolCategory.objects.create(name="Medición")
        cls.tipo = ToolType.objects.create(name="Calibradores", category=cls.categoria)
        cls.especificacion = ToolSpecification.objects.create(
            name="0–150 mm", tool_type=cls.tipo
        )
        cls.cantidad = Article.objects.create(
            article_code="CAL-001", name="Calibrador por cantidad",
            tracking_mode=Article.TrackingMode.QUANTITY,
            specification=cls.especificacion,
        )
        QuantityStock.objects.create(article=cls.cantidad, available_quantity=5)
        cls.sin_stock = Article.objects.create(
            article_code="CAL-002", name="Sin stock",
            tracking_mode=Article.TrackingMode.QUANTITY,
            specification=cls.especificacion,
        )
        QuantityStock.objects.create(article=cls.sin_stock, available_quantity=0)
        cls.individual = Article.objects.create(
            article_code="VER-001", name="Vernier digital",
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
            specification=cls.especificacion,
        )
        cls.pieza = Tool.objects.create(
            article=cls.individual, tool_code="PIEZA-0001",
            name="Vernier", inventory_status=Tool.InventoryStatus.AVAILABLE,
        )
        Tool.objects.create(
            article=cls.individual, tool_code="PIEZA-0002", name="Vernier",
            inventory_status=Tool.InventoryStatus.LOANED,
        )
        Tool.objects.create(
            article=cls.individual, tool_code="PIEZA-0003", name="Vernier",
            inventory_status=Tool.InventoryStatus.QUARANTINE,
        )
        cls.user = get_user_model().objects.create_user(
            username="almacencodigos", password="prueba-segura", is_staff=True,
        )
        cls.user.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="stockroom",
            codename__in=[
                "view_materialrequest", "view_article", "view_tool", "view_quantitystock",
            ],
        ))

    def test_solo_incluye_codigos_disponibles(self):
        filas = registros_disponibles()
        codigos = [dato["codigo"] for _, dato in filas]
        self.assertEqual(codigos, ["CAL-001", "PIEZA-0001"])
        self.assertEqual(filas[0][0], ("Medición", "Calibradores", "0–150 mm"))
        self.assertEqual(filas[0][1]["detalle"], "Disponibles: 5")

    def test_inactivos_no_aparecen(self):
        self.cantidad.is_active = False
        self.cantidad.save(update_fields=["is_active"])
        self.pieza.is_active = False
        self.pieza.save(update_fields=["is_active"])
        self.assertEqual(registros_disponibles(), [])

    def test_pdf_con_codigo_legible(self):
        self.client.force_login(self.user)
        respuesta = self.client.get(
            reverse("descargar_reporte_almacen"), {"tipo": "libro_codigos"}
        )
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "application/pdf")
        contenido = b"".join(respuesta.streaming_content)
        self.assertTrue(contenido.startswith(b"%PDF-"))
        from pypdf import PdfReader
        import io
        texto = " ".join(p.extract_text() for p in PdfReader(io.BytesIO(contenido)).pages)
        for texto_esperado in ("CAL-001", "PIEZA-0001", "Calibradores"):
            self.assertIn(texto_esperado, texto)
        self.assertNotIn("PIEZA-0002", texto)
        self.assertNotIn("CAL-002", texto)

    def test_sin_permiso_rechazado(self):
        usuario = get_user_model().objects.create_user(
            username="sinreportes", password="prueba-segura", is_staff=True,
        )
        usuario.user_permissions.add(Permission.objects.get(
            content_type__app_label="stockroom", codename="view_materialrequest",
        ))
        self.client.force_login(usuario)
        respuesta = self.client.get(
            reverse("descargar_reporte_almacen"), {"tipo": "libro_codigos"}
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_tipo_aparece_en_selector(self):
        self.client.force_login(self.user)
        respuesta = self.client.get(reverse("generar_reportes_almacen"))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'value="libro_codigos"')
