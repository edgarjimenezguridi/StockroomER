
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
)

from .individual_tool_forms import EditIndividualToolForm
from .models import Loan, Tool


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

    if estado not in ("", "disponible", "prestada", "inactiva"):
        estado = ""

    prestamos_abiertos = Loan.objects.filter(
        tool_id=OuterRef("pk"),
        returned_at__isnull=True,
    )

    piezas = (
        Tool.objects.select_related(
            "article",
            "specification",
        )
        .annotate(
            tiene_prestamo=Exists(prestamos_abiertos)
        )
    )

    # Buscar piezas por sus datos o los del artículo
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

    # Filtrar según su situación actual
    if estado == "disponible":
        piezas = piezas.filter(
            is_active=True,
            tiene_prestamo=False,
        )

    elif estado == "prestada":
        piezas = piezas.filter(
            tiene_prestamo=True,
        )

    elif estado == "inactiva":
        piezas = piezas.filter(
            is_active=False,
        )

    piezas = piezas.order_by("tool_code", "pk")

    paginador = Paginator(piezas, 25)
    pagina = paginador.get_page(
        request.GET.get("page")
    )

    piezas_pagina = list(pagina.object_list)

    # Consultar los préstamos abiertos de las piezas visibles,
    # evitando realizar una consulta por cada herramienta.
    ids_piezas = [
        pieza.pk for pieza in piezas_pagina
    ]

    prestamos = (
        Loan.objects.filter(
            tool_id__in=ids_piezas,
            returned_at__isnull=True,
        )
        .select_related("employee")
        .order_by("-borrowed_at", "-pk")
    )

    prestamos_por_pieza = {}

    for prestamo in prestamos:
        if prestamo.tool_id not in prestamos_por_pieza:
            prestamos_por_pieza[prestamo.tool_id] = prestamo

    for pieza in piezas_pagina:
        pieza.prestamo_abierto = prestamos_por_pieza.get(
            pieza.pk
        )

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

    prestamo_abierto = (
        Loan.objects.filter(
            tool=pieza,
            returned_at__isnull=True,
        )
        .select_related("employee")
        .order_by("-borrowed_at", "-pk")
        .first()
    )

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
        },
    )
