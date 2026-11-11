
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.core.paginator import Paginator
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.views.decorators.cache import never_cache
from django.views.decorators.http import (
    require_GET,
    require_http_methods,
)

from .article_edit_forms import EditArticleForm
from .models import Article, ToolCategory


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def administrar_articulos_almacen(request):

    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.view_article")
    ):
        raise PermissionDenied(
            "No tienes permiso para consultar el catálogo."
        )

    busqueda = request.GET.get("q", "").strip()[:100]
    categoria = request.GET.get("categoria", "").strip()
    control = request.GET.get("control", "").strip()
    estado = request.GET.get("estado", "activos").strip()

    if estado not in ("activos", "inactivos", "todos"):
        estado = "activos"

    articulos = Article.objects.select_related(
        "specification__tool_type__category",
    )

    # Estado de los artículos
    if estado == "activos":
        articulos = articulos.filter(is_active=True)

    elif estado == "inactivos":
        articulos = articulos.filter(is_active=False)

    # Búsqueda por código, nombre, marca o especificación
    if busqueda:
        for termino in busqueda.split():
            articulos = articulos.filter(
                Q(article_code__icontains=termino)
                | Q(name__icontains=termino)
                | Q(brand__icontains=termino)
                | Q(location__icontains=termino)
                | Q(specification__name__icontains=termino)
                | Q(
                    specification__tool_type__name__icontains=termino
                )
                | Q(
                    specification__tool_type__category__name__icontains=termino
                )
            )

    # Filtro por categoría
    if categoria:
        if categoria.isdecimal():
            articulos = articulos.filter(
                specification__tool_type__category_id=int(categoria)
            )
        else:
            articulos = articulos.none()

    # Filtro por forma de control
    if control in Article.TrackingMode.values:
        articulos = articulos.filter(
            tracking_mode=control
        )

    articulos = articulos.order_by(
        "article_code",
        "pk",
    )

    paginador = Paginator(articulos, 25)
    pagina = paginador.get_page(
        request.GET.get("page")
    )

    return render(
        request,
        "stockroom/almacen/administrar_articulos_almacen.html",
        {
            "articulos": pagina.object_list,
            "pagina": pagina,
            "total_articulos": paginador.count,
            "categorias": ToolCategory.objects.order_by("name"),
            "busqueda": busqueda,
            "categoria": categoria,
            "control": control,
            "estado": estado,
            "puede_editar": request.user.has_perm(
                "stockroom.change_article"
            ),
        },
    )


@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def editar_articulo_almacen(request, article_id):

    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.change_article")
    ):
        raise PermissionDenied(
            "No tienes permiso para modificar artículos."
        )

    articulo = get_object_or_404(
        Article.objects.select_related(
            "specification__tool_type__category",
        ),
        pk=article_id,
    )

    form = EditArticleForm(
        request.POST if request.method == "POST" else None,
        instance=articulo,
    )

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            form.save()

        messages.success(
            request,
            f"Artículo {articulo.article_code} "
            "actualizado correctamente.",
        )

        return redirect(
            "administrar_articulos_almacen"
        )

    return render(
        request,
        "stockroom/almacen/editar_articulo_almacen.html",
        {
            "articulo": articulo,
            "form": form,
        },
    )
