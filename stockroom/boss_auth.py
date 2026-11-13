
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.urls import reverse_lazy


def es_jefe(user):
    return (
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and (
            user.is_superuser
            or user.groups.filter(name="Jefes").exists()
        )
    )


class AccesoJefeForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)

        if not es_jefe(user):
            raise forms.ValidationError(
                "Esta cuenta no tiene permiso para acceder al panel del jefe.",
                code="sin_permiso",
            )


class AccesoJefeView(LoginView):
    template_name = "stockroom/jefe/acceso.html"
    authentication_form = AccesoJefeForm
    next_page = reverse_lazy("panel_jefe")
