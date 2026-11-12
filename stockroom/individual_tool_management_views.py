
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
)

from .individual_tool_forms import EditIndividualToolForm
from .models import Loan, QuantityIssue, Tool


ESTADOS_VALIDOS = (
    "",
    "disponible",
    "prestada",
    "revision",
    "consumida",
    "baja",
    "inactiva",
)


def obtener_estado_pieza(pieza):
    """
    Determina el estado que se mostrara al almacenista.

    Las obligaciones de devolucion abiertas tienen prioridad
    sobre un estado 'available' desactualizado.
    """

    if not pieza.is_active:
        return "inactiva", "Inactiva"

    if pieza.tiene_prestamo_legacy or pieza.tiene_entrega_abierta:
        return "prestada", "Prestada"

    estados = {
        Tool.InventoryStatus.AVAILABLE: (
            "disponible",
            "Disponible",
        ),
        Tool.InventoryStatus.LOANED: (
            "prestada",
            "Prestada",
        ),
        Tool.InventoryStatus.QUARANTINE: (
            "revision",
            "En revisión",
        ),
        Tool.InventoryStatus.CONSUMED: (
            "consumida",
            "Entregada sin devolución",
        ),
        Tool.InventoryStatus.SCRAPPED: (
            "baja",
            "Baja definitiva",
        ),
    }

    return estados.get(
        pieza.inventory_status,
        ("desconocido", "Estado desconocido"),
    )


def consultar_prestamos_de_piezas(piezas):
    """
    Consulta los movimientos pendientes de todas las piezas
    visibles sin realizar una consulta por cada herramienta.
    """

    ids = [pieza.pk for pieza in piezas]

    prestamos = (
        Loan.objects.filter(
            tool_id__in=ids,
            returned_at__isnull=True,
        )
        .select_related("employee")
        .order_by("-borrowed_at", "-pk")
    )

    entregas = (
        QuantityIssue.objects.filter(
            tool_id__in=ids,
            requires_return=True,
            returned_quantity__lt=F("quantity"),
        )
        .select_related("employee")
        .order_by("-issued_at", "-pk")
    )

    prestamos_por_pieza = {}

    for prestamo in prestamos:
        prestamos_por_pieza.setdefault(
            prestamo.tool_id,
            prestamo,
        )

    entregas_por_pieza = {}

    for entrega in entregas:
        entregas_por_pieza.setdefault(
            entrega.tool_id,
            entrega,
        )

    for pieza in piezas:
        pieza.prestamo_abierto = prestamos_por_pieza.get(
            pieza.pk
        )

        pieza.entrega_abierta = entregas_por_pieza.get(
            pieza.pk
        )

        pieza.estado_clave, pieza.estado_texto = (
            obtener_estado_pieza(pieza)
        )

        # Priorizar la entrega del sistema unificado.
        if pieza.entrega_abierta:
            pieza.trabajador_responsable = (
                pieza.entrega_abierta.employee
            )
            pieza.fecha_prestamo = (
                pieza.entrega_abierta.issued_at
            )

        elif pieza.prestamo_abierto:
            pieza.trabajador_responsable = (
                pieza.prestamo_abierto.employee
            )
            pieza.fecha_prestamo = (
                pieza.prestamo_abierto.borrowed_at
            )

        else:
            pieza.trabajador_responsable = None
            pieza.fecha_prestamo = None


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def consultar_piezas_individuales_almacen(request):

    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.view_tool")
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar las piezas individuales."
        )

    busqueda = request.GET.get("q", "").strip()[:100]
    estado = request.GET.get("estado", "").strip()

    if estado not in ESTADOS_VALIDOS:
        estado = ""

    prestamos_abiertos = Loan.objects.filter(
        tool_id=OuterRef("pk"),
        returned_at__isnull=True,
    )

    entregas_abiertas = QuantityIssue.objects.filter(
        tool_id=OuterRef("pk"),
        requires_return=True,
        returned_quantity__lt=F("quantity"),
    )

    piezas = (
        Tool.objects.select_related(
            "article",
            "specification",
        )
        .annotate(
            tiene_prestamo_legacy=Exists(prestamos_abiertos),
            tiene_entrega_abierta=Exists(entregas_abiertas),
        )
    )

    # Búsqueda por datos de la pieza o del artículo.
    if busqueda:
        for termino in busqueda.split():
            piezas = piezas.filter(
                Q(tool_code__icontains=termino)
                | Q(name__icontains=termino)
                | Q(serial_number__icontains=termino)
                | Q(brand__icontains=termino)
                | Q(location__icontains=termino)
                | Q(article__article_code__icontains=termino)
                | Q(article__name__icontains=termino)
            )

    # Una pieza con una entrega pendiente nunca
    # se considera disponible.
    tiene_adeudo = (
        Q(tiene_prestamo_legacy=True)
        | Q(tiene_entrega_abierta=True)
    )

    sin_adeudo = (
        Q(tiene_prestamo_legacy=False)
        & Q(tiene_entrega_abierta=False)
    )

    if estado == "disponible":
        piezas = piezas.filter(
            is_active=True,
            inventory_status=Tool.InventoryStatus.AVAILABLE,
        ).filter(sin_adeudo)

    elif estado == "prestada":
        piezas = piezas.filter(
            is_active=True,
        ).filter(
            tiene_adeudo
            | Q(
                inventory_status=Tool.InventoryStatus.LOANED
            )
        )

    elif estado == "revision":
        piezas = piezas.filter(
            is_active=True,
            inventory_status=Tool.InventoryStatus.QUARANTINE,
        ).filter(sin_adeudo)

    elif estado == "consumida":
        piezas = piezas.filter(
            is_active=True,
            inventory_status=Tool.InventoryStatus.CONSUMED,
        ).filter(sin_adeudo)

    elif estado == "baja":
        piezas = piezas.filter(
            is_active=True,
            inventory_status=Tool.InventoryStatus.SCRAPPED,
        ).filter(sin_adeudo)

    elif estado == "inactiva":
        piezas = piezas.filter(
            is_active=False,
        )

    piezas = piezas.order_by(
        "tool_code",
        "pk",
    )

    paginador = Paginator(piezas, 25)

    pagina = paginador.get_page(
        request.GET.get("page")
    )

    piezas_pagina = list(pagina.object_list)

    consultar_prestamos_de_piezas(piezas_pagina)

    return render(
        request,
        "stockroom/almacen/consultar_piezas_individuales_almacen.html",
        {
            "piezas": piezas_pagina,
            "pagina": pagina,
            "total_piezas": paginador.count,
            "busqueda": busqueda,
            "estado": estado,
            "puede_editar": request.user.has_perm(
                "stockroom.change_tool"
            ),
        },
    )


