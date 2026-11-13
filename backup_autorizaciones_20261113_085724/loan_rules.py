"""Reglas centrales de préstamos: vencimiento y duplicidad por artículo.

Esta versión no efectúa movimientos de inventario ni consume autorizaciones.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.utils import timezone

from .models import Article, Loan, MaterialRequest, MaterialRequestLine, QuantityIssue

PLAZO_PRESTAMO_DIAS = 15
ESTADOS_ACTIVOS = (
    MaterialRequest.Status.SUBMITTED,
    MaterialRequest.Status.PREPARED,
)


def entregas_vencidas(employee_id, *, now=None):
    """Entregas retornables con saldo pendiente tras 15 días naturales."""
    ahora = now or timezone.now()
    return QuantityIssue.objects.filter(
        employee_id=employee_id,
        requires_return=True,
        returned_quantity__lt=F("quantity"),
        issued_at__lt=ahora - timedelta(days=PLAZO_PRESTAMO_DIAS),
    )


def prestamos_antiguos_vencidos(employee_id, *, now=None):
    """Préstamos legacy aún no unificados, sin duplicar QuantityIssue."""
    ahora = now or timezone.now()
    return Loan.objects.filter(
        employee_id=employee_id,
        returned_at__isnull=True,
        unified_issue__isnull=True,
        borrowed_at__lt=ahora - timedelta(days=PLAZO_PRESTAMO_DIAS),
    )


def tiene_adeudos_vencidos(employee_id, *, now=None):
    return (
        entregas_vencidas(employee_id, now=now).exists()
        or prestamos_antiguos_vencidos(employee_id, now=now).exists()
    )


def validar_bloqueo_vencimiento(employee_id, *, now=None):
    """Bloqueo general para NUEVAS comandas si existen adeudos vencidos."""
    if tiene_adeudos_vencidos(employee_id, now=now):
        raise ValidationError(
            "Tienes préstamos vencidos (más de 15 días). "
            "Devuelve los artículos pendientes para solicitar nuevamente."
        )


def motivo_duplicado(*, employee_id, article_id, excluir_solicitud_id=None):
    """Retorna el motivo de duplicidad, o None si no existe conflicto."""
    articulo = Article.objects.filter(pk=article_id, is_active=True).first()
    if articulo is None:
        raise ValidationError("El artículo no existe o está inactivo.")

    solicitudes = MaterialRequestLine.objects.filter(
        request__employee_id=employee_id,
        request__status__in=ESTADOS_ACTIVOS,
        article_id=article_id,
    )
    if excluir_solicitud_id is not None:
        solicitudes = solicitudes.exclude(request_id=excluir_solicitud_id)
    if solicitudes.exists():
        return "Ya existe una solicitud activa de este artículo."

    # Los consumibles se restringen durante una solicitud activa, pero
    # no generan deuda de devolución tras ser entregados.
    if articulo.return_mode != Article.ReturnMode.RETURNABLE:
        return None

    if QuantityIssue.objects.filter(
        employee_id=employee_id,
        requires_return=True,
        returned_quantity__lt=F("quantity"),
    ).filter(
        Q(stock__article_id=article_id) | Q(tool__article_id=article_id)
    ).exists():
        return "Ya tienes este artículo pendiente de devolución."

    if Loan.objects.filter(
        employee_id=employee_id,
        returned_at__isnull=True,
        unified_issue__isnull=True,
        tool__article_id=article_id,
    ).exists():
        return "Ya tienes un préstamo anterior de este artículo pendiente."

    return None


def validar_sin_duplicado(*, employee_id, article_id, excluir_solicitud_id=None):
    motivo = motivo_duplicado(
        employee_id=employee_id,
        article_id=article_id,
        excluir_solicitud_id=excluir_solicitud_id,
    )
    if motivo:
        raise ValidationError(
            f"{motivo} Se requiere autorización del jefe para el duplicado."
        )


def fecha_limite(issue):
    if not issue.requires_return:
        return None
    return issue.issued_at + timedelta(days=PLAZO_PRESTAMO_DIAS)


def estado_prestamo(issue, *, now=None):
    if not issue.requires_return:
        return "consumible"
    if issue.returned_quantity >= issue.quantity:
        return "devuelto"
    restante = fecha_limite(issue) - (now or timezone.now())
    if restante.total_seconds() < 0:
        return "vencido"
    if restante <= timedelta(days=3):
        return "por_vencer"
    return "en_plazo"


def validar_articulo_solicitable(
    *,
    employee_id,
    article_id,
    exclude_request_id=None,
):
    """
    Compatibilidad con las funciones que todavía
    utilizan el nombre anterior.
    """

    validar_bloqueo_vencimiento(employee_id)

    validar_sin_duplicado(
        employee_id=employee_id,
        article_id=article_id,
        excluir_solicitud_id=exclude_request_id,
    )
