
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .classification_forms import (
    CategoryForm,
    ToolTypeForm,
    SpecificationForm,
)

from .models import (
    ToolCategory,
    ToolType,
    ToolSpecification,
)


@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def administrar_clasificaciones_almacen(request):

    permisos = {
        "categoria": "stockroom.add_toolcategory",
        "tipo": "stockroom.add_tooltype",
        "especificacion": "stockroom.add_toolspecification",
    }

    if not (
        request.user.is_active
        and request.user.is_staff
    ):
        raise PermissionDenied(
            "No tienes permiso para administrar clasificaciones."
        )

    permisos_disponibles = {
        accion: request.user.has_perm(permiso)
        for accion, permiso in permisos.items()
    }

    if not any(permisos_disponibles.values()):
        raise PermissionDenied(
            "No tienes permiso para agregar clasificaciones."
        )

    accion = (
        request.POST.get("accion", "")
        if request.method == "POST"
        else ""
    )

    if request.method == "POST":
        if accion not in permisos:
            raise PermissionDenied(
                "La operación solicitada no está permitida."
            )

        if not permisos_disponibles[accion]:
            raise PermissionDenied(
                "No tienes permiso para realizar esta operación."
            )

    formulario_categoria = CategoryForm(
        request.POST
        if request.method == "POST" and accion == "categoria"
        else None,
        prefix="categoria",
    )

    formulario_tipo = ToolTypeForm(
        request.POST
        if request.method == "POST" and accion == "tipo"
        else None,
        prefix="tipo",
    )

    formulario_especificacion = SpecificationForm(
        request.POST
        if request.method == "POST" and accion == "especificacion"
        else None,
        prefix="especificacion",
    )

    formularios = {
        "categoria": formulario_categoria,
        "tipo": formulario_tipo,
        "especificacion": formulario_especificacion,
    }

    if request.method == "POST":
        formulario = formularios[accion]

        if formulario.is_valid():
            try:
                with transaction.atomic():
                    registro = formulario.save()

            except IntegrityError:
                formulario.add_error(
                    None,
                    "No se pudo guardar el registro. "
                    "Es posible que ya exista una clasificación "
                    "con estos datos.",
                )

            else:
                mensajes = {
                    "categoria": "Categoría registrada correctamente.",
                    "tipo": "Tipo registrado correctamente.",
                    "especificacion": (
                        "Especificación registrada correctamente."
                    ),
                }

                messages.success(
                    request,
                    mensajes[accion],
                )

                return redirect(
                    "administrar_clasificaciones_almacen"
                )

    categorias = ToolCategory.objects.order_by("name")

    tipos = ToolType.objects.select_related(
        "category"
    ).order_by(
        "category__name",
        "name",
    )

    especificaciones = ToolSpecification.objects.select_related(
        "tool_type",
        "tool_type__category",
    ).order_by(
        "tool_type__category__name",
        "tool_type__name",
        "name",
    )

    return render(
        request,
        "stockroom/almacen/administrar_clasificaciones_almacen.html",
        {
            "formulario_categoria": formulario_categoria,
            "formulario_tipo": formulario_tipo,
            "formulario_especificacion": formulario_especificacion,
            "categorias": categorias,
            "tipos": tipos,
            "especificaciones": especificaciones,
            "puede_agregar_categoria": (
                permisos_disponibles["categoria"]
            ),
            "puede_agregar_tipo": (
                permisos_disponibles["tipo"]
            ),
            "puede_agregar_especificacion": (
                permisos_disponibles["especificacion"]
            ),
        },
    )
