from django.shortcuts import render, redirect
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from django.core import signing

from .credentials import (
    activate_pin,
    get_credential_for_setup,
    verify_employee_pin,
)

from .forms import (
    PinSetupForm,
    CredentialScanForm,
    EmployeeNumberAccessForm,
    EmployeePinForm,
)
from .models import EmployeeCredential


# Create your views here.

@never_cache
@sensitive_post_parameters("pin", "pin_confirmation")
@require_http_methods(["GET", "POST"])
def activar_nip(request, barcode):
    authorization = request.session.get("pin_setup_authorization")
    if not authorization:
        return HttpResponseForbidden(
            "Solicita al almacenista la autorización para activar tu NIP."
        )

    try:
        credential = get_credential_for_setup(
            barcode=barcode,
            authorization=authorization,
        )
    except ValidationError as exc:
        return HttpResponseForbidden(" ".join(exc.messages))

    form = PinSetupForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        try:
            activate_pin(
                barcode=barcode,
                authorization=authorization,
                pin=form.cleaned_data["pin"],
                pin_confirmation=form.cleaned_data["pin_confirmation"],
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            request.session.pop("pin_setup_authorization", None)
            return HttpResponse("Tu NIP quedó activado.")

    return render(
        request,
        "stockroom/activar_nip.html",
        {"credential": credential, "form": form},
    )

@never_cache
@sensitive_post_parameters("pin")
@require_http_methods(["GET", "POST"])
def acceso_empleado(request):
    scan_form = CredentialScanForm()
    number_form = EmployeeNumberAccessForm()
    pin_form = EmployeePinForm()
    credential = None

    # Volver a esta pantalla termina el acceso previo del trabajador.
    request.session.pop("worker_employee_id", None)
    request.session.pop("worker_credential_id", None)

    pending = request.session.get("pending_worker")

    if pending:
        try:
            data = signing.loads(
                pending,
                salt="stockroom.worker-identification",
                max_age=300,
            )
            credential = EmployeeCredential.objects.select_related(
                "employee"
            ).filter(
                barcode=data["barcode"],
                is_active=True,
                employee__is_active=True,
            ).exclude(pin_hash="").first()
        except signing.BadSignature:
            credential = None

        if credential is None:
            request.session.pop("pending_worker", None)

    if request.method == "POST":
        method = request.POST.get("access_method")

        if method == "change":
            request.session.pop("pending_worker", None)
            return redirect("acceso_empleado")

        if method == "pin":
            if credential is None:
                return redirect("acceso_empleado")

            pin_form = EmployeePinForm(request.POST)

            if pin_form.is_valid():
                try:
                    employee = verify_employee_pin(
                        barcode=credential.barcode,
                        pin=pin_form.cleaned_data["pin"],
                    )
                except ValidationError as exc:
                    pin_form.add_error(None, exc)
                else:
                    # Elimina también cualquier sesión administrativa.
                    request.session.flush()
                    request.session["worker_employee_id"] = employee.pk
                    request.session["worker_credential_id"] = credential.pk
                    request.session.set_expiry(10 * 60)

                    return HttpResponse(
                        "NIP verificado. Acceso de trabajador iniciado. "
                        "El panel de pedidos se conectará en el siguiente paso."
                    )

        elif method in ("barcode", "employee_id"):
            request.session.pop("pending_worker", None)
            credential = None

            if method == "barcode":
                scan_form = CredentialScanForm(request.POST)
                selected_form = scan_form
            else:
                number_form = EmployeeNumberAccessForm(request.POST)
                selected_form = number_form

            if selected_form.is_valid():
                credentials = EmployeeCredential.objects.select_related(
                    "employee"
                ).filter(
                    is_active=True,
                    employee__is_active=True,
                )

                if method == "barcode":
                    credential = credentials.filter(
                        barcode=scan_form.cleaned_data["barcode"],
                    ).first()
                else:
                    credential = credentials.filter(
                        employee__employee_id=(
                            number_form.cleaned_data["employee_id"]
                        ),
                    ).first()

                if credential is None:
                    selected_form.add_error(
                        None, "No encontramos una credencial activa."
                    )
                elif not credential.pin_hash:
                    selected_form.add_error(
                        None, "Solicita al almacenista activar tu NIP."
                    )
                    credential = None
                else:
                    request.session["pending_worker"] = signing.dumps(
                        {"barcode": str(credential.barcode)},
                        salt="stockroom.worker-identification",
                    )
                    return redirect("acceso_empleado")

        else:
            return HttpResponse("Forma de acceso no válida.", status=400)

    return render(
        request,
        "stockroom/acceso_empleado.html",
        {
            "scan_form": scan_form,
            "number_form": number_form,
            "pin_form": pin_form,
            "credential": credential,
        },
    )