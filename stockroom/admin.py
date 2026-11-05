from django.contrib import admin
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.db.models import Count, F, Q, Sum
from django.urls import reverse
from django.utils.html import format_html
from django import forms



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
    register_return_and_exchange,
)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = (
        "employee_id",
        "first_name",
        "last_name",
        "damaged_pieces",
        "is_active",
    )
    search_fields = ("employee_id", "first_name", "last_name")
    list_filter = ("is_active",)

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            damaged_total=Sum(
                "quantity_issues__returns__quantity",
                filter=Q(
                    quantity_issues__returns__condition="damaged"
                ),
                default=0,
            )
        )

    @admin.display(
        description="Piezas devueltas dañadas",
        ordering="damaged_total",
    )
    def damaged_pieces(self, obj):
        url = reverse("admin:stockroom_quantityreturn_changelist")
        return format_html(
            '<a href="{}?condition=damaged&issue__employee__id__exact={}">'
            "{}</a>",
            url,
            obj.pk,
            obj.damaged_total,
        )


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



    
    def get_model_perms(self, request):
        return {}





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
    actions = None

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
    
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
    
    def get_model_perms(self, request):
        return {}


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

class ToolInline(admin.TabularInline):
    model = Tool
    fk_name = "article"
    verbose_name = "Pieza individual"
    verbose_name_plural = "Piezas individuales"
    fields = (
        "tool_code",
        "name",
        "serial_number",
        "location",
        "inventory_status",
        "is_active",
    )
    readonly_fields = ("inventory_status",)
    extra = 0
    can_delete = False

class QuantityStockInline(admin.StackedInline):
    model = QuantityStock
    fk_name = "article"
    verbose_name_plural = "Existencias"
    fields = (
        "available_quantity",
        "loaned_quantity",
        "quarantine_quantity",
    )
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False

@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = (
        "article_code",
        "name",
        "tracking_mode",
        "available",
        "loaned",
        "quarantine",
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
        "quantity_stock",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            available_units=Count(
                "individual_tools",
                filter=Q(
                    individual_tools__inventory_status=(
                        Tool.InventoryStatus.AVAILABLE
                    ),
                    individual_tools__is_active=True,
                ),
            ),
            loaned_units=Count(
                "individual_tools",
                filter=Q(
                    individual_tools__inventory_status=(
                        Tool.InventoryStatus.LOANED
                    ),
                ),
            ),
            quarantine_units=Count(
                "individual_tools",
                filter=Q(
                    individual_tools__inventory_status=(
                        Tool.InventoryStatus.QUARANTINE
                    ),
                ),
            ),
        )

    def stock_value(self, obj, quantity_field, individual_field):
        if obj.tracking_mode == Article.TrackingMode.INDIVIDUAL:
            return getattr(obj, individual_field)

        stock = getattr(obj, "quantity_stock", None)
        if stock is None:
            return "Sin registro"
        return getattr(stock, quantity_field)

    @admin.display(description="Disponibles")
    def available(self, obj):
        return self.stock_value(
            obj, "available_quantity", "available_units"
        )

    @admin.display(description="Prestadas")
    def loaned(self, obj):
        return self.stock_value(
            obj, "loaned_quantity", "loaned_units"
        )

    @admin.display(description="Dañadas / en revisión")
    def quarantine(self, obj):
        return self.stock_value(
            obj, "quarantine_quantity", "quarantine_units"
        )

    def get_inlines(self, request, obj=None):
        if obj is None:
            return []

        if obj.tracking_mode == Article.TrackingMode.INDIVIDUAL:
            return [ToolInline]

        return [QuantityStockInline]

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

        if obj.tracking_mode == Article.TrackingMode.QUANTITY:
            QuantityStock.objects.get_or_create(article=obj)

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

    def get_model_perms(self, request):
        return {}

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
        "id",
        "item",
        "employee",
        "quantity",
        "returned_quantity",
        "pending_quantity",
        "status",
        "issued_at",
    )
    search_fields = (
        "stock__article__article_code",
        "stock__article__name",
        "tool__tool_code",
        "tool__name",
        "tool__serial_number",
        "employee__employee_id",
        "employee__first_name",
        "employee__last_name",
    )
    list_filter = ("requires_return",)
    list_select_related = (
        "stock__article",
        "tool__article",
        "employee",
    )
    fields = (
        "stock",
        "tool",
        "employee",
        "quantity",
        "issued_at",
        "requires_return",
        "returned_quantity",
        "pending_quantity",
        "status",
        "legacy_loan",
        "replacement_for",
        "notes",
    )
    readonly_fields = (
        "requires_return",
        "returned_quantity",
        "pending_quantity",
        "status",
        "legacy_loan",
        "replacement_for",
    )

    @admin.display(description="Artículo / pieza")
    def item(self, obj):
        if obj.tool_id:
            return str(obj.tool)
        return str(obj.stock.article)

    @admin.display(description="Pendientes")
    def pending_quantity(self, obj):
        if not obj.requires_return:
            return 0
        return obj.quantity - obj.returned_quantity

    @admin.display(description="Estado")
    def status(self, obj):
        if not obj.requires_return:
            return "Sin devolución"
        if obj.returned_quantity == obj.quantity:
            return "Devuelta"
        if obj.returned_quantity:
            return "Devolución parcial"
        return "Pendiente"

    def get_fields(self, request, obj=None):
        if obj is None:
            return (
                "stock",
                "tool",
                "employee",
                "quantity",
                "issued_at",
                "notes",
            )
        return self.fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "stock":
            kwargs["queryset"] = QuantityStock.objects.filter(
                article__is_active=True,
                article__tracking_mode=Article.TrackingMode.QUANTITY,
            ).select_related("article")

        elif db_field.name == "tool":
            kwargs["queryset"] = Tool.objects.filter(
                is_active=True,
                inventory_status=Tool.InventoryStatus.AVAILABLE,
                article__is_active=True,
                article__tracking_mode=Article.TrackingMode.INDIVIDUAL,
            ).select_related("article")

        elif db_field.name == "employee":
            kwargs["queryset"] = Employee.objects.filter(is_active=True)

        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )

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

