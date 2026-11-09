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

class CredentialScanForm(forms.Form):
    barcode = forms.UUIDField(
        label="Credencial de empleado",
        error_messages={
            "required": "Escanea tu credencial.",
            "invalid": "El código de la credencial no es válido.",
        },
        widget=forms.TextInput(attrs={
            "autofocus": True,
            "autocomplete": "off",
            "spellcheck": "false",
            "placeholder": "Escanea tu credencial aquí",
        }),
    )

class EmployeeNumberAccessForm(forms.Form):
    employee_id = forms.CharField(
        label="Número de empleado",
        max_length=20,
        strip=True,
        error_messages={
            "required": "Escribe tu número de empleado.",
        },
        widget=forms.TextInput(attrs={
            "autofocus": True,
            "autocomplete": "off",
            "spellcheck": "false",
            "placeholder": "Ejemplo: 0001",
        }),
    )

class EmployeePinForm(forms.Form):
    pin = forms.CharField(
        label="NIP personal",
        strip=False,
        max_length=128,
        widget=forms.PasswordInput(attrs={
            "autofocus": True,
            "inputmode": "numeric",
            "autocomplete": "current-password",
            "placeholder": "Escribe tu NIP de 6 dígitos",
        }),
    )

class ComandaScanForm(forms.Form):
    code = forms.RegexField(
        label="Código de la comanda",
        regex=r"\ASOL-[0-9]{1,18}\Z",
        max_length=22,
        error_messages={
            "required": "Escanea una comanda.",
            "invalid": "Usa un código como SOL-000001.",
        },
        widget=forms.TextInput(attrs={
            "autofocus": True,
            "autocomplete": "off",
            "spellcheck": "false",
            "placeholder": "SOL-000001",
        }),
    )