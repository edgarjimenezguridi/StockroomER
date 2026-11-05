from django.db import models
from django.utils import timezone

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


class Tool(models.Model):
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