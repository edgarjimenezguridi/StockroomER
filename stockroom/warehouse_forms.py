from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django import forms
from django.db.models import F
from .models import (
    Article, 
    Tool,
    QuantityStock, 
    StockEntry,
    QuantityReturn,
    DamageResolution,

)
from .selectors import piezas_individuales_disponibles


class WarehouseLoginForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)

        if not (
            user.is_staff
            and user.has_perm("stockroom.view_materialrequest")
        ):
            raise ValidationError(
                "Tu usuario no tiene permiso para acceder al panel del almacén.",
                code="warehouse_access_denied",
            )

class PrepareWarehouseLineForm(forms.Form):
    quantity = forms.IntegerField(
        label="Cantidad que entregarás",
        min_value=0,
        help_text="Escribe 0 si no entregarás este artículo.",
    )
    tools = forms.ModelMultipleChoiceField(
        label="Piezas individuales",
        queryset=Tool.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    def __init__(self, *args, line, **kwargs):
        super().__init__(*args, **kwargs)
        self.line = line

        self.fields["quantity"].initial = line.prepared_quantity
        self.fields["quantity"].widget.attrs["max"] = (
            line.requested_quantity
        )

        if line.article.tracking_mode == Article.TrackingMode.INDIVIDUAL:
            self.fields["tools"].queryset = (
                piezas_individuales_disponibles()
                .filter(article_id=line.article_id)
                .order_by("tool_code")
            )
            self.fields["tools"].initial = list(
                line.selected_pieces.values_list(
                    "tool_id",
                    flat=True,
                )
            )
        else:
            self.fields.pop("tools")

    def clean(self):
        cleaned_data = super().clean()
        quantity = cleaned_data.get("quantity")

        if quantity is None:
            return cleaned_data

        if quantity > self.line.requested_quantity:
            self.add_error(
                "quantity",
                "No puedes preparar más piezas de las solicitadas.",
            )

        if "tools" in self.fields and "tools" in cleaned_data:
            selected_tools = cleaned_data["tools"]

            if len(selected_tools) != quantity:
                self.add_error(
                    "tools",
                    "Selecciona exactamente una pieza por cada "
                    "unidad que entregarás. Si la cantidad es 0, "
                    "deja la selección vacía.",
                )

        return cleaned_data

class WarehouseReturnForm(forms.Form):
    operation = forms.ChoiceField(
        label="Tipo de operación",
        choices=[
            ("return_only", "Solo devolución"),
            ("exchange", "Devolución y cambio"),
        ],
        initial="return_only",
    )

    quantity = forms.IntegerField(
        label="Cantidad que regresa",
        min_value=1,
    )

    condition = forms.ChoiceField(
        label="Condición al regresar",
        choices=QuantityReturn.Condition.choices,
    )

    replacement_tool = forms.ModelChoiceField(
        label="Pieza individual de reemplazo",
        queryset=Tool.objects.none(),
        required=False,
        help_text=(
            "Solo para cambios de piezas individuales. "
            "Selecciona una pieza disponible del mismo artículo."
        ),
    )


    replacement_code = forms.CharField(
        label="Escanear código de reemplazo",
        max_length=100,
        required=False,
        help_text=(
            "Escanea el código único de la herramienta, "
            "por ejemplo TOOL-0002. También puedes "
            "utilizar el selector manual."
        ),
        widget=forms.TextInput(attrs={
            "autocomplete": "off",
            "spellcheck": "false",
            "placeholder": "Escanea o escribe el código de la pieza",
        }),
    )


    reason = forms.CharField(
        label="Motivo del daño",
        max_length=200,
        required=False,
    )

    notes = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, issue, pending_quantity, **kwargs):
        super().__init__(*args, **kwargs)

        self.issue = issue
        self.pending_quantity = pending_quantity

        self.fields["quantity"].widget.attrs["max"] = pending_quantity
        self.fields["quantity"].help_text = (
            f"Pendientes de devolución: {pending_quantity}."
        )

        if issue.tool_id:
            self.fields["replacement_tool"].queryset = (
                piezas_individuales_disponibles()
                .filter(article_id=issue.tool.article_id)
                .exclude(pk=issue.tool_id)
            )

    def clean_quantity(self):
        quantity = self.cleaned_data["quantity"]

        if quantity > self.pending_quantity:
            raise forms.ValidationError(
                "La cantidad supera las piezas pendientes de devolución."
            )

        return quantity

    def clean(self):
        cleaned_data = super().clean()

        operation = cleaned_data.get("operation")
        condition = cleaned_data.get("condition")
        replacement_tool = cleaned_data.get("replacement_tool")
        reason = cleaned_data.get("reason", "").strip()

        # Resolver la herramienta escaneada utilizando
        # el mismo selector protegido que el campo manual.
        replacement_code = (
            cleaned_data.get("replacement_code") or ""
        ).strip()

        if replacement_code:
            if operation != "exchange" or not self.issue.tool_id:
                self.add_error(
                    "replacement_code",
                    "El escaneo de reemplazo solo se permite "
                    "para cambios de herramientas individuales.",
                )
            else:
                scanned_tool = (
                    self.fields["replacement_tool"]
                    .queryset
                    .filter(tool_code__iexact=replacement_code)
                    .first()
                )

                if scanned_tool is None:
                    self.add_error(
                        "replacement_code",
                        "No se encontró una herramienta disponible "
                        "del mismo artículo con ese código.",
                    )

                elif (
                    replacement_tool is not None
                    and replacement_tool.pk != scanned_tool.pk
                ):
                    self.add_error(
                        "replacement_code",
                        "La herramienta escaneada no coincide "
                        "con la seleccionada manualmente.",
                    )

                else:
                    replacement_tool = scanned_tool
                    cleaned_data["replacement_tool"] = scanned_tool


        if (
            condition == QuantityReturn.Condition.DAMAGED
            and not reason
        ):
            self.add_error(
                "reason",
                "Indica el motivo del daño.",
            )

        if operation == "return_only":
            if replacement_tool:
                self.add_error(
                    "replacement_tool",
                    "Una devolución normal no debe tener reemplazo.",
                )

        elif operation == "exchange":
            if condition != QuantityReturn.Condition.DAMAGED:
                self.add_error(
                    "condition",
                    "Para realizar un cambio, la pieza debe estar dañada.",
                )

            if self.issue.tool_id:
                if not replacement_tool:
                    self.add_error(
                        "replacement_tool",
                        "Selecciona la pieza que se entregará como reemplazo.",
                    )
                elif replacement_tool.article_id != self.issue.tool.article_id:
                    self.add_error(
                        "replacement_tool",
                        "El reemplazo debe pertenecer al mismo artículo.",
                    )

            elif replacement_tool:
                self.add_error(
                    "replacement_tool",
                    "Los artículos por cantidad no requieren seleccionar una pieza individual.",
                )

        return cleaned_data
    
