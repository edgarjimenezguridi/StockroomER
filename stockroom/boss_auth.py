
from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
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


@never_cache
@login_required(login_url="acceso_jefe")
@require_POST
def salir_jefe(request):
    """Cierre de sesión de jefatura: explícito y protegido por CSRF."""
    if not es_jefe(request.user):
        raise PermissionDenied("Solo jefatura puede utilizar este acceso.")
    logout(request)
    return redirect("acceso_jefe")
