
from django import forms

from .models import (
    ToolCategory,
    ToolType,
    ToolSpecification,
)


class CategoryForm(forms.ModelForm):
    class Meta:
        model = ToolCategory
        fields = ["name", "description"]

        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Ej. Herramientas de medición",
                "autocomplete": "off",
            }),
            "description": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Descripción opcional",
            }),
        }

    def clean_name(self):
        name = self.cleaned_data["name"].strip()

        if ToolCategory.objects.filter(
            name__iexact=name
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError(
                "Esta categoría ya existe."
            )

        return name


class ToolTypeForm(forms.ModelForm):
    class Meta:
        model = ToolType
        fields = ["category", "name"]

        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Ej. Micrómetro",
                "autocomplete": "off",
            }),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean(self):
        cleaned_data = super().clean()

        category = cleaned_data.get("category")
        name = cleaned_data.get("name")

        if category and name:
            if ToolType.objects.filter(
                category=category,
                name__iexact=name,
            ).exclude(pk=self.instance.pk).exists():
                self.add_error(
                    "name",
                    "Este tipo ya existe en esta categoría."
                )

        return cleaned_data


class SpecificationForm(forms.ModelForm):
    class Meta:
        model = ToolSpecification
        fields = ["tool_type", "name", "description"]

        widgets = {
            "name": forms.TextInput(attrs={
                "placeholder": "Ej. Rango 0–25 mm",
                "autocomplete": "off",
            }),
            "description": forms.Textarea(attrs={
                "rows": 3,
                "placeholder": "Detalles técnicos opcionales",
            }),
        }

    def clean_name(self):
        return self.cleaned_data["name"].strip()

    def clean(self):
        cleaned_data = super().clean()

        tool_type = cleaned_data.get("tool_type")
        name = cleaned_data.get("name")

        if tool_type and name:
            if ToolSpecification.objects.filter(
                tool_type=tool_type,
                name__iexact=name,
            ).exclude(pk=self.instance.pk).exists():
                self.add_error(
                    "name",
                    "Esta especificación ya existe para este tipo."
                )

        return cleaned_data
