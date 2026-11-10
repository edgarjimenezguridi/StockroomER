from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.exceptions import ( 
    PermissionDenied, 
    ValidationError,
)
from django.shortcuts import get_object_or_404, render, redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.db.models import ( 
    F, 
    Sum, 
    Q, 
    Count,
    Case, 
    When, 
    Value, 
    IntegerField,
)
from django.db.models.functions import Coalesce, Greatest
from django.contrib import messages
from django.views.decorators.debug import sensitive_post_parameters
from django.contrib.auth import logout
from datetime import date
from django.utils import timezone
from django.core.paginator import Paginator
from django.views.decorators.http import ( 
    require_GET, 
    require_http_methods, 
    require_POST,
)
from .selectors import catalogo_articulos
from .fulfillment import (
    prepare_request_line, 
    finish_request_preparation,
    confirm_request_receipt,
)
from .services import (
    register_quantity_return,  
    register_stock_entry,
    register_damage_resolution,
    register_stock_entry_correction,
    register_return_and_exchange,
)
from .forms import EmployeePinForm 
from .warehouse_forms import (
    WarehouseLoginForm, 
    PrepareWarehouseLineForm,
    WarehouseReturnForm,
    WarehouseStockEntryForm,
    WarehouseDamageResolutionForm,
    WarehouseStockCorrectionForm,
)
from .models import (
Employee, 
QuantityIssue, 
QuantityReturn,
EmployeeCredential,
MaterialRequest, 
MaterialRequestLine,
StockEntry,
DamageResolution,
StockEntryCorrection,
Article,
Tool,
ToolCategory,
)
import csv
from django.http import HttpResponse, request


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

    puede_ver_adeudos = request.user.has_perms([
        "stockroom.view_employee",
        "stockroom.view_quantityissue",
    ])

    puede_ver_danos = request.user.has_perm(
        "stockroom.view_quantityreturn"
    )

    piezas_pendientes = 0
    piezas_danadas = 0

    if puede_ver_adeudos:
        piezas_pendientes = (
            QuantityIssue.objects.filter(
                requires_return=True,
                returned_quantity__lt=F("quantity"),
            ).aggregate(
                total=Sum(F("quantity") - F("returned_quantity"))
            )["total"] or 0
        )

    if puede_ver_danos:
        piezas_danadas = (
            QuantityReturn.objects.filter(
                condition=QuantityReturn.Condition.DAMAGED,
                resolved_quantity__lt=F("quantity"),
            ).aggregate(
                total=Sum(F("quantity") - F("resolved_quantity"))
            )["total"] or 0
        )

    # Alertas de inventario bajo
    puede_ver_alertas = request.user.has_perms([
        "stockroom.view_article",
        "stockroom.view_quantitystock",
        "stockroom.view_tool",
    ])

    articulos_bajos = 0

    if puede_ver_alertas:
        # Artículos controlados por cantidad
        bajos_cantidad = (
            Article.objects.filter(
                is_active=True,
                minimum_stock__gt=0,
                tracking_mode=Article.TrackingMode.QUANTITY,
            )
            .annotate(
                disponibles=Coalesce(
                    F("quantity_stock__available_quantity"),
                    Value(0),
                    output_field=IntegerField(),
                )
            )
            .filter(
                disponibles__lt=F("minimum_stock")
            )
            .count()
        )

        # Artículos controlados por pieza individual
        bajos_individuales = (
            Article.objects.filter(
                is_active=True,
                minimum_stock__gt=0,
                tracking_mode=Article.TrackingMode.INDIVIDUAL,
            )
            .annotate(
                disponibles=Count(
                    "individual_tools",
                    filter=Q(
                        individual_tools__inventory_status=(
                            Tool.InventoryStatus.AVAILABLE
                        ),
                        individual_tools__is_active=True,
                    ),
                    distinct=True,
                )
            )
            .filter(
                disponibles__lt=F("minimum_stock")
            )
            .count()
        )

        articulos_bajos = (
            bajos_cantidad + bajos_individuales
        )



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
            "inventario": catalogo_articulos(),
            "piezas_pendientes": piezas_pendientes,
            "piezas_danadas": piezas_danadas,
            "puede_ver_adeudos": puede_ver_adeudos,
            "puede_ver_danos": puede_ver_danos,
            "articulos_bajos": articulos_bajos,
            "puede_ver_alertas": puede_ver_alertas,

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


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def adeudos_almacen(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perms([
            "stockroom.view_employee",
            "stockroom.view_quantityissue",
        ])
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar adeudos."
        )

    employee_number = request.GET.get(
        "employee_id", ""
    ).strip()

    busqueda = request.GET.get("q", "").strip()[:100]

    trabajador = None

    if employee_number:
        trabajador = Employee.objects.filter(
            employee_id=employee_number
        ).first()

    entregas = (
        QuantityIssue.objects.filter(
            requires_return=True,
            returned_quantity__lt=F("quantity"),
        )
        .select_related(
            "employee",
            "stock__article",
            "tool__article",
        )
        .annotate(
            pending_quantity=(
                F("quantity") - F("returned_quantity")
            )
        )
    )

    # Mantener compatibilidad con búsquedas por empleado
    if employee_number:
        entregas = entregas.filter(
            employee__employee_id=employee_number
        )

    # Búsqueda por trabajador o artículo
    if busqueda:
        for termino in busqueda.split():
            entregas = entregas.filter(
                Q(employee__employee_id__icontains=termino)
                | Q(employee__first_name__icontains=termino)
                | Q(employee__last_name__icontains=termino)
                | Q(stock__article__article_code__icontains=termino)
                | Q(stock__article__name__icontains=termino)
                | Q(tool__tool_code__icontains=termino)
                | Q(tool__name__icontains=termino)
            )

    entregas = entregas.order_by("issued_at", "pk")

    total_piezas = entregas.aggregate(
        total=Sum(
            F("quantity") - F("returned_quantity")
        )
    )["total"] or 0

    paginador = Paginator(entregas, 25)
    pagina = paginador.get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "stockroom/adeudos_almacen.html",
        {
            "employee_number": employee_number,
            "trabajador": trabajador,
            "busqueda": busqueda,
            "entregas": pagina.object_list,
            "pagina": pagina,
            "total_entregas": paginador.count,
            "total_piezas": total_piezas,
            "puede_devolver": request.user.has_perm(
                "stockroom.add_quantityreturn"
            ),
        },
    )


