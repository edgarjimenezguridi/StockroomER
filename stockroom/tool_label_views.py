
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .models import Tool
from .label_barcodes import imagen_codigo_128


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def imprimir_etiqueta_pieza_almacen(request, tool_id):
    """
    Genera una etiqueta imprimible para una herramienta
    individual usando su codigo unico real.

    La consulta no modifica el inventario.
    """

    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.view_tool")
    ):
        raise PermissionDenied(
            "No tienes permiso para imprimir etiquetas."
        )

    pieza = get_object_or_404(
        Tool.objects.select_related("article"),
        pk=tool_id,
    )

    codigo = pieza.tool_code

    imagen_codigo = imagen_codigo_128(codigo)

    return render(
        request,
        "stockroom/almacen/etiqueta_pieza_individual.html",
        {
            "pieza": pieza,
            "codigo": codigo,
            "imagen_codigo": imagen_codigo,
        },
    )
