from django.shortcuts import render, redirect
from django.core.exceptions import ValidationError
from django.http import HttpResponse, HttpResponseForbidden
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods
from django.core import signing
from .selectors import catalogo_articulos
from django.contrib import messages
from .cart import set_cart_quantity, submit_cart
from .models import MaterialRequestLine
from .models import MaterialRequest
from django.shortcuts import get_object_or_404
from .fulfillment import confirm_request_receipt
from django.db.models import F
from .models import QuantityIssue
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from .forms import ComandaScanForm
from django.contrib.auth.decorators import login_required


import base64

from barcode import Code128
from barcode.writer import SVGWriter

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
        "stockroom/credenciales/activar_nip.html",
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

                    return redirect("panel_empleado")

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
        "stockroom/empleados/acceso_empleado.html",
        {
            "scan_form": scan_form,
            "number_form": number_form,
            "pin_form": pin_form,
            "credential": credential,
        },
    )

@never_cache
@require_http_methods(["GET"])
def panel_empleado(request):
    employee_id = request.session.get("worker_employee_id")
    credential_id = request.session.get("worker_credential_id")

    if not employee_id or not credential_id:
        return redirect("acceso_empleado")

    credential = EmployeeCredential.objects.select_related(
        "employee"
    ).filter(
        pk=credential_id,
        employee_id=employee_id,
        is_active=True,
        employee__is_active=True,
    ).exclude(pin_hash="").first()

    if credential is None:
        request.session.flush()
        return redirect("acceso_empleado")

    search = request.GET.get("q", "").strip()

    cart_lines = MaterialRequestLine.objects.filter(
        request__employee_id=credential.employee_id,
        request__status=MaterialRequest.Status.DRAFT,
    ).select_related("article")

    my_requests = (
        MaterialRequest.objects.filter(
            employee_id=credential.employee_id,
        )
        .exclude(status=MaterialRequest.Status.DRAFT)
        .prefetch_related("lines__article")
        .order_by("-created_at", "-pk")[:10]
    )

    pending_issues = (
        QuantityIssue.objects.filter(
            employee_id=credential.employee_id,
            requires_return=True,
            returned_quantity__lt=F("quantity"),
        )
        .select_related("stock__article", "tool__article")
        .annotate(
            pending_quantity=F("quantity") - F("returned_quantity"),
        )
        .order_by("issued_at", "pk")
    )

    return render(
        request,
        "stockroom/empleados/panel_empleado.html",
        {
            "employee": credential.employee,
            "articles": catalogo_articulos(search),
            "search": search,
            "cart_lines": cart_lines,
            "my_requests": my_requests,
            "pending_issues": pending_issues,
        },
    )

@never_cache
@require_http_methods(["POST"])
def salir_empleado(request):
    request.session.flush()
    return redirect("acceso_empleado")

@never_cache
@require_http_methods(["POST"])
def guardar_articulo_carrito(request, article_id):
    employee_id = request.session.get("worker_employee_id")
    credential_id = request.session.get("worker_credential_id")

    if not employee_id or not credential_id:
        return redirect("acceso_empleado")

    credential = EmployeeCredential.objects.filter(
        pk=credential_id,
        employee_id=employee_id,
        is_active=True,
        employee__is_active=True,
    ).exclude(pin_hash="").first()

    if credential is None:
        request.session.flush()
        return redirect("acceso_empleado")

    try:
        quantity = int(request.POST.get("quantity", ""))
    except (TypeError, ValueError):
        messages.error(request, "Escribe una cantidad entera válida.")
        return redirect("panel_empleado")

    try:
        line = set_cart_quantity(
            employee_id=credential.employee_id,
            article_id=article_id,
            quantity=quantity,
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request,
            f"Carrito actualizado: {line.article.name}, "
            f"{line.requested_quantity} piezas en total.",
        )

    return redirect("panel_empleado")

@never_cache
@require_http_methods(["POST"])
def quitar_articulo_carrito(request, line_id):
    employee_id = request.session.get("worker_employee_id")
    credential_id = request.session.get("worker_credential_id")

    if not employee_id or not credential_id:
        return redirect("acceso_empleado")

    credential = EmployeeCredential.objects.filter(
        pk=credential_id,
        employee_id=employee_id,
        is_active=True,
        employee__is_active=True,
    ).exclude(pin_hash="").first()

    if credential is None:
        request.session.flush()
        return redirect("acceso_empleado")

    deleted, _ = MaterialRequestLine.objects.filter(
        pk=line_id,
        request__employee_id=credential.employee_id,
        request__status="draft",
    ).delete()

    if deleted:
        messages.success(request, "Artículo retirado del carrito.")
    else:
        messages.error(
            request,
            "El artículo ya no está en tu carrito abierto.",
        )

    return redirect("panel_empleado")

