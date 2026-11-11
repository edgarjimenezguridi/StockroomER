
from django import forms

from .models import Article, Tool


class IndividualToolForm(forms.Form):

    article = forms.ModelChoiceField(
        label="Artículo del catálogo",
        queryset=Article.objects.none(),
        empty_label="Selecciona un artículo",
    )

    tool_code = forms.CharField(
        label="Código único de la pieza",
        max_length=30,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ej. MIC-001",
                "autocomplete": "off",
            }
        ),
    )

    serial_number = forms.CharField(
        label="Número de serie",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Número de serie del fabricante",
            }
        ),
    )

    location = forms.CharField(
        label="Ubicación de la pieza",
        max_length=100,
        required=False,
        widget=forms.TextInput(
            attrs={
                "placeholder": "Ej. Estante B, cajón 3",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["article"].queryset = (
            Article.objects.filter(
                is_active=True,
                tracking_mode=Article.TrackingMode.INDIVIDUAL,
            )
            .select_related("specification")
            .order_by("name", "article_code")
        )

        self.fields["article"].label_from_instance = (
            lambda article: (
                f"{article.article_code} — {article.name}"
            )
        )

    def clean_tool_code(self):
        code = self.cleaned_data["tool_code"].strip().upper()

        if Tool.objects.filter(
            tool_code__iexact=code
        ).exists():
            raise forms.ValidationError(
                "Ya existe una pieza registrada con este código."
            )

        return code

    def clean_serial_number(self):
        return self.cleaned_data["serial_number"].strip()

    def clean_location(self):
        return self.cleaned_data["location"].strip()

    def clean(self):
        cleaned_data = super().clean()

        article = cleaned_data.get("article")
        location = cleaned_data.get("location")

        if article and not location:
            default_location = (article.location or "").strip()

            if len(default_location) <= 100:
                cleaned_data["location"] = default_location

        return cleaned_data


class EditIndividualToolForm(forms.ModelForm):

    class Meta:
        model = Tool

        fields = [
            "serial_number",
            "location",
        ]

        labels = {
            "serial_number": "Número de serie",
            "location": "Ubicación de la pieza",
        }

        widgets = {
            "serial_number": forms.TextInput(
                attrs={
                    "placeholder": "Número de serie del fabricante",
                }
            ),
            "location": forms.TextInput(
                attrs={
                    "placeholder": "Ej. Estante B, cajón 3",
                }
            ),
        }

    def clean_serial_number(self):
        return self.cleaned_data["serial_number"].strip()

    def clean_location(self):
        return self.cleaned_data["location"].strip()