class QuantityReturnForm(forms.ModelForm):
    operation = forms.ChoiceField(
        label="Operación",
        choices=[
            ("return_only", "Solo devolución"),
            ("exchange", "Devolución y cambio"),
        ],
        initial="return_only",
    )
    replacement_tool = forms.ModelChoiceField(
        label="Pieza individual de reemplazo",
        queryset=Tool.objects.none(),
        required=False,
        help_text=(
            "Solo para cambios de piezas individuales. "
            "Debe pertenecer al mismo artículo que la pieza devuelta."
        ),
    )

    class Meta:
        model = QuantityReturn
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["replacement_tool"].queryset = (
            Tool.objects.filter(
                is_active=True,
                inventory_status=Tool.InventoryStatus.AVAILABLE,
                article__is_active=True,
                article__tracking_mode=Article.TrackingMode.INDIVIDUAL,
                article__return_mode=Article.ReturnMode.RETURNABLE,
            ).select_related("article")
        )

    def clean(self):
        cleaned = super().clean()
        operation = cleaned.get("operation")
        replacement = cleaned.get("replacement_tool")
        issue = cleaned.get("issue")

        if operation == "return_only":
            if replacement:
                self.add_error(
                    "replacement_tool",
                    "Para solo devolución, deja este campo vacío.",
                )
            return cleaned

        if operation != "exchange":
            return cleaned

        if cleaned.get("condition") != QuantityReturn.Condition.DAMAGED:
            self.add_error(
                "condition",
                "El cambio requiere una pieza dañada.",
            )

        if issue:
            if issue.tool_id:
                if replacement is None:
                    self.add_error(
                        "replacement_tool",
                        "Selecciona la pieza de reemplazo.",
                    )
                elif (
                    replacement.pk == issue.tool_id
                    or replacement.article_id != issue.tool.article_id
                ):
                    self.add_error(
                        "replacement_tool",
                        "Selecciona otra pieza del mismo artículo.",
                    )
            elif replacement:
                self.add_error(
                    "replacement_tool",
                    "Para artículos por cantidad, deja este campo vacío.",
                )

        return cleaned

@admin.register(QuantityReturn)
class QuantityReturnAdmin(admin.ModelAdmin):
    form = QuantityReturnForm
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
    list_filter = ("condition", "issue__employee")
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
    def get_fields(self, request, obj=None):
        if obj is None:
            return (
                "issue",
                "quantity",
                "condition",
                "returned_at",
                "reason",
                "notes",
                "operation",
                "replacement_tool",
            )
        return self.fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "issue":
            kwargs["queryset"] = QuantityIssue.objects.filter(
                requires_return=True,
                returned_quantity__lt=F("quantity"),
            ).select_related(
                "stock__article",
                "tool",
                "employee",
            )

        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )

    def save_model(self, request, obj, form, change):
        if form.cleaned_data["operation"] == "exchange":
            replacement_tool = form.cleaned_data.get("replacement_tool")

            register_return_and_exchange(
                obj,
                replacement_tool_id=(
                    replacement_tool.pk if replacement_tool else None
                ),
            )
        else:
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