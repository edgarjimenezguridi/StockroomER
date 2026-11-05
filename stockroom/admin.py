from django.contrib import admin
from .models import (
    Employee,
    Tool,
    Loan,
    ToolCategory,
    ToolType,
    ToolSpecification,
)
from django.utils import timezone

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "first_name", "last_name", "is_active")
    search_fields = ("employee_id", "first_name", "last_name")
    list_filter = ("is_active",)


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = (
        "tool_code",
        "name",
        "specification",
        "brand",
        "location",
        "is_active",
    )
    search_fields = (
        "tool_code",
        "name",
        "brand",
        "serial_number",
        "specification__name",
        "specification__tool_type__name",
        "specification__tool_type__category__name",
    )
    list_filter = (
        "is_active",
        "brand",
        "specification__tool_type__category",
        "specification__tool_type",
    )
    list_select_related = (
        "specification__tool_type__category",
    )

@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = ("employee", "tool", "borrowed_at", "returned_at", "status")
    search_fields = (
        "employee__employee_id",
        "employee__first_name",
        "employee__last_name",
        "tool__tool_code",
        "tool__name",
    )
    list_filter = ("returned_at",)
    actions = ["register_return"]

    @admin.action(
        description="Registrar devolución",
        permissions=["change"],
    )
    def register_return(self, request, queryset):
        updated = queryset.filter(
            returned_at__isnull=True
        ).update(returned_at=timezone.now())

        self.message_user(
            request,
            f"Préstamos devueltos: {updated}.",
        )

    @admin.display(description="Estado")
    def status(self, obj):
        return "Pendiente" if obj.returned_at is None else "Devuelto"

@admin.register(ToolCategory)
class ToolCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "description")
    search_fields = ("name", "description")

@admin.register(ToolType)
class ToolTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "category")
    search_fields = ("name", "category__name")
    list_filter = ("category",)

@admin.register(ToolSpecification)
class ToolSpecificationAdmin(admin.ModelAdmin):
    list_display = ("name", "tool_type")
    search_fields = (
        "name",
        "tool_type__name",
        "tool_type__category__name",
    )
    list_filter = ("tool_type__category", "tool_type")