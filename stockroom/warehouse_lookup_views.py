"""Búsquedas del almacén: consultas JSON de solo lectura y permisos por operación."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import Article, Employee, QuantityStock, StockEntry, Tool


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def buscar_almacen(request):
    """Máximo 20 coincidencias por consulta, sin realizar movimientos."""
    tipo = request.GET.get("tipo", "").strip()
    termino = request.GET.get("q", "").strip()[:80]
    requisitos = {
        "articulos_entrada": ("stockroom.add_stockentry",),
        "entradas_correccion": ("stockroom.add_stockentrycorrection",),
        "trabajadores_stock": ("stockroom.add_quantityissue", "stockroom.view_employee", "stockroom.view_materialrequest"),
        "articulos_stock": ("stockroom.add_quantityissue", "stockroom.view_employee", "stockroom.view_materialrequest"),
        "piezas_stock": ("stockroom.add_quantityissue", "stockroom.view_employee", "stockroom.view_materialrequest"),
    }
    if tipo not in requisitos:
        return JsonResponse({"error": "Tipo de búsqueda no válido."}, status=400)
    usuario = request.user
    if not (usuario.is_active and usuario.is_staff and all(usuario.has_perm(p) for p in requisitos[tipo])):
        raise PermissionDenied("No tienes permisos para consultar esta operación de almacén.")
    if not termino:
        return JsonResponse({"results": []})

    if tipo == "articulos_entrada":
        registros = QuantityStock.objects.filter(
            article__is_active=True, article__tracking_mode=Article.TrackingMode.QUANTITY,
        ).filter(Q(article__article_code__icontains=termino) | Q(article__name__icontains=termino))            .select_related("article").order_by("article__article_code", "pk")[:20]
        resultados = [{"id": obj.pk, "text": f"{obj.article.article_code} — {obj.article.name}"} for obj in registros]
    elif tipo == "entradas_correccion":
        registros = StockEntry.objects.filter(
            stock__article__is_active=True,
            stock__article__tracking_mode=Article.TrackingMode.QUANTITY,
        ).filter(Q(stock__article__article_code__icontains=termino) |
                 Q(stock__article__name__icontains=termino) |
                 Q(reference__icontains=termino))            .select_related("stock__article").order_by("-received_at", "-pk")[:20]
        resultados = [{"id": obj.pk, "text": (
            f"{obj.stock.article.article_code} — {obj.stock.article.name} "
            f"(entrada #{obj.pk}, cantidad original: {obj.quantity})"
        )} for obj in registros]
    elif tipo == "trabajadores_stock":
        registros = Employee.objects.filter(is_active=True).filter(
            Q(employee_id__icontains=termino) | Q(first_name__icontains=termino) |
            Q(last_name__icontains=termino)
        ).order_by("employee_id", "pk")[:20]
        resultados = [{"id": obj.pk, "text": str(obj)} for obj in registros]
    elif tipo == "articulos_stock":
        registros = Article.objects.filter(is_active=True, return_mode=Article.ReturnMode.RETURNABLE).filter(
            Q(article_code__icontains=termino) | Q(name__icontains=termino)
        ).order_by("article_code", "pk")[:20]
        resultados = [{"id": obj.pk, "text": f"{obj.article_code} — {obj.name}"} for obj in registros]
    else:
        registros = Tool.objects.filter(
            is_active=True, inventory_status=Tool.InventoryStatus.AVAILABLE,
        ).filter(Q(tool_code__icontains=termino) |
                 Q(article__article_code__icontains=termino) |
                 Q(article__name__icontains=termino))            .select_related("article").order_by("tool_code", "pk")[:20]
        resultados = [{"id": obj.pk, "text": f"{obj.tool_code} — {obj.article.name}"} for obj in registros]
    return JsonResponse({"results": resultados})
