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
    DamageResolution,
)
from django.utils import timezone
from .services import (
    register_stock_entry,
    register_quantity_issue,
    register_quantity_return,
    register_return_and_exchange,
    register_damage_resolution,
)

def piezas_individuales_disponibles():
    piezas_con_pendiente = QuantityIssue.objects.filter(
        tool__isnull=False,
        requires_return=True,
        returned_quantity__lt=F("quantity"),
    ).values("tool_id")

    prestamos_sin_importar = Loan.objects.filter(
        returned_at__isnull=True,
        unified_issue__isnull=True,
    ).values("tool_id")

    return (
        Tool.objects.filter(
            is_active=True,
            inventory_status=Tool.InventoryStatus.AVAILABLE,
            article__is_active=True,
            article__tracking_mode=Article.TrackingMode.INDIVIDUAL,
        )
        .exclude(pk__in=piezas_con_pendiente)
        .exclude(pk__in=prestamos_sin_importar)
        .select_related("article")
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
        "scrapped_quantity",
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
        "scrapped",
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
            scrapped_units=Count(
                "individual_tools",
                filter=Q(
                    individual_tools__inventory_status=(
                        Tool.InventoryStatus.SCRAPPED
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
    @admin.display(description="Bajas acumuladas")
    def scrapped(self, obj):
        return self.stock_value(
            obj, "scrapped_quantity", "scrapped_units"
        )

    def get_readonly_fields(self, request, obj=None):
        readonly = tuple(
            super().get_readonly_fields(request, obj)
        )

        if obj is not None:
            has_stock = QuantityStock.objects.filter(
                article_id=obj.pk,
            ).exists()
            has_tools = Tool.objects.filter(
                article_id=obj.pk,
            ).exists()

            if has_stock or has_tools:
                return readonly + ("tracking_mode",)

        return readonly

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

class IssueStatusFilter(admin.SimpleListFilter):
    title = "Estado de entrega"
    parameter_name = "issue_status"

    def lookups(self, request, model_admin):
        return (
            ("pending", "Con piezas pendientes"),
            ("partial", "Devolución parcial"),
            ("returned", "Devuelta"),
            ("no_return", "Sin devolución"),
        )

    def queryset(self, request, queryset):
        if self.value() == "pending":
            return queryset.filter(
                requires_return=True,
                returned_quantity__lt=F("quantity"),
            )

        if self.value() == "partial":
            return queryset.filter(
                requires_return=True,
                returned_quantity__gt=0,
                returned_quantity__lt=F("quantity"),
            )

        if self.value() == "returned":
            return queryset.filter(
                requires_return=True,
                returned_quantity=F("quantity"),
            )

        if self.value() == "no_return":
            return queryset.filter(requires_return=False)

        return queryset

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
    list_filter = (IssueStatusFilter, "employee")
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
            kwargs["queryset"] = piezas_individuales_disponibles()

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
            piezas_individuales_disponibles().filter(
                article__return_mode=Article.ReturnMode.RETURNABLE,
            )
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
        "id",
        "issue",
        "worker",
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
    list_filter = (
        "condition",
        "issue__employee",
        "returned_at",
    )
    date_hierarchy = "returned_at"
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
    @admin.display(
        description="Trabajador",
        ordering="issue__employee__last_name",
    )
    
    def worker(self, obj):
        return str(obj.issue.employee)

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

@admin.register(DamageResolution)
class DamageResolutionAdmin(admin.ModelAdmin):
    list_display = (
        "source_return",
        "quantity",
        "outcome",
        "resolved_at",
        "reason",
    )
    search_fields = (
        "source_return__issue__stock__article__article_code",
        "source_return__issue__stock__article__name",
        "source_return__issue__tool__tool_code",
        "source_return__issue__tool__name",
        "reason",
    )
    list_filter = ("outcome",)
    list_select_related = (
        "source_return__issue__stock__article",
        "source_return__issue__tool",
        "source_return__issue__employee",
    )
    fields = (
        "source_return",
        "quantity",
        "outcome",
        "resolved_at",
        "reason",
        "notes",
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "source_return":
            kwargs["queryset"] = QuantityReturn.objects.filter(
                condition=QuantityReturn.Condition.DAMAGED,
                resolved_quantity__lt=F("quantity"),
            ).select_related(
                "issue__stock__article",
                "issue__tool",
                "issue__employee",
            )

        return super().formfield_for_foreignkey(
            db_field, request, **kwargs
        )

    def save_model(self, request, obj, form, change):
        register_damage_resolution(obj)

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