from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Sum

from .models import (
    Article,
    Employee,
    Tool,
    Loan,
    QuantityStock,
    QuantityIssue,
    QuantityReturn,
    DamageResolution,
    StockEntryCorrection,
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
        # Una entrega nueva siempre debe iniciar
        # sin cantidades previamente devueltas.
        if issue.returned_quantity != 0:
            raise ValidationError(
                "Una entrega nueva no puede tener "
                "piezas ya devueltas."
            )

        # Obtener la modalidad real del artículo.
        article = Article.objects.get(
            quantity_stock__pk=issue.stock_id
        )

        # Establecer el valor correcto ANTES
        # de ejecutar las validaciones del modelo.
        issue.requires_return = (
            article.return_mode
            == Article.ReturnMode.RETURNABLE
        )

        issue.full_clean()

        # Impedir entregas a trabajadores inactivos.
        if not Employee.objects.filter(
            pk=issue.employee_id,
            is_active=True,
        ).exists():
            raise ValidationError(
                "El trabajador debe estar activo "
                "para recibir herramientas."
            )

        changes = {
            "available_quantity": (
                F("available_quantity") - issue.quantity
            ),
        }

        if issue.requires_return:
            changes["loaned_quantity"] = (
                F("loaned_quantity") + issue.quantity
            )

        # Actualización condicionada para evitar
        # descontar existencias insuficientes.
        updated = QuantityStock.objects.filter(
            pk=issue.stock_id,
            article__is_active=True,
            article__tracking_mode=Article.TrackingMode.QUANTITY,
            article__return_mode=article.return_mode,
            available_quantity__gte=issue.quantity,
        ).update(**changes)

        if updated != 1:
            raise ValidationError(
                "No se pudo registrar la entrega. "
                "Verifica que haya suficientes piezas "
                "disponibles y que el artículo esté activo. "
                "Recarga el formulario e intenta de nuevo."
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

            # Sincronizar el préstamo antiguo vinculado,
            # únicamente cuando la entrega esté completamente devuelta.
            if issue.legacy_loan_id:
                issue.refresh_from_db(
                    fields=["returned_quantity"]
                )

                if issue.returned_quantity == issue.quantity:
                    updated_loan = Loan.objects.filter(
                        pk=issue.legacy_loan_id,
                        tool_id=issue.tool_id,
                        employee_id=issue.employee_id,
                        returned_at__isnull=True,
                    ).update(
                        returned_at=return_record.returned_at
                    )

                    if updated_loan != 1:
                        raise ValidationError(
                            "No se pudo cerrar el préstamo antiguo "
                            "vinculado. Revisa su historial."
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

        
        # Impedir nuevas entregas mientras exista cualquier
        # préstamo antiguo abierto, esté vinculado o no
        # a una entrega del sistema unificado.
        if Loan.objects.filter(
            tool_id=tool.pk,
            returned_at__isnull=True,
        ).exists():
            raise ValidationError(
                "Esta pieza tiene un préstamo anterior pendiente. "
                "Registra su devolución antes de entregarla nuevamente."
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

def register_damage_resolution(resolution):
    if resolution.pk is not None or not resolution._state.adding:
        raise ValidationError(
            "Solo se pueden registrar resoluciones nuevas."
        )

    with transaction.atomic():
        resolution.full_clean()

        if not resolution.reason.strip():
            raise ValidationError(
                "Indica el motivo de la resolución."
            )

        source = QuantityReturn.objects.select_related(
            "issue",
        ).get(pk=resolution.source_return_id)

        if resolution.resolved_at < source.returned_at:
            raise ValidationError(
                "La resolución no puede ser anterior a la devolución."
            )

        updated_return = QuantityReturn.objects.filter(
            pk=source.pk,
            condition=QuantityReturn.Condition.DAMAGED,
            resolved_quantity__lte=(
                F("quantity") - resolution.quantity
            ),
        ).update(
            resolved_quantity=(
                F("resolved_quantity") + resolution.quantity
            )
        )

        if updated_return != 1:
            raise ValidationError(
                "La devolución no corresponde a piezas dañadas "
                "o la cantidad supera las piezas pendientes de revisión."
            )

        issue = source.issue
        restored = (
            resolution.outcome == DamageResolution.Outcome.RESTORED
        )

        if issue.tool_id:
            if resolution.quantity != 1:
                raise ValidationError(
                    "Para una pieza individual, la cantidad debe ser 1."
                )

            changes = {
                "inventory_status": (
                    Tool.InventoryStatus.AVAILABLE
                    if restored
                    else Tool.InventoryStatus.SCRAPPED
                ),
            }

            if not restored:
                changes["is_active"] = False

            updated_inventory = Tool.objects.filter(
                pk=issue.tool_id,
                inventory_status=Tool.InventoryStatus.QUARANTINE,
            ).update(**changes)

        else:
            destination = (
                "available_quantity"
                if restored
                else "scrapped_quantity"
            )

            updated_inventory = QuantityStock.objects.filter(
                pk=issue.stock_id,
                quarantine_quantity__gte=resolution.quantity,
            ).update(
                quarantine_quantity=(
                    F("quarantine_quantity") - resolution.quantity
                ),
                **{
                    destination: F(destination) + resolution.quantity,
                },
            )

        if updated_inventory != 1:
            raise ValidationError(
                "El inventario en revisión no coincide con la resolución. "
                "Revisa el historial antes de continuar."
            )

        resolution.save(force_insert=True)

    return resolution

def register_stock_entry_correction(correction, *, user):
    if correction.pk is not None or not correction._state.adding:
        raise ValidationError("Solo se pueden registrar correcciones nuevas.")

    correction.recorded_by = user
    correction.reason = correction.reason.strip()
    correction.full_clean()

    delta = correction.quantity_delta

    with transaction.atomic():
        stock = QuantityStock.objects.filter(entries__pk=correction.entry_id)

        if delta < 0:
            stock = stock.filter(available_quantity__gte=-delta)

        updated = stock.update(
            available_quantity=F("available_quantity") + delta
        )
        if updated != 1:
            raise ValidationError(
                "No hay suficientes piezas disponibles para aplicar el ajuste."
            )

        entry = correction.entry
        previous_delta = entry.corrections.aggregate(
            total=Sum("quantity_delta", default=0)
        )["total"]
        corrected_quantity = entry.quantity + previous_delta + delta

        if corrected_quantity < 0:
            raise ValidationError(
                "La corrección dejaría la cantidad de esta entrada "
                "por debajo de cero."
            )

        correction.save(force_insert=True)

    return correction