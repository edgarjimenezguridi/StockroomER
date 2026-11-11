from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from django.conf import settings
import uuid


class Employee(models.Model):
    employee_id = models.CharField(
        "Número de empleado",
        max_length=20,
        unique=True,
    )
    first_name = models.CharField("Nombre(s)", max_length=100)
    last_name = models.CharField("Apellidos", max_length=100)
    is_active = models.BooleanField("Activo", default=True)

    class Meta:
        verbose_name = "Trabajador"
        verbose_name_plural = "Trabajadores"
        ordering = ["last_name", "first_name"]

    def __str__(self):
        return f"{self.employee_id} - {self.first_name} {self.last_name}"
    
class EmployeeCredential(models.Model):
    employee = models.OneToOneField(
        Employee,
        on_delete=models.PROTECT,
        related_name="credential",
        verbose_name="Trabajador",
    )
    barcode = models.UUIDField(
        "Código de credencial",
        default=uuid.uuid4,
        unique=True,
        editable=False,
    )
    is_active = models.BooleanField("Credencial activa", default=True)
    
    pin_hash = models.CharField(
        "NIP verificado mediante hash",
        max_length=255,
        blank=True,
        default="",
        editable=False,
    )
    pin_fingerprint = models.CharField(
        "Huella de unicidad del NIP",
        max_length=64,
        unique=True,
        null=True,
        blank=True,
        editable=False,
    )
    
    failed_pin_attempts = models.PositiveIntegerField(
        "Intentos de NIP fallidos",
        default=0,
        editable=False,
    )
    pin_locked_until = models.DateTimeField(
        "NIP bloqueado hasta",
        null=True,
        blank=True,
        editable=False,
    )

    class Meta:
        verbose_name = "Credencial de empleado"
        verbose_name_plural = "Credenciales de empleados"

    def __str__(self):
        return f"Credencial de {self.employee}"
    
class ToolCategory(models.Model):
    name = models.CharField(
        "Nombre de la categoría",
        max_length=100,
        unique=True,
    )
    description = models.TextField(
        "Descripción",
        blank=True,
    )

    class Meta:
        verbose_name = "Categoría de herramienta"
        verbose_name_plural = "Categorías de herramientas"
        ordering = ["name"]

    def __str__(self):
        return self.name
    
class ToolType(models.Model):
    category = models.ForeignKey(
        ToolCategory,
        on_delete=models.PROTECT,
        verbose_name="Categoría",
        related_name="tool_types",
    )
    name = models.CharField(
        "Nombre del tipo",
        max_length=100,
    )

    class Meta:
        verbose_name = "Tipo de herramienta"
        verbose_name_plural = "Tipos de herramientas"
        ordering = ["category__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "name"],
                name="unique_tool_type_per_category",
                violation_error_message=(
                    "Este tipo de herramienta ya existe en esta categoría."
                ),
            ),
        ]

    def __str__(self):
        return f"{self.category.name} → {self.name}"
    

class ToolSpecification(models.Model):
    tool_type = models.ForeignKey(
        ToolType,
        on_delete=models.PROTECT,
        verbose_name="Tipo de herramienta",
        related_name="specifications",
    )
    name = models.CharField(
        "Especificación",
        max_length=150,
        help_text="Ejemplos: M6 × 1.0, diámetro 10 mm o rango 0–25 mm.",
    )
    description = models.TextField(
        "Descripción",
        blank=True,
    )

    class Meta:
        verbose_name = "Especificación de herramienta"
        verbose_name_plural = "Especificaciones de herramientas"
        ordering = ["tool_type__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tool_type", "name"],
                name="unique_specification_per_tool_type",
                violation_error_message=(
                    "Esta especificación ya existe para este tipo de herramienta."
                ),
            ),
        ]

    def __str__(self):
        return f"{self.tool_type} → {self.name}"

