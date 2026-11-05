from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from .models import (
    Article,
    Employee,
    Tool,
    Loan,
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
    if issue.tool_id:
        return register_individual_issue(issue)

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

        if issue.tool_id:
            new_status = (
                Tool.InventoryStatus.AVAILABLE
                if return_record.condition == QuantityReturn.Condition.GOOD
                else Tool.InventoryStatus.QUARANTINE
            )

            updated_tool = Tool.objects.filter(
                pk=issue.tool_id,
                inventory_status=Tool.InventoryStatus.LOANED,
            ).update(inventory_status=new_status)

            if updated_tool != 1:
                raise ValidationError(
                    "La pieza no figura como prestada. "
                    "Revisa su historial antes de registrar la devolución."
                )

            return_record.save(force_insert=True)
            return return_record

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

def register_individual_issue(issue):
    if issue.pk is not None or not issue._state.adding:
        raise ValidationError(
            "Solo se pueden registrar entregas nuevas."
        )

    with transaction.atomic():
        tool = Tool.objects.select_related("article").filter(
            pk=issue.tool_id,
        ).first()

        if tool is None or tool.article_id is None:
            raise ValidationError(
                "Selecciona una pieza vinculada a un artículo."
            )

        article = tool.article
        issue.requires_return = (
            article.return_mode == Article.ReturnMode.RETURNABLE
        )
        issue.full_clean()

        if issue.returned_quantity != 0:
            raise ValidationError(
                "Una entrega nueva no puede tener piezas ya devueltas."
            )

        if not Employee.objects.filter(
            pk=issue.employee_id,
            is_active=True,
        ).exists():
            raise ValidationError(
                "El trabajador debe estar activo."
            )

        if Loan.objects.filter(
            tool_id=tool.pk,
            returned_at__isnull=True,
            unified_issue__isnull=True,
        ).exists():
            raise ValidationError(
                "Esta pieza tiene un préstamo anterior pendiente."
            )

        new_status = (
            Tool.InventoryStatus.LOANED
            if issue.requires_return
            else Tool.InventoryStatus.CONSUMED
        )

        updated = Tool.objects.filter(
            pk=tool.pk,
            is_active=True,
            inventory_status=Tool.InventoryStatus.AVAILABLE,
            article_id=article.pk,
            article__is_active=True,
            article__tracking_mode=Article.TrackingMode.INDIVIDUAL,
            article__return_mode=article.return_mode,
        ).update(inventory_status=new_status)

        if updated != 1:
            raise ValidationError(
                "La pieza no está disponible o su artículo no está "
                "activo y configurado para control individual. "
                "Recarga el formulario y verifica sus datos."
            )

        issue.save(force_insert=True)

    return issue

def register_return_and_exchange(
    return_record,
    replacement_tool_id=None,
):
    with transaction.atomic():
        return_record.full_clean()

        if return_record.condition != QuantityReturn.Condition.DAMAGED:
            raise ValidationError(
                "El cambio requiere una devolución de piezas dañadas."
            )

        original_issue = QuantityIssue.objects.select_related(
            "stock__article",
            "tool__article",
        ).get(pk=return_record.issue_id)

        replacement = QuantityIssue(
            employee_id=original_issue.employee_id,
            quantity=return_record.quantity,
            issued_at=return_record.returned_at,
        )

        if original_issue.tool_id:
            original_tool = original_issue.tool

            if original_tool.article_id is None:
                raise ValidationError(
                    "La pieza original debe estar vinculada a un artículo."
                )

            replacement_tool = Tool.objects.filter(
                pk=replacement_tool_id,
                article_id=original_tool.article_id,
            ).first()

            if replacement_tool is None:
                raise ValidationError(
                    "Selecciona una pieza de reemplazo del mismo artículo."
                )

            if replacement_tool.pk == original_tool.pk:
                raise ValidationError(
                    "La pieza dañada no puede ser su propio reemplazo."
                )

            article = original_tool.article
            replacement.tool = replacement_tool

        else:
            if replacement_tool_id is not None:
                raise ValidationError(
                    "Un artículo por cantidad no requiere seleccionar "
                    "una pieza individual de reemplazo."
                )

            article = original_issue.stock.article
            replacement.stock_id = original_issue.stock_id

        if article.return_mode != Article.ReturnMode.RETURNABLE:
            raise ValidationError(
                "El artículo debe estar configurado con devolución "
                "para realizar este cambio."
            )

        register_quantity_return(return_record)

        replacement.replacement_for = return_record
        replacement.notes = (
            f"Reemplazo por la devolución #{return_record.pk}. "
            f"Motivo: {return_record.reason}"
        )

        register_quantity_issue(replacement)

    return replacement