@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def registrar_devolucion_almacen(request, issue_id):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perms([
            "stockroom.view_quantityissue",
            "stockroom.add_quantityreturn",
        ])
    ):
        raise PermissionDenied(
            "No tienes permiso para registrar devoluciones."
        )

    entrega = get_object_or_404(
        QuantityIssue.objects.select_related(
            "employee",
            "stock__article",
            "tool__article",
        ).annotate(
            pending_quantity=F("quantity") - F("returned_quantity"),
        ),
        pk=issue_id,
        requires_return=True,
    )

    if entrega.pending_quantity < 1:
        messages.error(request, "Esta entrega ya no tiene piezas pendientes.")
        return redirect(
            f"{reverse('adeudos_almacen')}?employee_id="
            f"{entrega.employee.employee_id}"
        )

    form = WarehouseReturnForm(
        request.POST if request.method == "POST" else None,
        issue=entrega,
        pending_quantity=entrega.pending_quantity,
    )

    if request.method == "POST" and form.is_valid():
        devolucion = QuantityReturn(
            issue=entrega,
            quantity=form.cleaned_data["quantity"],
            condition=form.cleaned_data["condition"],
            reason=form.cleaned_data["reason"],
            notes=form.cleaned_data["notes"],
        )

        operation = form.cleaned_data["operation"]
        replacement_tool = form.cleaned_data.get("replacement_tool")

        if (
            operation == "exchange"
            and not request.user.has_perm("stockroom.add_quantityissue")
        ):
            raise PermissionDenied(
                "No tienes permiso para entregar piezas de reemplazo."
            )

        try:
            if operation == "exchange":
                register_return_and_exchange(
                    devolucion,
                    replacement_tool_id=(
                        replacement_tool.pk
                        if replacement_tool
                        else None
                    ),
                )
            else:
                register_quantity_return(devolucion)

        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))

        else:
            if operation == "exchange":
                messages.success(
                    request,
                    "Devolución y cambio registrados correctamente.",
                )
            else:
                messages.success(
                    request,
                    "Devolución registrada correctamente.",
                )

            return redirect(
                f"{reverse('adeudos_almacen')}?employee_id="
                f"{entrega.employee.employee_id}"
            )


    return render(
        request,
        "stockroom/registrar_devolucion_almacen.html",
        {
            "entrega": entrega,
            "form": form,
        },
    )

