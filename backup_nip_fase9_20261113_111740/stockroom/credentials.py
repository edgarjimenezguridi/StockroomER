from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from .models import EmployeeCredential
from datetime import timedelta
from uuid import UUID
from django.utils import timezone

import re
from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.utils.crypto import salted_hmac


ACTIVATION_SALT = "stockroom.employee-pin-activation"
ACTIVATION_MAX_AGE = 5 * 60


def authorize_pin_setup(*, credential, operator):
    if not (
        operator.is_active
        and operator.is_staff
        and operator.has_perm("stockroom.change_employeecredential")
    ):
        raise PermissionDenied(
            "Se requiere un usuario autorizado para activar credenciales."
        )

    if not credential.is_active or not credential.employee.is_active:
        raise ValidationError("El trabajador y su credencial deben estar activos.")

    if credential.pin_hash:
        raise ValidationError("Esta credencial ya tiene un NIP configurado.")

    return signing.dumps(
        {"barcode": str(credential.barcode)},
        salt=ACTIVATION_SALT,
    )


def get_credential_for_setup(*, barcode, authorization):
    try:
        data = signing.loads(
            authorization,
            salt=ACTIVATION_SALT,
            max_age=ACTIVATION_MAX_AGE,
        )
    except signing.SignatureExpired:
        raise ValidationError(
            "La autorización venció. Solicita otra al almacenista."
        )
    except signing.BadSignature:
        raise ValidationError("La autorización de activación es inválida.")

    if data.get("barcode") != str(barcode):
        raise ValidationError("La autorización corresponde a otra credencial.")

    credential = EmployeeCredential.objects.select_related("employee").filter(
        barcode=barcode,
        is_active=True,
        employee__is_active=True,
    ).first()

    if credential is None:
        raise ValidationError("La credencial o el trabajador están inactivos.")

    if credential.pin_hash:
        raise ValidationError("Esta credencial ya tiene un NIP configurado.")

    return credential

def activate_pin(*, barcode, authorization, pin, pin_confirmation):
    credential = get_credential_for_setup(
        barcode=barcode,
        authorization=authorization,
    )

    if not isinstance(pin, str) or not re.fullmatch(r"[0-9]{6}", pin):
        raise ValidationError("El NIP debe contener exactamente 6 dígitos.")

    if pin != pin_confirmation:
        raise ValidationError("Los dos NIP deben coincidir.")

    fingerprint = salted_hmac(
        "stockroom.employee-pin-uniqueness.v1",
        pin,
        algorithm="sha256",
    ).hexdigest()
    encoded_pin = make_password(pin)

    try:
        with transaction.atomic():
            updated = EmployeeCredential.objects.filter(
                pk=credential.pk,
                barcode=credential.barcode,
                is_active=True,
                employee__is_active=True,
                pin_hash="",
            ).update(
                pin_hash=encoded_pin,
                pin_fingerprint=fingerprint,
            )
    except IntegrityError:
        if EmployeeCredential.objects.filter(pin_fingerprint=fingerprint).exists():
            raise ValidationError("Elige otro NIP. Ese no está disponible.")
        raise

    if updated != 1:
        raise ValidationError(
            "La credencial ya se activó o dejó de estar disponible."
        )

def verify_employee_pin(*, barcode, pin):
    try:
        barcode = UUID(str(barcode))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError("La credencial no es válida.")

    # Si otra solicitud cambia el contador, volvemos a leerlo.
    for _ in range(5):
        credential = EmployeeCredential.objects.select_related(
            "employee"
        ).filter(
            barcode=barcode,
            is_active=True,
            employee__is_active=True,
        ).first()

        if credential is None:
            raise ValidationError(
                "La credencial no existe o está inactiva."
            )

        if not credential.pin_hash:
            raise ValidationError(
                "Primero debes activar el NIP de esta credencial."
            )

        now = timezone.now()

        if (
            credential.pin_locked_until is not None
            and credential.pin_locked_until > now
        ):
            raise ValidationError(
                "Acceso bloqueado temporalmente. "
                "Espera a que termine el bloqueo de 5 minutos."
            )

        attempts = credential.failed_pin_attempts

        # Después de un bloqueo vencido, comienza un nuevo ciclo.
        if credential.pin_locked_until is not None:
            attempts = 0

        valid = (
            isinstance(pin, str)
            and re.fullmatch(r"[0-9]{6}", pin) is not None
            and check_password(pin, credential.pin_hash)
        )

        new_attempts = 0 if valid else attempts + 1
        locked_until = None

        if not valid and new_attempts >= 5:
            locked_until = timezone.now() + timedelta(minutes=5)

        updated = EmployeeCredential.objects.filter(
            pk=credential.pk,
            is_active=True,
            employee__is_active=True,
            pin_hash=credential.pin_hash,
            failed_pin_attempts=credential.failed_pin_attempts,
            pin_locked_until=credential.pin_locked_until,
        ).update(
            failed_pin_attempts=new_attempts,
            pin_locked_until=locked_until,
        )

        if updated != 1:
            continue

        if valid:
            return credential.employee

        if locked_until is not None:
            raise ValidationError(
                "Acumulaste 5 intentos incorrectos. "
                "El acceso queda bloqueado durante 5 minutos."
            )

        raise ValidationError(
            f"NIP incorrecto. Intentos restantes: {5 - new_attempts}."
        )

    raise ValidationError(
        "Se recibió otra solicitud al mismo tiempo. Intenta nuevamente."
    )