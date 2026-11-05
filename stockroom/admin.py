from django.contrib import admin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect



from .models import (
    Employee,
    Tool,
    Loan,
    ToolCategory,
    ToolType,
    ToolSpecification,
    Article,
    QuantityStock,
    StockEntry,
    QuantityIssue,
    QuantityReturn,
)

from django.utils import timezone
from .services import (
    register_stock_entry,
    register_quantity_issue,
    register_quantity_return,
)

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
        "article",
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

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "article_code",
        "name",
        "specification",
        "brand",
        "tracking_mode",
        "return_mode",
        "is_active",
    )
    search_fields = (
        "article_code",
        "name",
        "brand",
        "specification__name",
        "specification__tool_type__name",
    )
    list_filter = (
        "tracking_mode",
        "return_mode",
        "is_active",
    )
    list_select_related = (
        "specification__tool_type__category",
    )

@admin.register(QuantityStock)
class QuantityStockAdmin(admin.ModelAdmin):
    list_display = (
        "article",
        "available_quantity",
        "loaned_quantity",
        "quarantine_quantity",
    )
    search_fields = (
        "article__article_code",
        "article__name",
    )
    list_select_related = ("article",)
    readonly_fields = (
        "available_quantity",
        "loaned_quantity",
        "quarantine_quantity",
    )

    def get_readonly_fields(self, request, obj=None):
        if obj:
            return self.readonly_fields + ("article",)
        return self.readonly_fields

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(StockEntry)
class StockEntryAdmin(admin.ModelAdmin):
    list_display = (
        "stock",
        "quantity",
        "received_at",
        "reference",
    )
    search_fields = (
        "stock__article__article_code",
        "stock__article__name",
        "reference",
    )
    list_select_related = ("stock__article",)
    fields = (
        "stock",
        "quantity",
        "received_at",
        "reference",
        "notes",
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "stock":
            kwargs["queryset"] = QuantityStock.objects.filter(
                article__is_active=True,
                article__tracking_mode=Article.TrackingMode.QUANTITY,
            ).select_related("article")

        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )

    def save_model(self, request, obj, form, change):
        register_stock_entry(obj)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(QuantityIssue)
class QuantityIssueAdmin(admin.ModelAdmin):
    list_display = (
        "stock",
        "employee",
        "quantity",
        "issued_at",
        "requires_return",
    )
    search_fields = (
        "stock__article__article_code",
        "stock__article__name",
        "employee__employee_id",
        "employee__first_name",
        "employee__last_name",
    )
    list_filter = ("requires_return",)
    list_select_related = ("stock__article", "employee")
    fields = (
        "stock",
        "employee",
        "quantity",
        "issued_at",
        "requires_return",
        "notes",
    )
    readonly_fields = ("requires_return",)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "stock":
            kwargs["queryset"] = QuantityStock.objects.filter(
                article__is_active=True,
                article__tracking_mode=Article.TrackingMode.QUANTITY,
            ).select_related("article")

        elif db_field.name == "employee":
            kwargs["queryset"] = Employee.objects.filter(is_active=True)

        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )

    def get_fields(self, request, obj=None):
        if obj is None:
            return tuple(
                field for field in self.fields
                if field != "requires_return"
            )
        return self.fields

    def save_model(self, request, obj, form, change):
        register_quantity_issue(obj)

    def changeform_view(
        self, request, object_id=None, form_url="", extra_context=None
    ):
        try:
            return super().changeform_view(
                request, object_id, form_url, extra_context
            )
        except ValidationError as exc:
            self.message_user(
                request,
                " ".join(exc.messages),
                level="error",
            )
            return redirect(request.path)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

@admin.register(QuantityReturn)
class QuantityReturnAdmin(admin.ModelAdmin):
    list_display = (
        "issue",
        "quantity",
        "condition",
        "returned_at",
        "reason",
    )
    search_fields = (
        "issue__stock__article__article_code",
        "issue__stock__article__name",
        "issue__employee__employee_id",
        "issue__employee__first_name",
        "issue__employee__last_name",
    )
    list_filter = ("condition",)
    list_select_related = (
        "issue__stock__article",
        "issue__employee",
    )
    fields = (
        "issue",
        "quantity",
        "condition",
        "returned_at",
        "reason",
        "notes",
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "issue":
            kwargs["queryset"] = QuantityIssue.objects.filter(
                requires_return=True,
            ).select_related("stock__article", "employee")

        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )

    def save_model(self, request, obj, form, change):
        register_quantity_return(obj)

    def changeform_view(
        self, request, object_id=None, form_url="", extra_context=None
    ):
        try:
            return super().changeform_view(
                request, object_id, form_url, extra_context
            )
        except ValidationError as exc:
            self.message_user(
                request,
                " ".join(exc.messages),
                level="error",
            )
            return redirect(request.path)

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False