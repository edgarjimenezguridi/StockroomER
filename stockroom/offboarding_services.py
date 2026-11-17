
"""Servicio central para aprobar bajas de trabajadores."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.contrib.admin.models import LogEntry, CHANGE

from .models import (
    Employee,
    EmployeeOffboardingRequest,
    Loan,
    MaterialRequest,
    QuantityIssue,
    EmployeeCredential,
)


@transaction.atomic
def aprobar_baja_trabajador(*, solicitud_id, autorizado_por):
    """Aprueba una baja si el jefe tiene permiso y no existen pendientes."""

    if not (
        autorizado_por.is_authenticated
        and autorizado_por.is_active
        and autorizado_por.is_staff
        and (
            autorizado_por.is_superuser
            or autorizado_por.groups.filter(name="Jefes").exists()
        )
    ):
        raise PermissionDenied("Solo el jefe puede autorizar bajas.")

    try:
        solicitud = EmployeeOffboardingRequest.objects.select_for_update().get(
            pk=solicitud_id,
        )
    except EmployeeOffboardingRequest.DoesNotExist:
        raise ValidationError("La solicitud de baja no existe.")

    if solicitud.status != EmployeeOffboardingRequest.Status.PENDING:
        raise ValidationError("La solicitud ya fue resuelta.")

    trabajador = Employee.objects.select_for_update().get(
        pk=solicitud.employee_id,
    )

    if not trabajador.is_active:
        raise ValidationError("El trabajador ya está inactivo.")

    entregas_pendientes = QuantityIssue.objects.filter(
        employee=trabajador,
        requires_return=True,
        returned_quantity__lt=F("quantity"),
    ).exists()

    prestamos_antiguos = Loan.objects.filter(
        employee=trabajador,
        returned_at__isnull=True,
        unified_issue__isnull=True,
    ).exists()

    solicitudes_activas = MaterialRequest.objects.filter(
        employee=trabajador,
        status__in=(
            MaterialRequest.Status.SUBMITTED,
            MaterialRequest.Status.PREPARED,
        ),
    ).exists()

    if entregas_pendientes or prestamos_antiguos or solicitudes_activas:
        raise ValidationError(
            "No se puede aprobar la baja: el trabajador tiene "
            "herramientas pendientes o solicitudes activas."
        )

    solicitud.status = EmployeeOffboardingRequest.Status.APPROVED
    solicitud.decided_by = autorizado_por
    solicitud.decided_at = timezone.now()
    solicitud.save(update_fields=[
        "status",
        "decided_by",
        "decided_at",
    ])

    trabajador.is_active = False
    trabajador.save(update_fields=["is_active"])
    
        # Revocar también el acceso del trabajador.
    EmployeeCredential.objects.filter(
        employee=trabajador,
    ).update(is_active=False)

    # Registrar la baja autorizada en el historial administrativo.
    LogEntry.objects.log_actions(
        user_id=autorizado_por.pk,
        queryset=Employee.objects.filter(pk=trabajador.pk),
        action_flag=CHANGE,
        change_message="Baja de trabajador autorizada por jefatura",
    )


    return solicitud

