"""Consultas operativas exclusivas de jefatura; nunca registran movimientos."""
from django.contrib.auth.decorators import login_required
from django.db.models import F
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .boss_personnel_views import jefe_obligatorio
from .models import MaterialRequest, QuantityIssue, QuantityStock


@never_cache
@login_required(login_url="acceso_jefe")
@require_GET
def consultas_operativas_jefe(request, seccion):
    jefe_obligatorio(request)
    titulos = {
        "adeudos": "Adeudos y devoluciones pendientes",
        "reabastecimiento": "Artículos que necesitan reabastecimiento",
        "solicitudes": "Solicitudes activas de material",
    }
    if seccion not in titulos:
        from django.http import Http404
        raise Http404("Consulta no disponible")

    registros = []
    total = 0
    if seccion == "adeudos":
        qs = (QuantityIssue.objects.filter(
            requires_return=True, returned_quantity__lt=F("quantity"),
        ).select_related("employee", "tool__article", "stock__article")
          .order_by("issued_at", "pk"))
        for entrega in qs:
            articulo = entrega.tool.article if entrega.tool_id else entrega.stock.article
            pendiente = entrega.quantity - entrega.returned_quantity
            registros.append({
                "trabajador": entrega.employee,
                "articulo": articulo,
                "pendiente": pendiente,
                "fecha": entrega.issued_at,
            })
            total += pendiente
    elif seccion == "reabastecimiento":
        qs = (QuantityStock.objects.filter(
            article__is_active=True, article__minimum_stock__gt=0,
            available_quantity__lt=F("article__minimum_stock"),
        ).select_related("article").order_by("article__article_code"))
        for stock in qs:
            registros.append({
                "articulo": stock.article,
                "disponibles": stock.available_quantity,
                "minimo": stock.article.minimum_stock,
                "faltantes": stock.article.minimum_stock - stock.available_quantity,
            })
        total = len(registros)
    else:
        qs = (MaterialRequest.objects.filter(status__in=[
            MaterialRequest.Status.SUBMITTED, MaterialRequest.Status.PREPARED,
        ]).select_related("employee").order_by("-submitted_at", "-pk"))
        registros = list(qs)
        total = len(registros)

    return render(request, "stockroom/jefe/consultas_operativas.html", {
        "seccion": seccion, "titulo_consulta": titulos[seccion],
        "registros": registros, "total": total,
    })