@never_cache
@login_required(login_url="acceso_almacen")
@require_POST
def salir_almacen(request):
    logout(request)
    return redirect("acceso_almacen")

@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def registrar_entrada_almacen(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.add_stockentry")
    ):
        raise PermissionDenied(
            "No tienes permiso para registrar entradas de almacén."
        )

    form = WarehouseStockEntryForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        entrada = StockEntry(
            stock=form.cleaned_data["stock"],
            quantity=form.cleaned_data["quantity"],
            reference=form.cleaned_data["reference"],
            notes=form.cleaned_data["notes"],
        )

        try:
            register_stock_entry(entrada)
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(
                request,
                "Entrada registrada y existencias actualizadas.",
            )
            return redirect("registrar_entrada_almacen")

    return render(
        request,
        "stockroom/registrar_entrada_almacen.html",
        {"form": form},
    )

@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def resolver_dano_almacen(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.add_damageresolution")
    ):
        raise PermissionDenied(
            "No tienes permiso para resolver piezas dañadas."
        )

    form = WarehouseDamageResolutionForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        resolucion = DamageResolution(
            source_return=form.cleaned_data["source_return"],
            quantity=form.cleaned_data["quantity"],
            outcome=form.cleaned_data["outcome"],
            reason=form.cleaned_data["reason"],
            notes=form.cleaned_data["notes"],
        )

        try:
            register_damage_resolution(resolucion)
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(
                request,
                "Resolución registrada y existencias actualizadas.",
            )
            return redirect("resolver_dano_almacen")

    return render(
        request,
        "stockroom/resolver_dano_almacen.html",
        {"form": form},
    )