class Article(models.Model):
    class TrackingMode(models.TextChoices):
        QUANTITY = "quantity", "Por cantidad"
        INDIVIDUAL = "individual", "Por pieza individual"

    class ReturnMode(models.TextChoices):
        RETURNABLE = "returnable", "Con devolución"
        CONSUMABLE = "consumable", "Consumible sin devolución"

    article_code = models.CharField(
        "Código de artículo",
        max_length=30,
        unique=True,
    )
    name = models.CharField(
        "Nombre del artículo",
        max_length=150,
    )
    specification = models.ForeignKey(
        ToolSpecification,
        on_delete=models.PROTECT,
        verbose_name="Especificación",
        related_name="articles",
        null=True,
        blank=True,
    )
    brand = models.CharField(
        "Marca",
        max_length=100,
        blank=True,
    )
    location = models.CharField(
        "Ubicación principal en almacén",
        max_length=150,
        blank=True,
        default="",
        help_text=(
            "Ejemplo: Estante A, nivel 2, "
            "cajón 4. Si no tiene ubicación, dejar vacío."
        ),
    )
    tracking_mode = models.CharField(
        "Forma de control",
        max_length=20,
        choices=TrackingMode.choices,
        default=TrackingMode.INDIVIDUAL,
    )
    return_mode = models.CharField(
        "Modalidad de devolución",
        max_length=20,
        choices=ReturnMode.choices,
        default=ReturnMode.RETURNABLE,
    )
    minimum_stock = models.PositiveIntegerField(
        "Existencia mínima",
        default=0,
        help_text=(
            "Cantidad mínima deseada. "
            "Si es 0, no se generarán alertas."
        ),
    )
    is_active = models.BooleanField(
        "Activo",
        default=True,
    )

    class Meta:
        verbose_name = "Artículo"
        verbose_name_plural = "Artículos"
        ordering = ["article_code"]

    def __str__(self):
        return f"{self.article_code} - {self.name}"

class QuantityStock(models.Model):
    article = models.OneToOneField(
        Article,
        on_delete=models.PROTECT,
        verbose_name="Artículo",
        related_name="quantity_stock",
        limit_choices_to={"tracking_mode": "quantity"},
    )
    available_quantity = models.PositiveIntegerField(
        "Disponibles",
        default=0,
    )
    loaned_quantity = models.PositiveIntegerField(
        "Prestadas",
        default=0,
    )
    quarantine_quantity = models.PositiveIntegerField(
        "Dañadas / en revisión",
        default=0,
    )
    scrapped_quantity = models.PositiveIntegerField(
        "Bajas definitivas acumuladas",
        default=0,
        editable=False,
    )

    class Meta:
        verbose_name = "Existencia por cantidad"
        verbose_name_plural = "Existencias por cantidad"

    def __str__(self):
        return f"Existencias de {self.article}"


class StockEntry(models.Model):
    stock = models.ForeignKey(
        QuantityStock,
        on_delete=models.PROTECT,
        verbose_name="Existencias del artículo",
        related_name="entries",
    )
    quantity = models.PositiveIntegerField(
        "Cantidad recibida",
        validators=[MinValueValidator(1)],
    )
    received_at = models.DateTimeField(
        "Fecha de entrada",
        default=timezone.now,
    )
    reference = models.CharField(
        "Referencia",
        max_length=150,
        blank=True,
        help_text="Número de factura, compra o inventario inicial.",
    )
    notes = models.TextField(
        "Observaciones",
        blank=True,
    )

    class Meta:
        verbose_name = "Entrada de almacén"
        verbose_name_plural = "Entradas de almacén"
        ordering = ["-received_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="stock_entry_quantity_gte_1",
            ),
        ]

    def __str__(self):
        return f"{self.stock.article.article_code} — Entrada de {self.quantity}"

class StockEntryCorrection(models.Model):
    entry = models.ForeignKey(
        StockEntry,
        on_delete=models.PROTECT,
        related_name="corrections",
        verbose_name="Entrada original",
    )
    quantity_delta = models.IntegerField(
        "Ajuste en piezas",
        help_text="Ejemplo: si registraste 10 y recibiste 8, escribe -2.",
    )
    reason = models.CharField("Motivo de la corrección", max_length=200)
    created_at = models.DateTimeField(
        "Fecha de registro",
        auto_now_add=True,
    )
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name="Registrada por",
        editable=False,
    )

    class Meta:
        verbose_name = "Corrección de entrada"
        verbose_name_plural = "Correcciones de entradas"
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity_delta=0),
                name="entry_correction_nonzero_delta",
                violation_error_message="El ajuste debe ser distinto de cero.",
            ),
        ]

    def __str__(self):
        return f"Entrada #{self.entry_id} — ajuste de {self.quantity_delta:+d}"

