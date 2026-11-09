from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import redirect
from django.views.decorators.http import require_http_methods
from .models import MaterialRequestLine
from .warehouse_forms import PrepareWarehouseLineForm
from .fulfillment import prepare_request_line
from django.views.decorators.http import require_POST
from .fulfillment import finish_request_preparation
from django.views.decorators.debug import sensitive_post_parameters
from .forms import EmployeePinForm
from .models import EmployeeCredential
from .fulfillment import confirm_request_receipt

from .models import MaterialRequest
from .warehouse_forms import WarehouseLoginForm


class WarehouseLoginView(LoginView):
    template_name = "stockroom/acceso_almacen.html"
    authentication_form = WarehouseLoginForm

    def form_valid(self, form):
        response = super().form_valid(form)

        for key in (
            "worker_employee_id",
            "worker_credential_id",
            "pending_worker",
            "pin_setup_authorization",
        ):
            self.request.session.pop(key, None)

        self.request.session.set_expiry(0)
        return response

    def get_success_url(self):
        return reverse("panel_almacen")


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def panel_almacen(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.view_materialrequest")
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar las solicitudes del almacén."
        )

    solicitudes = MaterialRequest.objects.select_related(
        "employee",
    ).filter(
        status__in=[
            MaterialRequest.Status.SUBMITTED,
            MaterialRequest.Status.PREPARED,
        ],
    ).order_by("submitted_at", "pk")

    return render(
        request,
        "stockroom/panel_almacen.html",
        {
            "por_preparar": solicitudes.filter(
                status=MaterialRequest.Status.SUBMITTED,
            ),
            "por_confirmar": solicitudes.filter(
                status=MaterialRequest.Status.PREPARED,
            ),
        },
    )

@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def detalle_solicitud_almacen(request, request_id):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.view_materialrequest")
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar las solicitudes del almacén."
        )

    solicitud = get_object_or_404(
        MaterialRequest.objects.select_related(
            "employee",
        ).prefetch_related(
            "lines__article",
            "lines__selected_pieces__tool",
        ).exclude(
            status=MaterialRequest.Status.DRAFT,
        ),
        pk=request_id,
    )

    return render(
        request,
        "stockroom/detalle_solicitud_almacen.html",
        {"solicitud": solicitud},
    )

@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def preparar_articulo_almacen(request, request_id, line_id):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perms([
            "stockroom.view_materialrequest",
            "stockroom.change_materialrequest",
        ])
    ):
        raise PermissionDenied(
            "No tienes permiso para preparar solicitudes."
        )

    linea = get_object_or_404(
        MaterialRequestLine.objects.select_related(
            "request__employee",
            "article",
        ),
        pk=line_id,
        request_id=request_id,
    )

    if linea.request.status != MaterialRequest.Status.SUBMITTED:
        messages.error(
            request,
            "Esta solicitud ya no está disponible para preparación.",
        )
        return redirect(
            "detalle_solicitud_almacen",
            request_id=request_id,
        )

    form = PrepareWarehouseLineForm(
        request.POST if request.method == "POST" else None,
        line=linea,
    )

    if request.method == "POST" and form.is_valid():
        herramientas = form.cleaned_data.get("tools", [])

        try:
            prepare_request_line(
                line_id=linea.pk,
                quantity=form.cleaned_data["quantity"],
                operator=request.user,
                tool_ids=[tool.pk for tool in herramientas],
            )
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(
                request,
                f"Preparación guardada: {linea.article.name}.",
            )
            return redirect(
                "detalle_solicitud_almacen",
                request_id=request_id,
            )

    return render(
        request,
        "stockroom/preparar_articulo_almacen.html",
        {
            "linea": linea,
            "form": form,
        },
    )

@never_cache
@login_required(login_url="acceso_almacen")
@require_POST
def terminar_preparacion_almacen(request, request_id):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perms([
            "stockroom.view_materialrequest",
            "stockroom.change_materialrequest",
        ])
    ):
        raise PermissionDenied(
            "No tienes permiso para preparar solicitudes."
        )

    get_object_or_404(MaterialRequest, pk=request_id)

    try:
        finish_request_preparation(
            request_id=request_id,
            operator=request.user,
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request,
            "Preparación terminada. Falta la confirmación "
            "de recibido del trabajador.",
        )

    return redirect(
        "detalle_solicitud_almacen",
        request_id=request_id,
    )

@never_cache
@sensitive_post_parameters("pin")
@login_required(login_url="acceso_almacen")
@require_POST
def confirmar_entrega_almacen(request, request_id):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perms([
            "stockroom.view_materialrequest",
            "stockroom.change_materialrequest",
            "stockroom.add_quantityissue",
        ])
    ):
        raise PermissionDenied(
            "No tienes permiso para registrar entregas."
        )

    solicitud = get_object_or_404(
        MaterialRequest,
        pk=request_id,
    )

    form = EmployeePinForm(request.POST)

    if not form.is_valid():
        messages.error(
            request,
            "Introduce un NIP válido para confirmar recibido.",
        )
        return redirect(
            "detalle_solicitud_almacen",
            request_id=request_id,
        )

    try:
        expected_version = int(
            request.POST.get("preparation_version", "")
        )
    except (TypeError, ValueError):
        messages.error(
            request,
            "Recarga la solicitud y revisa las cantidades antes de confirmar.",
        )
        return redirect(
            "detalle_solicitud_almacen",
            request_id=request_id,
        )

    credential = EmployeeCredential.objects.filter(
        employee_id=solicitud.employee_id,
        is_active=True,
        employee__is_active=True,
    ).first()

    if credential is None:
        messages.error(
            request,
            "El trabajador no tiene una credencial activa.",
        )
        return redirect(
            "detalle_solicitud_almacen",
            request_id=request_id,
        )

    try:
        confirm_request_receipt(
            request_id=solicitud.pk,
            employee_id=solicitud.employee_id,
            credential_id=credential.pk,
            pin=form.cleaned_data["pin"],
            expected_version=expected_version,
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(
            request,
            "Recibido confirmado. La solicitud quedó cerrada "
            "y las entregas fueron registradas.",
        )

    return redirect(
        "detalle_solicitud_almacen",
        request_id=request_id,
    )