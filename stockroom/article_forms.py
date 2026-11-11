
from django import forms

from .models import Article, ToolSpecification


class NewArticleForm(forms.ModelForm):
    class Meta:
        model = Article

        fields = [
            "article_code",
            "name",
            "specification",
            "brand",
            "location",
            "tracking_mode",
            "return_mode",
            "minimum_stock",
        ]

        widgets = {
            "article_code": forms.TextInput(
                attrs={
                    "placeholder": "Ej. ART-001",
                    "autocomplete": "off",
                }
            ),
            "name": forms.TextInput(
                attrs={
                    "placeholder": "Ej. Broca de 8 mm",
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
                attrs={"min": 0, "step": 1}
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

        self.fields["tracking_mode"].choices = [
            ("", "Selecciona el tipo de control"),
            *Article.TrackingMode.choices,
        ]

        self.fields["return_mode"].choices = [
            ("", "Selecciona la modalidad"),
            *Article.ReturnMode.choices,
        ]

        self.fields["tracking_mode"].required = True
        self.fields["return_mode"].required = True

    def clean_article_code(self):
        code = self.cleaned_data["article_code"].strip().upper()

        if Article.objects.filter(
            article_code__iexact=code
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(
                "Ya existe un artículo con este código."
            )

        return code

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if not name:
            raise forms.ValidationError(
                "El nombre del artículo es obligatorio."
            )

        return name