@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def corregir_existencia_almacen(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.add_stockentrycorrection")
    ):
        raise PermissionDenied(
            "No tienes permiso para corregir existencias."
        )

    form = WarehouseStockCorrectionForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():
        correccion = StockEntryCorrection(
            entry=form.cleaned_data["entry"],
            quantity_delta=form.cleaned_data["quantity_delta"],
            reason=form.cleaned_data["reason"],
        )

        try:
            register_stock_entry_correction(
                correccion,
                user=request.user,
            )
        except ValidationError as exc:
            form.add_error(None, " ".join(exc.messages))
        else:
            messages.success(
                request,
                "Corrección registrada y existencias actualizadas.",
            )
            return redirect("corregir_existencia_almacen")

    return render(
        request,
        "stockroom/corregir_existencia_almacen.html",
        {"form": form},
    )


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def historial_almacen(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.view_materialrequest")
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar el historial."
        )

    filtro = request.GET.get("tipo", "todos")

    tipos_validos = {
        "todos", "entrada", "entrega", "cambio",
        "devolucion", "resolucion", "correccion",
    }

    if filtro not in tipos_validos:
        filtro = "todos"

    movimientos = []

    def agregar(fecha, tipo, clase, articulo, cantidad, detalle):
        movimientos.append({
            "fecha": fecha,
            "tipo": tipo,
            "clase": clase,
            "articulo": articulo,
            "cantidad": cantidad,
            "detalle": detalle,
        })

    # Entradas
    if filtro in ("todos", "entrada") and request.user.has_perm(
        "stockroom.view_stockentry"
    ):
        entradas = StockEntry.objects.select_related(
            "stock__article"
        ).order_by("-received_at", "-pk")

        for entrada in entradas:
            agregar(
                entrada.received_at,
                "Entrada",
                "entrada",
                str(entrada.stock.article),
                entrada.quantity,
                f"Referencia: {entrada.reference or 'Sin referencia'}",
            )

    # Entregas y reemplazos
    if filtro in ("todos", "entrega", "cambio") and request.user.has_perm(
        "stockroom.view_quantityissue"
    ):
        entregas = QuantityIssue.objects.select_related(
            "employee", "tool", "stock__article"
        ).order_by("-issued_at", "-pk")

        for entrega in entregas:
            es_cambio = entrega.replacement_for_id is not None
            clase = "cambio" if es_cambio else "entrega"

            if filtro not in ("todos", clase):
                continue

            articulo = (
                str(entrega.tool)
                if entrega.tool_id
                else str(entrega.stock.article)
            )

            detalle = f"Trabajador: {entrega.employee}"

            if es_cambio:
                detalle += (
                    f" | Reemplazo de devolución "
                    f"#{entrega.replacement_for_id}"
                )

            agregar(
                entrega.issued_at,
                "Cambio / reemplazo" if es_cambio else "Entrega",
                clase,
                articulo,
                entrega.quantity,
                detalle,
            )

    # Devoluciones
    if filtro in ("todos", "devolucion") and request.user.has_perm(
        "stockroom.view_quantityreturn"
    ):
        devoluciones = QuantityReturn.objects.select_related(
            "issue__employee",
            "issue__tool",
            "issue__stock__article",
        ).order_by("-returned_at", "-pk")

        for devolucion in devoluciones:
            entrega = devolucion.issue

            articulo = (
                str(entrega.tool)
                if entrega.tool_id
                else str(entrega.stock.article)
            )

            detalle = (
                f"Trabajador: {entrega.employee} | "
                f"Condición: {devolucion.get_condition_display()}"
            )

            if devolucion.reason:
                detalle += f" | Motivo: {devolucion.reason}"

            agregar(
                devolucion.returned_at,
                "Devolución",
                "devolucion",
                articulo,
                devolucion.quantity,
                detalle,
            )

    # Resoluciones de daños
    if filtro in ("todos", "resolucion") and request.user.has_perm(
        "stockroom.view_damageresolution"
    ):
        resoluciones = DamageResolution.objects.select_related(
            "source_return__issue__tool",
            "source_return__issue__stock__article",
        ).order_by("-resolved_at", "-pk")

        for resolucion in resoluciones:
            entrega = resolucion.source_return.issue

            articulo = (
                str(entrega.tool)
                if entrega.tool_id
                else str(entrega.stock.article)
            )

            agregar(
                resolucion.resolved_at,
                "Resolución de daño",
                "resolucion",
                articulo,
                resolucion.quantity,
                resolucion.get_outcome_display(),
            )

    # Correcciones de existencias
    if filtro in ("todos", "correccion") and request.user.has_perm(
        "stockroom.view_stockentrycorrection"
    ):
        correcciones = StockEntryCorrection.objects.select_related(
            "entry__stock__article", "recorded_by"
        ).order_by("-created_at", "-pk")

        for correccion in correcciones:
            agregar(
                correccion.created_at,
                "Corrección",
                "correccion",
                str(correccion.entry.stock.article),
                correccion.quantity_delta,
                (
                    f"Entrada #{correccion.entry_id} | "
                    f"Motivo: {correccion.reason}"
                ),
            )

    movimientos.sort(
        key=lambda movimiento: movimiento["fecha"],
        reverse=True,
    )

    # Buscar movimientos
    busqueda = request.GET.get("q", "").strip()[:100]

    if busqueda:
        texto = busqueda.casefold()

        movimientos = [
            movimiento
            for movimiento in movimientos
            if texto in (
                f"{movimiento['articulo']} "
                f"{movimiento['detalle']} "
                f"{movimiento['tipo']}"
            ).casefold()
        ]

    # Filtrar por fechas
    desde = request.GET.get("desde", "")
    hasta = request.GET.get("hasta", "")

    try:
        fecha_desde = date.fromisoformat(desde) if desde else None
    except ValueError:
        fecha_desde = None

    try:
        fecha_hasta = date.fromisoformat(hasta) if hasta else None
    except ValueError:
        fecha_hasta = None

    if fecha_desde or fecha_hasta:
        filtrados = []

        for movimiento in movimientos:
            fecha_movimiento = timezone.localtime(
                movimiento["fecha"]
            ).date()

            if fecha_desde and fecha_movimiento < fecha_desde:
                continue

            if fecha_hasta and fecha_movimiento > fecha_hasta:
                continue

            filtrados.append(movimiento)

        movimientos = filtrados

    total_movimientos = len(movimientos)

    # Exportar historial a CSV compatible con Excel
    if request.GET.get("exportar") == "csv":
        response = HttpResponse(
            content_type="text/csv; charset=utf-8"
        )

        response["Content-Disposition"] = (
            'attachment; filename="StockroomER_Historial.csv"'
        )

        # UTF-8 y separador para Excel
        response.write("\ufeffsep=;\r\n")

        escritor = csv.writer(
            response,
            delimiter=";",
            lineterminator="\r\n",
        )

        escritor.writerow([
            "Fecha",
            "Movimiento",
            "Artículo / Pieza",
            "Cantidad",
            "Detalles",
        ])

        def texto_seguro(valor):
            texto = str(valor)

            if texto.lstrip().startswith(("=", "+", "-", "@")):
                return "'" + texto

            return texto

        for movimiento in movimientos:
            escritor.writerow([
                timezone.localtime(
                    movimiento["fecha"]
                ).strftime("%d/%m/%Y %H:%M"),

                texto_seguro(movimiento["tipo"]),
                texto_seguro(movimiento["articulo"]),
                movimiento["cantidad"],
                texto_seguro(movimiento["detalle"]),
            ])

        return response
    
    paginador = Paginator(movimientos, 25)
    pagina = paginador.get_page(request.GET.get("page"))



    return render(
        request,
        "stockroom/historial_almacen.html",
        {
            "movimientos": pagina.object_list,
            "pagina": pagina,
            "filtro": filtro,
            "busqueda": busqueda,
            "desde": desde,
            "hasta": hasta,
            "total_movimientos": total_movimientos,
        },
    )


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def consultar_existencias_almacen(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perms([
            "stockroom.view_article",
            "stockroom.view_quantitystock",
            "stockroom.view_tool",
        ])
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar existencias."
        )

    busqueda = request.GET.get("q", "").strip()[:100]
    categoria = request.GET.get("categoria", "").strip()
    control = request.GET.get("control", "").strip()
    solo_bajos = request.GET.get("alertas") == "1"

    articulos = Article.objects.select_related(
        "quantity_stock",
        "specification__tool_type__category",
    )

    if busqueda:
        for termino in busqueda.split():
            articulos = articulos.filter(
                Q(article_code__icontains=termino)
                | Q(name__icontains=termino)
                | Q(brand__icontains=termino)
                | Q(specification__name__icontains=termino)
                | Q(
                    pk__in=Tool.objects.filter(
                        tool_code__icontains=termino
                    ).values("article_id")
                )
            )

    if categoria:
        if categoria.isdecimal():
            articulos = articulos.filter(
                specification__tool_type__category_id=int(categoria)
            )
        else:
            articulos = articulos.none()

    if control in Article.TrackingMode.values:
        articulos = articulos.filter(tracking_mode=control)

    articulos = articulos.annotate(
        unidades_disponibles=Count(
            "individual_tools",
            filter=Q(
                individual_tools__inventory_status=(
                    Tool.InventoryStatus.AVAILABLE
                ),
                individual_tools__is_active=True,
            ),
            distinct=True,
        ),
        unidades_prestadas=Count(
            "individual_tools",
            filter=Q(
                individual_tools__inventory_status=(
                    Tool.InventoryStatus.LOANED
                )
            ),
            distinct=True,
        ),
        unidades_revision=Count(
            "individual_tools",
            filter=Q(
                individual_tools__inventory_status=(
                    Tool.InventoryStatus.QUARANTINE
                )
            ),
            distinct=True,
        ),
        unidades_bajas=Count(
            "individual_tools",
            filter=Q(
                individual_tools__inventory_status=(
                    Tool.InventoryStatus.SCRAPPED
                )
            ),
            distinct=True,
        ),
    
    ).annotate(
        disponibles_actuales=Case(
            When(
                tracking_mode=Article.TrackingMode.QUANTITY,
                then=Coalesce(
                    F("quantity_stock__available_quantity"),
                    Value(0),
                ),
            ),
            default=F("unidades_disponibles"),
            output_field=IntegerField(),
        )
    ).order_by("article_code", "pk")

    if solo_bajos:
        articulos = articulos.filter(
            is_active=True,
            minimum_stock__gt=0,
            disponibles_actuales__lt=F("minimum_stock"),
        )


    paginador = Paginator(articulos, 25)
    pagina = paginador.get_page(request.GET.get("page"))

    registros = []

    for articulo in pagina.object_list:
        if articulo.tracking_mode == Article.TrackingMode.QUANTITY:
            stock = getattr(articulo, "quantity_stock", None)

            if stock:
                disponibles = stock.available_quantity
                prestadas = stock.loaned_quantity
                revision = stock.quarantine_quantity
                bajas = stock.scrapped_quantity
            else:
                disponibles = "—"
                prestadas = "—"
                revision = "—"
                bajas = "—"
        else:
            disponibles = articulo.unidades_disponibles
            prestadas = articulo.unidades_prestadas
            revision = articulo.unidades_revision
            bajas = articulo.unidades_bajas

        registros.append({
            "articulo": articulo,
            "disponibles": disponibles,
            "prestadas": prestadas,
            "revision": revision,
            "bajas": bajas,
            "minimo": articulo.minimum_stock,
            "bajo_minimo": (
                articulo.is_active
                and articulo.minimum_stock > 0
                and articulo.disponibles_actuales
                < articulo.minimum_stock
            ),
        })

    return render(
        request,
        "stockroom/consultar_existencias_almacen.html",
        {
            "registros": registros,
            "pagina": pagina,
            "total_articulos": paginador.count,
            "busqueda": busqueda,
            "categoria": categoria,
            "control": control,
            "categorias": ToolCategory.objects.order_by("name"),
            "solo_bajos": solo_bajos,
        },
    )


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def reabastecimiento_almacen(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perms([
            "stockroom.view_article",
            "stockroom.view_quantitystock",
            "stockroom.view_tool",
        ])
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar reabastecimiento."
        )

    busqueda = request.GET.get("q", "").strip()[:100]

    articulos = Article.objects.filter(
        is_active=True,
        minimum_stock__gt=0,
    )

    if busqueda:
        for termino in busqueda.split():
            articulos = articulos.filter(
                Q(article_code__icontains=termino)
                | Q(name__icontains=termino)
                | Q(brand__icontains=termino)
                | Q(
                    pk__in=Tool.objects.filter(
                        tool_code__icontains=termino
                    ).values("article_id")
                )
            )

    # Conteos de herramientas individuales
    articulos = articulos.annotate(
        disponibles_individuales=Count(
            "individual_tools",
            filter=Q(
                individual_tools__inventory_status=(
                    Tool.InventoryStatus.AVAILABLE
                ),
                individual_tools__is_active=True,
            ),
            distinct=True,
        ),
        prestadas_individuales=Count(
            "individual_tools",
            filter=Q(
                individual_tools__inventory_status=(
                    Tool.InventoryStatus.LOANED
                )
            ),
            distinct=True,
        ),
    )

    # Unificar artículos por cantidad e individuales
    articulos = articulos.annotate(
        disponibles_actuales=Case(
            When(
                tracking_mode=Article.TrackingMode.QUANTITY,
                then=Coalesce(
                    F("quantity_stock__available_quantity"),
                    Value(0),
                ),
            ),
            default=F("disponibles_individuales"),
            output_field=IntegerField(),
        ),
        prestadas_actuales=Case(
            When(
                tracking_mode=Article.TrackingMode.QUANTITY,
                then=Coalesce(
                    F("quantity_stock__loaned_quantity"),
                    Value(0),
                ),
            ),
            default=F("prestadas_individuales"),
            output_field=IntegerField(),
        ),
    )

    # Faltante para alcanzar la disponibilidad mínima
    articulos = articulos.annotate(
        faltante=F("minimum_stock") - F("disponibles_actuales")
    ).filter(
        faltante__gt=0
    )

    # Compra estimada:
    # Descontamos piezas prestadas solo si requieren devolución.
    # No descontamos piezas dañadas/en revisión.
    articulos = articulos.annotate(
        compra_estimada=Greatest(
            Value(0),
            F("faltante") - Case(
                When(
                    return_mode=Article.ReturnMode.RETURNABLE,
                    then=F("prestadas_actuales"),
                ),
                default=Value(0),
                output_field=IntegerField(),
            ),
            output_field=IntegerField(),
        )
    ).order_by("-faltante", "article_code")

    resumen = articulos.aggregate(
        total_faltante=Coalesce(
            Sum("faltante"), Value(0)
        ),
        total_compra=Coalesce(
            Sum("compra_estimada"), Value(0)
        ),
    )

    paginador = Paginator(articulos, 25)
    pagina = paginador.get_page(request.GET.get("page"))

    return render(
        request,
        "stockroom/reabastecimiento_almacen.html",
        {
            "articulos": pagina.object_list,
            "pagina": pagina,
            "busqueda": busqueda,
            "total_articulos": paginador.count,
            "total_faltante": resumen["total_faltante"],
            "total_compra": resumen["total_compra"],
        },
    )
