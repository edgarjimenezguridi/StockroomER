from django.shortcuts import render
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .credentials import activate_pin, get_credential_for_setup
from .forms import PinSetupForm

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