class Tool(models.Model):

    class InventoryStatus(models.TextChoices):
        AVAILABLE = "available", "Disponible"
        LOANED = "loaned", "Prestada"
        QUARANTINE = "quarantine", "Dañada / en revisión"
        CONSUMED = "consumed", "Entregada sin devolución"
        SCRAPPED = "scrapped", "Baja definitiva"

    inventory_status = models.CharField(
        "Estado de inventario",
        max_length=20,
        choices=InventoryStatus.choices,
        default=InventoryStatus.AVAILABLE,
        editable=False,
    )

    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        verbose_name="Artículo",
        related_name="individual_tools",
        limit_choices_to={"tracking_mode": "individual"},
        null=True,
        blank=True,
    )
    tool_code = models.CharField(
        "Código de herramienta",
        max_length=30,
        unique=True,
    )
    name = models.CharField("Nombre", max_length=100)
    specification = models.ForeignKey(
        ToolSpecification,
        on_delete=models.PROTECT,
        verbose_name="Especificación",
        related_name="tools",
        null=True,
        blank=True,
    )
    brand = models.CharField("Marca", max_length=100, blank=True)
    serial_number = models.CharField(
        "Número de serie",
        max_length=100,
        blank=True,
    )
    location = models.CharField(
        "Ubicación en almacén",
        max_length=100,
        blank=True,
    )
    is_active = models.BooleanField("Activo", default=True)

    class Meta:
        verbose_name = "Herramienta"
        verbose_name_plural = "Herramientas"
        ordering = ["tool_code"]

    def __str__(self):
        return f"{self.tool_code} - {self.name}"

class Loan(models.Model):
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        verbose_name="Trabajador",
    )
    tool = models.ForeignKey(
        Tool,
        on_delete=models.PROTECT,
        verbose_name="Herramienta",
    )
    borrowed_at = models.DateTimeField(
        "Fecha de préstamo",
        default=timezone.now,
    )
    returned_at = models.DateTimeField(
        "Fecha de devolución",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Préstamo"
        verbose_name_plural = "Préstamos"
        ordering = ["-borrowed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tool"],
                condition=models.Q(returned_at__isnull=True),
                name="unique_open_loan_per_tool",
                violation_error_message=(
                    "Esta herramienta ya está prestada. "
                    "Registra su devolución antes de realizar otro préstamo."
                ),
            ),
        ]

    def __str__(self):
        return f"{self.tool.tool_code} - {self.employee.employee_id}"

