from django.contrib import admin
from .models import Employee, Tool, Loan
from django.utils import timezone

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ("employee_id", "first_name", "last_name", "is_active")
    search_fields = ("employee_id", "first_name", "last_name")
    list_filter = ("is_active",)


@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ("tool_code", "name", "brand", "location", "is_active")
    search_fields = ("tool_code", "name", "brand", "serial_number")
    list_filter = ("is_active", "brand")

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
    