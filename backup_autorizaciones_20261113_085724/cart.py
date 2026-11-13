
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .loan_rules import (
    validar_bloqueo_vencimiento,
    validar_sin_duplicado,
)
from .models import Employee, MaterialRequest, MaterialRequestLine
from .selectors import catalogo_articulos


def bloquear_trabajador(employee_id):
    """Comprueba que el trabajador exista y esté activo."""
    employee = Employee.objects.select_for_update().filter(
        pk=employee_id,
        is_active=True,
    ).first()

    if employee is None:
        raise ValidationError("El trabajador no está activo.")

    return employee


def set_cart_quantity(*, employee_id, article_id, quantity):
    if type(quantity) is not int or quantity < 1:
        raise ValidationError(
            "La cantidad debe ser un número entero mayor que cero."
        )

    with transaction.atomic():
        bloquear_trabajador(employee_id)

        # No permitir nuevas solicitudes con adeudos vencidos.
        validar_bloqueo_vencimiento(employee_id)

        cart, _ = MaterialRequest.objects.get_or_create(
            employee_id=employee_id,
            status=MaterialRequest.Status.DRAFT,
        )

        updated = MaterialRequest.objects.filter(
            pk=cart.pk,
            employee_id=employee_id,
            status=MaterialRequest.Status.DRAFT,
        ).update(updated_at=timezone.now())

        if updated != 1:
            raise ValidationError(
                "Este carrito ya no está abierto. Recarga la página."
            )

        article = catalogo_articulos().filter(
            pk=article_id,
        ).first()

        if article is None:
            raise ValidationError(
                "El artículo no existe o está inactivo."
            )

        # No permitir duplicados sin autorización.
        validar_sin_duplicado(
            employee_id=employee_id,
            article_id=article_id,
            excluir_solicitud_id=cart.pk,
        )

        if quantity > article.available_quantity:
            raise ValidationError(
                f"Actualmente hay {article.available_quantity} "
                "piezas disponibles de este artículo."
            )

        line, _ = MaterialRequestLine.objects.update_or_create(
            request=cart,
            article=article,
            defaults={"requested_quantity": quantity},
        )

        return line


def submit_cart(*, employee_id, cart_id):
    with transaction.atomic():
        bloquear_trabajador(employee_id)

        validar_bloqueo_vencimiento(employee_id)

        cart = MaterialRequest.objects.select_for_update().filter(
            pk=cart_id,
            employee_id=employee_id,
            status=MaterialRequest.Status.DRAFT,
        ).first()

        if cart is None:
            raise ValidationError(
                "El carrito ya fue enviado o no está disponible."
            )

        lines = MaterialRequestLine.objects.filter(
            request_id=cart.pk,
        )

        if not lines.exists():
            raise ValidationError(
                "Agrega al menos un artículo antes de enviar la solicitud."
            )

        for article_id in lines.values_list(
            "article_id", flat=True
        ):
            validar_sin_duplicado(
                employee_id=employee_id,
                article_id=article_id,
                excluir_solicitud_id=cart.pk,
            )

        if lines.filter(article__is_active=False).exists():
            raise ValidationError(
                "Tu carrito contiene un artículo desactivado. "
                "Retíralo antes de enviar la solicitud."
            )

        if lines.filter(prepared_quantity__gt=0).exists():
            raise ValidationError(
                "El carrito tiene cantidades preparadas inesperadas. "
                "Solicita al almacenista que lo revise."
            )

        submitted_at = timezone.now()

        updated = MaterialRequest.objects.filter(
            pk=cart.pk,
            employee_id=employee_id,
            status=MaterialRequest.Status.DRAFT,
        ).update(
            status=MaterialRequest.Status.SUBMITTED,
            submitted_at=submitted_at,
            updated_at=submitted_at,
        )

        if updated != 1:
            raise ValidationError(
                "El carrito ya fue enviado o no está disponible."
            )

        return MaterialRequest.objects.get(pk=cart.pk)
