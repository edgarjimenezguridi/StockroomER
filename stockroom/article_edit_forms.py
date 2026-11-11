
from django import forms

from .models import Article, ToolSpecification


class EditArticleForm(forms.ModelForm):

    class Meta:
        model = Article

        fields = [
            "name",
            "specification",
            "brand",
            "location",
            "minimum_stock",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Nombre del artículo",
                    "autocomplete": "off",
                }
            ),
            "brand": forms.TextInput(
                attrs={
                    "placeholder": "Marca del artículo",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "placeholder": "Ej. Estante A, nivel 2",
                }
            ),
            "minimum_stock": forms.NumberInput(
                attrs={
                    "min": 0,
                    "step": 1,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["specification"].queryset = (
            ToolSpecification.objects.select_related(
                "tool_type",
                "tool_type__category",
            ).order_by(
                "tool_type__category__name",
                "tool_type__name",
                "name",
            )
        )

        self.fields["specification"].empty_label = (
            "Sin especificación"
        )

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError(
                "El nombre del artículo es obligatorio."
            )

        return name

    def clean_brand(self):
        return self.cleaned_data["brand"].strip()

    def clean_location(self):
        return self.cleaned_data["location"].strip()