@never_cache
@require_http_methods(["POST"])
def enviar_solicitud(request, cart_id):
    employee_id = request.session.get("worker_employee_id")
    credential_id = request.session.get("worker_credential_id")

    if not employee_id or not credential_id:
        return redirect("acceso_empleado")

    credential = EmployeeCredential.objects.filter(
        pk=credential_id,
        employee_id=employee_id,
        is_active=True,
        employee__is_active=True,
    ).exclude(pin_hash="").first()

    if credential is None:
        request.session.flush()
        return redirect("acceso_empleado")

    try:
        material_request = submit_cart(
            employee_id=credential.employee_id,
            cart_id=cart_id,
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request,
            f"Solicitud #{material_request.pk} enviada al almacén. "
            "Todavía no se ha registrado ninguna entrega.",
        )

    return redirect("panel_empleado")

@never_cache
@sensitive_post_parameters("pin")
@require_http_methods(["GET", "POST"])
def confirmar_recibido(request, request_id):
    employee_id = request.session.get("worker_employee_id")
    credential_id = request.session.get("worker_credential_id")

    if not employee_id or not credential_id:
        return redirect("acceso_empleado")

    credential = EmployeeCredential.objects.filter(
        pk=credential_id,
        employee_id=employee_id,
        is_active=True,
        employee__is_active=True,
    ).exclude(pin_hash="").first()

    if credential is None:
        request.session.flush()
        return redirect("acceso_empleado")

    solicitud = get_object_or_404(
        MaterialRequest.objects.prefetch_related(
            "lines__article",
            "lines__selected_pieces__tool",
        ),
        pk=request_id,
        employee_id=credential.employee_id,
    )

    if solicitud.status != MaterialRequest.Status.PREPARED:
        messages.error(
            request,
            "Esta solicitud no está pendiente de confirmar recibido.",
        )
        return redirect("panel_empleado")

    form = EmployeePinForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        try:
            expected_version = int(
                request.POST.get("preparation_version", "")
            )
        except (TypeError, ValueError):
            messages.error(
                request,
                "No se pudo validar la versión de la solicitud. "
                "Ábrela nuevamente.",
            )
            return redirect("panel_empleado")

        if expected_version != solicitud.preparation_version:
            messages.error(
                request,
                "El almacenista cambió la preparación. "
                "Revisa las cantidades actuales antes de confirmar.",
            )
            return redirect("panel_empleado")

        try:
            confirm_request_receipt(
                request_id=solicitud.pk,
                employee_id=credential.employee_id,
                credential_id=credential.pk,
                pin=form.cleaned_data["pin"],
                expected_version=expected_version,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(
                request,
                f"Recibido confirmado. Solicitud #{solicitud.pk} cerrada.",
            )
            return redirect("panel_empleado")

    return render(
        request,
        "stockroom/empleados/confirmar_recibido.html",
        {"solicitud": solicitud, "form": form},
    )

@never_cache
@require_http_methods(["GET"])
def comanda_empleado(request, request_id):
    employee_id = request.session.get("worker_employee_id")
    credential_id = request.session.get("worker_credential_id")

    if not employee_id or not credential_id:
        return redirect("acceso_empleado")

    credential = EmployeeCredential.objects.filter(
        pk=credential_id,
        employee_id=employee_id,
        is_active=True,
        employee__is_active=True,
    ).exclude(pin_hash="").first()

    if credential is None:
        request.session.flush()
        return redirect("acceso_empleado")

    solicitud = get_object_or_404(
        MaterialRequest.objects.select_related(
            "employee"
        ).prefetch_related(
            "lines__article"
        ).exclude(
            status=MaterialRequest.Status.DRAFT,
        ),
        pk=request_id,
        employee_id=credential.employee_id,
    )

    barcode_value = f"SOL-{solicitud.pk:06d}"

    barcode_svg = Code128(
        barcode_value,
        writer=SVGWriter(),
    ).render()

    barcode_image = (
        "data:image/svg+xml;base64,"
        + base64.b64encode(barcode_svg).decode("ascii")
    )

    return render(
        request,
        "stockroom/empleados/comanda_empleado.html",
        {
            "solicitud": solicitud,
            "barcode_value": barcode_value,
            "barcode_image": barcode_image,
        },
    )

@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def escanear_comanda(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.view_materialrequest")
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar solicitudes del almacén."
        )

    form = ComandaScanForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        code = form.cleaned_data["code"]
        request_id = int(code.split("-", 1)[1])

        solicitud = MaterialRequest.objects.exclude(
            status=MaterialRequest.Status.DRAFT,
        ).filter(pk=request_id).first()

        if solicitud is None:
            form.add_error(
                "code",
                "No encontramos una solicitud enviada con ese folio.",
            )
        else:
            return redirect(
                "detalle_solicitud_almacen",
                request_id=solicitud.pk,
            )

    return render(
        request,
        "stockroom/almacen/escanear_comanda.html",
        {"form": form},
    )