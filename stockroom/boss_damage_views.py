
"""Consulta de daños pendientes exclusiva de jefatura."""

from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .boss_personnel_views import jefe_obligatorio
from .models import QuantityReturn


@never_cache
@login_required(login_url="acceso_jefe")
@require_GET
def danos_pendientes_jefe(request):
    jefe_obligatorio(request)

    devoluciones = (
        QuantityReturn.objects.filter(
            condition=QuantityReturn.Condition.DAMAGED,
            resolved_quantity__lt=F("quantity"),
        )
        .select_related(
            "issue__employee",
            "issue__stock__article",
            "issue__tool__article",
        )
        .order_by("-returned_at", "-pk")
    )

    registros = []

    for devolucion in devoluciones:
        issue = devolucion.issue

        articulo = (
            issue.tool.article
            if issue.tool_id
            else issue.stock.article
        )

        registros.append({
            "empleado": issue.employee,
            "articulo": articulo,
            "devueltas": devolucion.quantity,
            "resueltas": devolucion.resolved_quantity,
            "pendientes": (
                devolucion.quantity -
                devolucion.resolved_quantity
            ),
            "fecha": devolucion.returned_at,
        })

    total_pendientes = sum(
        registro["pendientes"]
        for registro in registros
    )

    return render(
        request,
        "stockroom/jefe/danos_pendientes.html",
        {
            "registros": registros,
            "total_pendientes": total_pendientes,
        },
    )
