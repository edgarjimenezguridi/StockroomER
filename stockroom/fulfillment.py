from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from django.db.models import F
from .loan_rules import validar_articulo_solicitable

from .models import (
    Article,
    MaterialRequest,
    MaterialRequestLine,
    MaterialRequestPiece,
    EmployeeCredential,
    QuantityIssue,
    QuantityStock,
)
from .selectors import catalogo_articulos, piezas_individuales_disponibles
from .credentials import verify_employee_pin
from .services import register_quantity_issue

def prepare_request_line(
    *,
    line_id,
    quantity,
    operator,
    tool_ids=None,
):
    if not (
        operator.is_active
        and operator.is_staff
        and operator.has_perm("stockroom.change_materialrequest")
    ):
        raise PermissionDenied(
            "No tienes permiso para preparar solicitudes."
        )

    if type(quantity) is not int or quantity < 0:
        raise ValidationError(
            "La cantidad preparada debe ser un entero igual o mayor que cero."
        )

    selected_ids = list(tool_ids or [])

    if any(type(tool_id) is not int for tool_id in selected_ids):
        raise ValidationError("La selección de piezas no es válida.")

    if len(selected_ids) != len(set(selected_ids)):
        raise ValidationError("No puedes seleccionar la misma pieza dos veces.")

    with transaction.atomic():
        updated = MaterialRequest.objects.filter(
            lines__pk=line_id,
            status=MaterialRequest.Status.SUBMITTED,
            employee__is_active=True,
        ).update(updated_at=timezone.now())

        if updated != 1:
            raise ValidationError(
                "La solicitud no está disponible para preparación."
            )

        line = MaterialRequestLine.objects.select_related(
            "article"
        ).get(pk=line_id)

        if quantity > line.requested_quantity:
            raise ValidationError(
                "No puedes preparar más piezas de las solicitadas."
            )

        if quantity == 0:
            if selected_ids:
                raise ValidationError(
                    "Si no entregarás piezas, deja vacía la selección."
                )
        else:
            article = catalogo_articulos().filter(
                pk=line.article_id,
            ).first()

            if article is None:
                raise ValidationError("El artículo está inactivo.")

            if quantity > article.available_quantity:
                raise ValidationError(
                    f"Actualmente hay {article.available_quantity} "
                    "piezas disponibles."
                )

            if article.tracking_mode == Article.TrackingMode.INDIVIDUAL:
                if len(selected_ids) != quantity:
                    raise ValidationError(
                        "Selecciona una pieza individual por cada unidad preparada."
                    )

                available_count = piezas_individuales_disponibles().filter(
                    article_id=article.pk,
                    pk__in=selected_ids,
                ).count()

                if available_count != quantity:
                    raise ValidationError(
                        "Alguna pieza no está disponible o pertenece a otro artículo."
                    )
            elif selected_ids:
                raise ValidationError(
                    "Los artículos por cantidad no requieren seleccionar piezas."
                )

        line.selected_pieces.all().delete()

        MaterialRequestPiece.objects.bulk_create([
            MaterialRequestPiece(line=line, tool_id=tool_id)
            for tool_id in selected_ids
        ])

        line.prepared_quantity = quantity
        line.save(update_fields=["prepared_quantity"])

    return line

def finish_request_preparation(*, request_id, operator):
    if not (
        operator.is_active
        and operator.is_staff
        and operator.has_perm("stockroom.change_materialrequest")
    ):
        raise PermissionDenied(
            "No tienes permiso para preparar solicitudes."
        )

    with transaction.atomic():
        now = timezone.now()

        updated = MaterialRequest.objects.filter(
            pk=request_id,
            status=MaterialRequest.Status.SUBMITTED,
            employee__is_active=True,
        ).update(
            status=MaterialRequest.Status.PREPARED,
            prepared_by=operator,
            prepared_at=now,
            preparation_version=F("preparation_version") + 1,
            updated_at=now,
        )

        if updated != 1:
            raise ValidationError(
                "La solicitud ya fue preparada o no está disponible."
            )

        lines = list(
            MaterialRequestLine.objects.filter(
                request_id=request_id,
            ).select_related("article").prefetch_related(
                "selected_pieces"
            )
        )

        if not any(line.prepared_quantity > 0 for line in lines):
            raise ValidationError(
                "Prepara al menos una pieza antes de continuar."
            )

        for line in lines:
            quantity = line.prepared_quantity
            selections = list(line.selected_pieces.all())

            if quantity > line.requested_quantity:
                raise ValidationError(
                    "Hay una cantidad preparada mayor que la solicitada."
                )

            if quantity == 0:
                if selections:
                    raise ValidationError(
                        "Un artículo sin cantidad preparada tiene piezas seleccionadas."
                    )
                continue

            article = catalogo_articulos().filter(
                pk=line.article_id,
            ).first()

            if article is None:
                raise ValidationError(
                    f"El artículo {line.article.article_code} está inactivo."
                )

            if quantity > article.available_quantity:
                raise ValidationError(
                    f"No hay suficientes piezas disponibles de "
                    f"{article.article_code}. Revisa la preparación."
                )

            if article.tracking_mode == Article.TrackingMode.INDIVIDUAL:
                tool_ids = [selection.tool_id for selection in selections]

                if len(tool_ids) != quantity:
                    raise ValidationError(
                        f"Revisa las piezas seleccionadas de {article.article_code}."
                    )

                available_count = piezas_individuales_disponibles().filter(
                    article_id=article.pk,
                    pk__in=tool_ids,
                ).count()

                if available_count != quantity:
                    raise ValidationError(
                        f"Alguna pieza de {article.article_code} "
                        "ya no está disponible."
                    )
            elif selections:
                raise ValidationError(
                    "Un artículo por cantidad tiene piezas individuales seleccionadas."
                )

        return MaterialRequest.objects.get(pk=request_id)

