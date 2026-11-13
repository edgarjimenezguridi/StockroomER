"""Reglas centrales de préstamos: vencimiento y duplicidad por artículo.

Esta versión no efectúa movimientos de inventario ni consume autorizaciones.
"""
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import F, Q
from django.utils import timezone

from .models import Article, Loan, MaterialRequest, MaterialRequestLine, QuantityIssue, DuplicateLoanAuthorization

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
        is_initial_stock=False,
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


def autorizacion_aprobada(*, employee_id, article_id, quantity, request_id=None):
    """Busca una autorización libre o ya vinculada a esta solicitud.

    No permite usar una autorización de otra solicitud o por más cantidad.
    """
    aprobadas = DuplicateLoanAuthorization.objects.filter(
        employee_id=employee_id,
        article_id=article_id,
        status=DuplicateLoanAuthorization.Status.APPROVED,
        max_quantity__gte=quantity,
    )
    if request_id is not None:
        vinculada = aprobadas.filter(used_request_id=request_id).first()
        if vinculada:
            return vinculada
    return aprobadas.filter(used_request__isnull=True).first()


def validar_sin_duplicado(
    *, employee_id, article_id, excluir_solicitud_id=None,
    quantity=1, require_bound=False,
):
    """Valida duplicidad; una autorización aprobada permite excepción puntual."""
    motivo = motivo_duplicado(
        employee_id=employee_id,
        article_id=article_id,
        excluir_solicitud_id=excluir_solicitud_id,
    )
    if not motivo:
        return None

    autorizacion = autorizacion_aprobada(
        employee_id=employee_id,
        article_id=article_id,
        quantity=quantity,
        request_id=excluir_solicitud_id,
    )
    if autorizacion is not None and (
        not require_bound or autorizacion.used_request_id == excluir_solicitud_id
    ):
        return autorizacion

    raise ValidationError(
        f"{motivo} Se requiere autorización aprobada del jefe para el duplicado."
    )


def vincular_autorizacion_si_necesaria(*, employee_id, article_id, quantity, request_id):
    """Reserva una aprobación una sola vez, dentro de la transacción del envío."""
    autorizacion = validar_sin_duplicado(
        employee_id=employee_id, article_id=article_id,
        excluir_solicitud_id=request_id, quantity=quantity,
    )
    if autorizacion is None:
        return None
    updated = DuplicateLoanAuthorization.objects.filter(
        pk=autorizacion.pk,
        status=DuplicateLoanAuthorization.Status.APPROVED,
        used_request__isnull=True,
    ).update(used_request_id=request_id)
    if updated != 1:
        # La misma autorización fue usada por otra comanda o invalidada.
        if autorizacion.used_request_id != request_id:
            raise ValidationError("La autorización ya fue utilizada o dejó de estar vigente.")
    return autorizacion


def fecha_limite(issue):
    if not issue.requires_return or issue.is_initial_stock:
        return None
    return issue.issued_at + timedelta(days=PLAZO_PRESTAMO_DIAS)


def estado_prestamo(issue, *, now=None):
    if not issue.requires_return:
        return "consumible"
    if issue.returned_quantity >= issue.quantity:
        return "devuelto"
    if issue.is_initial_stock:
        return "stock_inicial"
    restante = fecha_limite(issue) - (now or timezone.now())
    if restante.total_seconds() < 0:
        return "vencido"
    if restante <= timedelta(days=3):
        return "por_vencer"
    return "en_plazo"


def validar_articulo_solicitable(
    *, employee_id, article_id, exclude_request_id=None,
    quantity=1, require_bound=False,
):
    """Control de adeudos y duplicados antes de la entrega."""
    validar_bloqueo_vencimiento(employee_id)
    return validar_sin_duplicado(
        employee_id=employee_id,
        article_id=article_id,
        excluir_solicitud_id=exclude_request_id,
        quantity=quantity,
        require_bound=require_bound,
    )


# Compatibilidad con las propiedades QuantityIssue.fecha_limite / estado_plazo.
def fecha_limite_prestamo(issue):
    return fecha_limite(issue)


def estado_plazo_prestamo(issue):
    return estado_prestamo(issue)