class QuantityIssue(models.Model):

    request_line = models.ForeignKey(
        "MaterialRequestLine",
        on_delete=models.PROTECT,
        verbose_name="Artículo de la solicitud de origen",
        related_name="deliveries",
        null=True,
        blank=True,
        editable=False,
    )
    
    replacement_for = models.OneToOneField(
        "QuantityReturn",
        on_delete=models.PROTECT,
        verbose_name="Devolución que origina el cambio",
        related_name="replacement_issue",
        null=True,
        blank=True,
        editable=False,
    )
    
    legacy_loan = models.OneToOneField(
        Loan,
        on_delete=models.PROTECT,
        verbose_name="Préstamo de origen",
        related_name="unified_issue",
        null=True,
        blank=True,
        editable=False,
    )
    stock = models.ForeignKey(
        QuantityStock,
        on_delete=models.PROTECT,
        verbose_name="Existencias del artículo",
        related_name="issues",
        null=True,
        blank=True,
    )
    tool = models.ForeignKey(
        Tool,
        on_delete=models.PROTECT,
        verbose_name="Pieza individual",
        related_name="issues",
        null=True,
        blank=True,
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        verbose_name="Trabajador",
        related_name="quantity_issues",
    )
    quantity = models.PositiveIntegerField(
        "Cantidad entregada",
        validators=[MinValueValidator(1)],
    )
    returned_quantity = models.PositiveIntegerField(
        "Cantidad devuelta acumulada",
        default=0,
        editable=False,
    )
    issued_at = models.DateTimeField(
        "Fecha de entrega",
        default=timezone.now,
    )
    requires_return = models.BooleanField(
        "Requiere devolución",
        default=True,
        editable=False,
    )
    notes = models.TextField(
        "Observaciones",
        blank=True,
    )

    class Meta:
        verbose_name = "Entrega"
        verbose_name_plural = "Entregas"
        ordering = ["-issued_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="quantity_issue_quantity_gte_1",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    returned_quantity__lte=models.F("quantity")
                ),
                name="quantity_issue_returned_lte_quantity",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(stock__isnull=False, tool__isnull=True)
                    | models.Q(stock__isnull=True, tool__isnull=False)
                ),
                name="issue_stock_or_tool",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(tool__isnull=True)
                    | models.Q(quantity=1)
                ),
                name="issue_individual_quantity_one",
            ),
            models.UniqueConstraint(
                fields=["tool"],
                condition=models.Q(
                    tool__isnull=False,
                    requires_return=True,
                    returned_quantity=0,
                ),
                name="unique_open_issue_per_tool",
                violation_error_message=(
                    "Esta pieza ya tiene una entrega pendiente."
                ),
            ),
        ]

    def __str__(self):
        if self.tool_id:
            reference = self.tool.tool_code
        elif self.stock_id:
            reference = self.stock.article.article_code
        else:
            reference = "Sin artículo"

        return (
            f"Entrega #{self.pk} — {reference} — "
            f"Trabajador {self.employee.employee_id}"
        )

class QuantityReturn(models.Model):
    class Condition(models.TextChoices):
        GOOD = "good", "Buen estado"
        DAMAGED = "damaged", "Dañada"

    issue = models.ForeignKey(
        QuantityIssue,
        on_delete=models.PROTECT,
        verbose_name="Entrega original",
        related_name="returns",
    )
    quantity = models.PositiveIntegerField(
        "Cantidad devuelta",
        validators=[MinValueValidator(1)],
    )
    resolved_quantity = models.PositiveIntegerField(
        "Cantidad resuelta acumulada",
        default=0,
        editable=False,
    )
    condition = models.CharField(
        "Condición al regresar",
        max_length=20,
        choices=Condition.choices,
    )
    returned_at = models.DateTimeField(
        "Fecha de devolución",
        default=timezone.now,
    )
    reason = models.CharField(
        "Motivo del daño",
        max_length=200,
        blank=True,
    )
    notes = models.TextField(
        "Observaciones",
        blank=True,
    )

    class Meta:
        verbose_name = "Devolución"
        verbose_name_plural = "Devoluciones"
        ordering = ["-returned_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="quantity_return_quantity_gte_1",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    resolved_quantity__lte=models.F("quantity")
                ),
                name="quantity_return_resolved_lte_quantity",
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.condition == self.Condition.DAMAGED
            and not self.reason.strip()
        ):
            raise ValidationError({
                "reason": "Indica el motivo del daño.",
            })

    def __str__(self):
        return (
            f"Entrega #{self.issue_id} — "
            f"Devolución de {self.quantity} piezas"
        )

class DamageResolution(models.Model):
    class Outcome(models.TextChoices):
        RESTORED = "restored", "Regresar a disponibles"
        SCRAPPED = "scrapped", "Baja definitiva"

    source_return = models.ForeignKey(
        QuantityReturn,
        on_delete=models.PROTECT,
        verbose_name="Devolución por daño",
        related_name="resolutions",
        limit_choices_to={"condition": "damaged"},
    )
    quantity = models.PositiveIntegerField(
        "Cantidad revisada",
        validators=[MinValueValidator(1)],
    )
    outcome = models.CharField(
        "Resultado",
        max_length=20,
        choices=Outcome.choices,
    )
    resolved_at = models.DateTimeField(
        "Fecha de resolución",
        default=timezone.now,
    )
    reason = models.CharField(
        "Motivo de la resolución",
        max_length=200,
    )
    notes = models.TextField(
        "Observaciones",
        blank=True,
    )

    class Meta:
        verbose_name = "Resolución de daño"
        verbose_name_plural = "Resoluciones de daños"
        ordering = ["-resolved_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="damage_resolution_quantity_gte_1",
            ),
        ]

    def __str__(self):
        return (
            f"Devolución #{self.source_return_id} — "
            f"{self.get_outcome_display()} — {self.quantity}"
        )
    
