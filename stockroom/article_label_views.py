"""Etiquetas de artículos por cantidad; no registran movimientos."""
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .label_barcodes import imagen_codigo_128
from .models import Article


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def imprimir_etiqueta_articulo_almacen(request, article_id):
    """Imprime un código por artículo, no por unidad física."""
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perms([
            "stockroom.view_article",
            "stockroom.view_quantitystock",
            "stockroom.view_tool",
        ])
    ):
        raise PermissionDenied("No tienes permiso para imprimir etiquetas de artículos.")

    articulo = get_object_or_404(
        Article,
        pk=article_id,
        tracking_mode=Article.TrackingMode.QUANTITY,
    )
    codigo = articulo.article_code
    return render(
        request,
        "stockroom/almacen/etiqueta_articulo_cantidad.html",
        {
            "articulo": articulo,
            "codigo": codigo,
            "imagen_codigo": imagen_codigo_128(codigo),
        },
    )
