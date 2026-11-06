from django import forms


class PinSetupForm(forms.Form):
    pin = forms.RegexField(
        label="NIP personal",
        regex=r"\A[0-9]{6}\Z",
        strip=False,
        help_text="Elige un NIP de 6 dígitos.",
        error_messages={
            "invalid": "Escribe exactamente 6 dígitos.",
        },
        widget=forms.PasswordInput(attrs={
            "inputmode": "numeric",
            "maxlength": "6",
            "autocomplete": "new-password",
        }),
    )
    pin_confirmation = forms.CharField(
        label="Confirmar NIP",
        strip=False,
        widget=forms.PasswordInput(attrs={
            "inputmode": "numeric",
            "maxlength": "6",
            "autocomplete": "new-password",
        }),
    )