class MaterialRequest(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Carrito"
        SUBMITTED = "submitted", "Enviada al almacén"
        PREPARED = "prepared", "Pendiente de confirmar recibido"
        CLOSED = "closed", "Cerrada"
        CANCELLED = "cancelled", "Cancelada"

    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        related_name="material_requests",
        verbose_name="Trabajador",
    )
    status = models.CharField(
        "Estado",
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        editable=False,
    )
    created_at = models.DateTimeField(
        "Fecha de creación",
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        "Última modificación",
        auto_now=True,
    )
    submitted_at = models.DateTimeField(
        "Fecha de envío",
        null=True,
        blank=True,
        editable=False,
    )
    closed_at = models.DateTimeField(
        "Fecha de cierre",
        null=True,
        blank=True,
        editable=False,
    )
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        verbose_name="Preparada por",
        related_name="prepared_material_requests",
        null=True,
        blank=True,
        editable=False,
    )
    prepared_at = models.DateTimeField(
        "Fecha de preparación",
        null=True,
        blank=True,
        editable=False,
    )
    preparation_version = models.PositiveIntegerField(
        "Versión de preparación",
        default=0,
        editable=False,
    )

    class Meta:
        verbose_name = "Solicitud de materiales"
        verbose_name_plural = "Solicitudes de materiales"
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["employee"],
                condition=models.Q(status="draft"),
                name="unique_draft_request_per_employee",
                violation_error_message=(
                    "Este trabajador ya tiene un carrito abierto."
                ),
            ),
        ]

    def __str__(self):
        return (
            f"Solicitud #{self.pk} — "
            f"{self.employee.employee_id}"
        )

class MaterialRequestLine(models.Model):
    request = models.ForeignKey(
        MaterialRequest,
        on_delete=models.PROTECT,
        related_name="lines",
        verbose_name="Solicitud",
    )
    article = models.ForeignKey(
        Article,
        on_delete=models.PROTECT,
        related_name="request_lines",
        verbose_name="Artículo",
    )
    requested_quantity = models.PositiveIntegerField(
        "Cantidad solicitada",
        validators=[MinValueValidator(1)],
    )
    prepared_quantity = models.PositiveIntegerField(
        "Cantidad preparada",
        default=0,
        editable=False,
    )

    class Meta:
        verbose_name = "Artículo solicitado"
        verbose_name_plural = "Artículos solicitados"
        ordering = ["pk"]
        constraints = [
            models.UniqueConstraint(
                fields=["request", "article"],
                name="unique_article_per_material_request",
            ),
            models.CheckConstraint(
                condition=models.Q(requested_quantity__gte=1),
                name="request_line_quantity_gte_1",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    prepared_quantity__lte=models.F(
                        "requested_quantity"
                    )
                ),
                name="request_line_prepared_lte_requested",
            ),
        ]

    def __str__(self):
        return (
            f"Solicitud #{self.request_id} — "
            f"{self.article.article_code} — "
            f"{self.requested_quantity} solicitadas"
        )

class MaterialRequestPiece(models.Model):
    line = models.ForeignKey(
        MaterialRequestLine,
        on_delete=models.PROTECT,
        related_name="selected_pieces",
        verbose_name="Artículo solicitado",
    )
    tool = models.ForeignKey(
        Tool,
        on_delete=models.PROTECT,
        related_name="request_selections",
        verbose_name="Pieza individual seleccionada",
    )

    class Meta:
        verbose_name = "Pieza preparada"
        verbose_name_plural = "Piezas preparadas"
        constraints = [
            models.UniqueConstraint(
                fields=["line", "tool"],
                name="unique_piece_per_request_line",
            ),
        ]

    def __str__(self):
        return (
            f"Solicitud #{self.line.request_id} — "
            f"{self.tool.tool_code}"
        )