class WarehouseStockEntryForm(forms.Form):
    stock = forms.ModelChoiceField(
        label="Artículo",
        queryset=QuantityStock.objects.none(),
    )
    quantity = forms.IntegerField(
        label="Cantidad recibida",
        min_value=1,
    )
    reference = forms.CharField(
        label="Referencia",
        max_length=100,
        required=False,
    )
    notes = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["stock"].queryset = (
            QuantityStock.objects.filter(
                article__is_active=True,
                article__tracking_mode=Article.TrackingMode.QUANTITY,
            )
            .select_related("article")
            .order_by("article__name")
        )

class WarehouseDamageResolutionForm(forms.Form):
    source_return = forms.ModelChoiceField(
        label="Devolución dañada",
        queryset=QuantityReturn.objects.none(),
    )
    quantity = forms.IntegerField(
        label="Cantidad que resolverás",
        min_value=1,
    )
    outcome = forms.ChoiceField(
        label="Resolución",
        choices=DamageResolution.Outcome.choices,
    )
    reason = forms.CharField(
        label="Motivo de la resolución",
        max_length=200,
    )
    notes = forms.CharField(
        label="Observaciones",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["source_return"].queryset = (
            QuantityReturn.objects.filter(
                condition=QuantityReturn.Condition.DAMAGED,
                resolved_quantity__lt=F("quantity"),
            )
            .select_related(
                "issue__employee",
                "issue__stock__article",
                "issue__tool__article",
                "issue__tool",
            )
            .order_by("-returned_at", "-pk")
        )

    def clean(self):
        cleaned_data = super().clean()
        damaged_return = cleaned_data.get("source_return")
        quantity = cleaned_data.get("quantity")

        if damaged_return is not None and quantity is not None:
            pending = (
                damaged_return.quantity - damaged_return.resolved_quantity
            )

            if quantity > pending:
                self.add_error(
                    "quantity",
                    f"Solo quedan {pending} piezas dañadas por resolver.",
                )

        return cleaned_data

class WarehouseStockCorrectionForm(forms.Form):
    entry = forms.ModelChoiceField(
        label="Entrada que vas a corregir",
        queryset=StockEntry.objects.none(),
    )
    quantity_delta = forms.IntegerField(
        label="Ajuste de cantidad",
        help_text=(
            "Usa un número positivo para aumentar existencias "
            "o negativo para reducirlas."
        ),
    )
    reason = forms.CharField(
        label="Motivo de la corrección",
        max_length=200,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entry"].queryset = (
            StockEntry.objects.filter(
                stock__article__is_active=True,
                stock__article__tracking_mode=Article.TrackingMode.QUANTITY,
            )
            .select_related("stock__article")
            .order_by("-received_at", "-pk")
        )
        self.fields["entry"].label_from_instance = self.entry_label

    @staticmethod
    def entry_label(entry):
        article = entry.stock.article
        return (
            f"{article.article_code} — {article.name} "
            f"(entrada #{entry.pk}, cantidad original: {entry.quantity})"
        )

    def clean_quantity_delta(self):
        delta = self.cleaned_data["quantity_delta"]

        if delta == 0:
            raise forms.ValidationError(
                "El ajuste debe ser distinto de cero."
            )

        return delta