@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def editar_pieza_individual_almacen(request, tool_id):

    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.change_tool")
    ):
        raise PermissionDenied(
            "No tienes permiso para editar piezas individuales."
        )

    pieza = get_object_or_404(
        Tool.objects.select_related("article"),
        pk=tool_id,
    )

    prestamos_abiertos = Loan.objects.filter(
        tool_id=pieza.pk,
        returned_at__isnull=True,
    )

    entregas_abiertas = QuantityIssue.objects.filter(
        tool_id=pieza.pk,
        requires_return=True,
        returned_quantity__lt=F("quantity"),
    )

    pieza.tiene_prestamo_legacy = prestamos_abiertos.exists()
    pieza.tiene_entrega_abierta = entregas_abiertas.exists()

    prestamo_abierto = (
        prestamos_abiertos
        .select_related("employee")
        .order_by("-borrowed_at", "-pk")
        .first()
    )

    entrega_abierta = (
        entregas_abiertas
        .select_related("employee")
        .order_by("-issued_at", "-pk")
        .first()
    )

    estado_clave, estado_texto = obtener_estado_pieza(pieza)

    form = EditIndividualToolForm(
        request.POST if request.method == "POST" else None,
        instance=pieza,
    )

    if request.method == "POST" and form.is_valid():

        with transaction.atomic():
            form.save()

        messages.success(
            request,
            f"La pieza {pieza.tool_code} "
            "se actualizó correctamente.",
        )

        return redirect(
            "consultar_piezas_individuales_almacen"
        )

    return render(
        request,
        "stockroom/almacen/editar_pieza_individual_almacen.html",
        {
            "pieza": pieza,
            "form": form,
            "prestamo_abierto": prestamo_abierto,
            "entrega_abierta": entrega_abierta,
            "estado_clave": estado_clave,
            "estado_texto": estado_texto,
        },
    )
