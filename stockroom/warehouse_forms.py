from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django import forms
from .models import Article, Tool
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