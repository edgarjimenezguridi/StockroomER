from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from .models import (
    Article,
    Employee,
    QuantityStock,
    QuantityIssue,
    QuantityReturn,
)


def register_stock_entry(entry):
    if entry.pk is not None or not entry._state.adding:
        raise ValidationError(
            "Solo se pueden registrar entradas nuevas."
        )

    with transaction.atomic():
        entry.full_clean()

        updated = QuantityStock.objects.filter(
            pk=entry.stock_id,
            article__is_active=True,
            article__tracking_mode=Article.TrackingMode.QUANTITY,
        ).update(
            available_quantity=F("available_quantity") + entry.quantity
        )

        if updated != 1:
            raise ValidationError(
                "La entrada requiere un artículo activo "
                "con control por cantidad y un registro de existencias."
            )

        entry.save(force_insert=True)

    return entry

def register_quantity_issue(issue):
    if issue.pk is not None or not issue._state.adding:
        raise ValidationError(
            "Solo se pueden registrar entregas nuevas."
        )

    with transaction.atomic():
        issue.full_clean()

        if not Employee.objects.filter(
            pk=issue.employee_id,
            is_active=True,
        ).exists():
            raise ValidationError(
                "El trabajador debe estar activo para recibir herramientas."
            )

        article = Article.objects.get(
            quantity_stock__pk=issue.stock_id
        )

        issue.requires_return = (
            article.return_mode == Article.ReturnMode.RETURNABLE
        )

        changes = {
            "available_quantity": F("available_quantity") - issue.quantity,
        }

        if issue.requires_return:
            changes["loaned_quantity"] = (
                F("loaned_quantity") + issue.quantity
            )

        updated = QuantityStock.objects.filter(
            pk=issue.stock_id,
            article__is_active=True,
            article__tracking_mode=Article.TrackingMode.QUANTITY,
            article__return_mode=article.return_mode,
            available_quantity__gte=issue.quantity,
        ).update(**changes)

        if updated != 1:
            raise ValidationError(
                "No se pudo registrar la entrega. Verifica que haya "
                "suficientes piezas disponibles y que el artículo esté "
                "activo, con control por cantidad y la misma modalidad "
                "de devolución. Recarga el formulario e intenta de nuevo."
            )

        issue.save(force_insert=True)

    return issue

def register_quantity_return(return_record):
    if return_record.pk is not None or not return_record._state.adding:
        raise ValidationError(
            "Solo se pueden registrar devoluciones nuevas."
        )

    with transaction.atomic():
        return_record.full_clean()

        issue = QuantityIssue.objects.get(pk=return_record.issue_id)

        if return_record.returned_at < issue.issued_at:
            raise ValidationError(
                "La devolución no puede tener una fecha anterior a la entrega."
            )

        updated_issue = QuantityIssue.objects.filter(
            pk=issue.pk,
            requires_return=True,
            returned_quantity__lte=(
                F("quantity") - return_record.quantity
            ),
        ).update(
            returned_quantity=(
                F("returned_quantity") + return_record.quantity
            )
        )

        if updated_issue != 1:
            raise ValidationError(
                "La entrega no requiere devolución o la cantidad "
                "que intentas devolver supera las piezas pendientes."
            )

        changes = {
            "loaned_quantity": (
                F("loaned_quantity") - return_record.quantity
            ),
        }

        if return_record.condition == QuantityReturn.Condition.GOOD:
            changes["available_quantity"] = (
                F("available_quantity") + return_record.quantity
            )
        else:
            changes["quarantine_quantity"] = (
                F("quarantine_quantity") + return_record.quantity
            )

        updated_stock = QuantityStock.objects.filter(
            pk=issue.stock_id,
            loaned_quantity__gte=return_record.quantity,
        ).update(**changes)

        if updated_stock != 1:
            raise ValidationError(
                "Las existencias prestadas no coinciden con la devolución. "
                "Revisa los movimientos antes de continuar."
            )

        return_record.save(force_insert=True)

    return return_record