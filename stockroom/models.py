from django.db import models
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError

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


    
class Tool(models.Model):
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
    stock = models.ForeignKey(
        QuantityStock,
        on_delete=models.PROTECT,
        verbose_name="Existencias del artículo",
        related_name="issues",
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
        verbose_name = "Entrega por cantidad"
        verbose_name_plural = "Entregas por cantidad"
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
        ]

    def __str__(self):
        return (
            f"{self.stock.article.article_code} — "
            f"{self.employee.employee_id} — "
            f"{self.quantity} piezas"
        )

class QuantityReturn(models.Model):
    class Condition(models.TextChoices):
        GOOD = "good", "Buen estado"
        WORN = "worn", "Desgaste"
        DAMAGED = "damaged", "Daño"

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
        "Motivo del desgaste o daño",
        max_length=200,
        blank=True,
    )
    notes = models.TextField(
        "Observaciones",
        blank=True,
    )

    class Meta:
        verbose_name = "Devolución por cantidad"
        verbose_name_plural = "Devoluciones por cantidad"
        ordering = ["-returned_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1),
                name="quantity_return_quantity_gte_1",
            ),
        ]

    def clean(self):
        super().clean()
        if self.condition in (
            self.Condition.WORN,
            self.Condition.DAMAGED,
        ) and not self.reason.strip():
            raise ValidationError({
                "reason": "Indica el motivo del desgaste o daño.",
            })

    def __str__(self):
        return (
            f"Entrega #{self.issue_id} — "
            f"Devolución de {self.quantity} piezas"
        )