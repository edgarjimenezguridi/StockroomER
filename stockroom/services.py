from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F

from .models import Article, QuantityStock


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