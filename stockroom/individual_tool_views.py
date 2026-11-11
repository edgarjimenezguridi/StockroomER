
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.shortcuts import render, redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .individual_tool_forms import IndividualToolForm
from .models import Article, Tool


@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def registrar_pieza_individual_almacen(request):

    # Verificar permisos del almacenista
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.add_tool")
    ):
        raise PermissionDenied(
            "No tienes permiso para registrar piezas individuales."
        )

    form = IndividualToolForm(
        request.POST if request.method == "POST" else None
    )

    if request.method == "POST" and form.is_valid():

        article = form.cleaned_data["article"]

        # Comprobar que el artículo sigue siendo válido
        if not Article.objects.filter(
            pk=article.pk,
            is_active=True,
            tracking_mode=Article.TrackingMode.INDIVIDUAL,
        ).exists():
            form.add_error(
                "article",
                "El artículo ya no está disponible "
                "para registrar piezas individuales.",
            )

        else:
            pieza = Tool(
                article=article,
                tool_code=form.cleaned_data["tool_code"],
                name=article.name,
                specification=article.specification,
                brand=article.brand,
                serial_number=form.cleaned_data["serial_number"],
                location=form.cleaned_data["location"],
                is_active=True,
            )

            try:
                with transaction.atomic():
                    # Aplicar las validaciones del modelo
                    pieza.full_clean()

                    # Registrar la herramienta
                    pieza.save()

            except ValidationError as exc:
                if hasattr(exc, "message_dict"):
                    for campo, errores in exc.message_dict.items():
                        destino = campo if campo in form.fields else None

                        for error in errores:
                            form.add_error(destino, error)
                else:
                    form.add_error(None, exc)

            except IntegrityError:
                form.add_error(
                    "tool_code",
                    "No se pudo guardar la pieza. "
                    "Verifica que el código no esté registrado.",
                )

            else:
                messages.success(
                    request,
                    f"Pieza {pieza.tool_code} registrada "
                    f"correctamente para el artículo "
                    f"{article.article_code} — {article.name}.",
                )

                return redirect(
                    "registrar_pieza_individual_almacen"
                )

    return render(
        request,
        "stockroom/almacen/registrar_pieza_individual_almacen.html",
        {
            "form": form,
        },
    )
