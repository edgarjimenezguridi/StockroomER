"""Autoservicio de alta inicial de NIP, siempre con autorización emitida por jefatura."""
from django import forms
from django.contrib.admin.models import LogEntry, CHANGE
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .credentials import authorize_pin_setup, get_credential_for_setup
from .duplicate_authorization_admin import es_jefe
from .models import EmployeeCredential

IDENTIFICATION_SALT = "stockroom.worker-pin-onboarding"
MAX_IDENTIFICATION_AGE = 5 * 60


class AuthorizationForm(forms.Form):
    authorization = forms.CharField(
        label="Código de autorización de jefatura",
        max_length=2048,
        widget=forms.Textarea(attrs={"rows": 3, "autocomplete": "off", "spellcheck": "false"}),
    )


@never_cache
@sensitive_post_parameters("authorization")
@require_http_methods(["GET", "POST"])
def inicio_nip_trabajador(request):
    signed = request.session.get("pin_setup_pending")
    if not signed:
        return redirect("acceso_empleado")
    try:
        data = signing.loads(signed, salt=IDENTIFICATION_SALT, max_age=MAX_IDENTIFICATION_AGE)
        credential = EmployeeCredential.objects.select_related("employee").get(
            barcode=data["barcode"], is_active=True, employee__is_active=True
        )
    except (signing.BadSignature, EmployeeCredential.DoesNotExist, KeyError, TypeError):
        request.session.pop("pin_setup_pending", None)
        return redirect("acceso_empleado")

    if credential.pin_hash:
        request.session.pop("pin_setup_pending", None)
        return redirect("acceso_empleado")

    form = AuthorizationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        authorization = form.cleaned_data["authorization"].strip()
        try:
            matching = get_credential_for_setup(barcode=credential.barcode, authorization=authorization)
            if matching.pk != credential.pk:
                raise ValidationError("La autorización no corresponde a tu credencial.")
        except ValidationError as exc:
            form.add_error("authorization", exc)
        else:
            request.session.pop("pin_setup_pending", None)
            request.session["pin_setup_authorization"] = authorization
            return redirect("activar_nip", barcode=credential.barcode)

    return render(request, "stockroom/credenciales/inicio_nip.html", {"credential": credential, "form": form})


@never_cache
@login_required(login_url="acceso_jefe")
@require_http_methods(["GET", "POST"])
def autorizar_nip_jefe(request, employee_id):
    if not es_jefe(request.user):
        raise PermissionDenied("Solo jefatura puede emitir autorizaciones de NIP.")

    credential = get_object_or_404(EmployeeCredential.objects.select_related("employee"), employee_id=employee_id)
    authorization = None
    if request.method == "POST":
        try:
            authorization = authorize_pin_setup(credential=credential, operator=request.user)
            # Registrar únicamente emisión y responsable: nunca guardar token ni NIP.
            LogEntry.objects.log_actions(
                user_id=request.user.pk,
                queryset=EmployeeCredential.objects.filter(pk=credential.pk),
                action_flag=CHANGE,
                change_message="Autorización inicial de NIP emitida",
            )
        except ValidationError as exc:
            return render(request, "stockroom/jefe/autorizar_nip.html", {
                "credential": credential, "error": " ".join(exc.messages)
            }, status=400)
    return render(request, "stockroom/jefe/autorizar_nip.html", {
        "credential": credential, "authorization": authorization
    })