def confirm_request_receipt(
    *,
    request_id,
    employee_id,
    credential_id,
    pin,
    expected_version,
):
    credential = EmployeeCredential.objects.filter(
        pk=credential_id,
        employee_id=employee_id,
        is_active=True,
        employee__is_active=True,
    ).first()

    if credential is None:
        raise ValidationError("La credencial no está disponible.")

    if not MaterialRequest.objects.filter(
        pk=request_id,
        employee_id=employee_id,
        status=MaterialRequest.Status.PREPARED,
        preparation_version=expected_version,
    ).exists():
        raise ValidationError(
            "La solicitud cambió o ya no está pendiente. "
            "Vuelve al panel y revisa las cantidades actuales."
        )

    # Fuera de la transacción de inventario:
    # los intentos fallidos de NIP deben permanecer registrados.
    employee = verify_employee_pin(
        barcode=credential.barcode,
        pin=pin,
    )

    with transaction.atomic():
        now = timezone.now()

        updated = MaterialRequest.objects.filter(
            pk=request_id,
            employee_id=employee.pk,
            employee__is_active=True,
            status=MaterialRequest.Status.PREPARED,
            preparation_version=expected_version,
        ).update(
            status=MaterialRequest.Status.CLOSED,
            closed_at=now,
            updated_at=now,
        )

        if updated != 1:
            raise ValidationError(
                "La solicitud cambió o ya no está pendiente. "
                "Vuelve al panel y revisa las cantidades actuales."
            )

        if QuantityIssue.objects.filter(
            request_line__request_id=request_id,
        ).exists():
            raise ValidationError(
                "Esta solicitud ya tiene entregas registradas. "
                "Solicita al almacenista revisar el historial."
            )

        lines = list(
            MaterialRequestLine.objects.filter(
                request_id=request_id,
            ).select_related("article").prefetch_related(
                "selected_pieces__tool"
            )
        )
        # Ultima validacion antes de registrar
        # las entregas y descontar inventario.
        for line in lines:
            if line.prepared_quantity > 0:
                validar_articulo_solicitable(
                    employee_id=employee.pk,
                    article_id=line.article_id,
                    exclude_request_id=request_id,
                    quantity=line.prepared_quantity,
                    require_bound=True,
                )

        if not any(line.prepared_quantity > 0 for line in lines):
            raise ValidationError("La solicitud no tiene piezas preparadas.")

        for line in lines:
            quantity = line.prepared_quantity
            selections = list(line.selected_pieces.all())

            if quantity > line.requested_quantity:
                raise ValidationError(
                    "Hay una cantidad preparada mayor que la solicitada."
                )

            if quantity == 0:
                if selections:
                    raise ValidationError(
                        "Hay piezas seleccionadas en un artículo no surtido."
                    )
                continue

            article = line.article

            if article.tracking_mode == Article.TrackingMode.INDIVIDUAL:
                if len(selections) != quantity:
                    raise ValidationError(
                        f"Revisa las piezas preparadas de {article.article_code}."
                    )

                for selection in selections:
                    if selection.tool.article_id != article.pk:
                        raise ValidationError(
                            "Una pieza preparada pertenece a otro artículo."
                        )

                    register_quantity_issue(
                        QuantityIssue(
                            employee_id=employee.pk,
                            tool_id=selection.tool_id,
                            quantity=1,
                            issued_at=now,
                            request_line=line,
                        )
                    )
            else:
                if selections:
                    raise ValidationError(
                        "Un artículo por cantidad tiene piezas individuales."
                    )

                stock = QuantityStock.objects.filter(
                    article_id=article.pk,
                ).first()

                if stock is None:
                    raise ValidationError(
                        f"{article.article_code} no tiene registro de existencias."
                    )

                register_quantity_issue(
                    QuantityIssue(
                        employee_id=employee.pk,
                        stock=stock,
                        quantity=quantity,
                        issued_at=now,
                        request_line=line,
                    )
                )

        return MaterialRequest.objects.get(pk=request_id)

def reopen_request_preparation(*, request_id, operator):
    if not (
        operator.is_active
        and operator.is_staff
        and operator.has_perm("stockroom.change_materialrequest")
    ):
        raise PermissionDenied(
            "No tienes permiso para corregir preparaciones."
        )

    with transaction.atomic():
        updated = MaterialRequest.objects.filter(
            pk=request_id,
            status=MaterialRequest.Status.PREPARED,
            closed_at__isnull=True,
        ).update(
            status=MaterialRequest.Status.SUBMITTED,
            preparation_version=F("preparation_version") + 1,
            prepared_by=None,
            prepared_at=None,
            updated_at=timezone.now(),
        )

        if updated != 1:
            raise ValidationError(
                "Solo puedes reabrir una preparación pendiente "
                "de confirmar recibido."
            )

        if QuantityIssue.objects.filter(
            request_line__request_id=request_id,
        ).exists():
            raise ValidationError(
                "Esta solicitud ya tiene entregas registradas. "
                "No se puede reabrir."
            )

        return MaterialRequest.objects.get(pk=request_id)