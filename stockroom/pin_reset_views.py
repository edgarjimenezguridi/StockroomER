"""Recuperación de NIP con autorización de jefatura, con persistencia de un solo uso."""
import re
import secrets
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password, make_password
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from .duplicate_authorization_admin import es_jefe
from .models import EmployeeCredential, PinResetAuthorization

WORKER_SALT = 'stockroom.worker-identification'
CODE_LENGTH = 10
CODE_TTL = timedelta(minutes=10)
MAX_ATTEMPTS = 5


def _digest(credential_id, code):
    return salted_hmac('stockroom.pin-reset-code.v1', f'{credential_id}:{code}', algorithm='sha256').hexdigest()


class ResetPinForm(forms.Form):
    code = forms.CharField(label='Código de recuperación', max_length=CODE_LENGTH, min_length=CODE_LENGTH,
                           widget=forms.TextInput(attrs={'inputmode': 'numeric', 'autocomplete': 'one-time-code', 'pattern': '[0-9]{10}'}))
    pin = forms.CharField(label='Nuevo NIP (6 dígitos)', max_length=6, min_length=6,
                          widget=forms.PasswordInput(attrs={'inputmode': 'numeric', 'autocomplete': 'new-password'}))
    pin_confirmation = forms.CharField(label='Confirmar NIP', max_length=6, min_length=6,
                                       widget=forms.PasswordInput(attrs={'inputmode': 'numeric', 'autocomplete': 'new-password'}))

    def clean(self):
        data = super().clean()
        for name, count in [('code', CODE_LENGTH), ('pin', 6), ('pin_confirmation', 6)]:
            value = data.get(name)
            if value is not None and not re.fullmatch(r'[0-9]{' + str(count) + r'}', value):
                self.add_error(name, f'Introduce exactamente {count} dígitos numéricos.')
        if data.get('pin') and data.get('pin_confirmation') and data['pin'] != data['pin_confirmation']:
            self.add_error('pin_confirmation', 'Los NIP no coinciden.')
        return data


def create_pin_reset(*, credential, operator):
    """El código solo se devuelve al jefe en la respuesta de esta llamada."""
    if not es_jefe(operator):
        raise PermissionDenied('Solo jefatura puede autorizar restablecimientos de NIP.')

    with transaction.atomic():
        credential = get_object_or_404(
            EmployeeCredential.objects.select_related('employee').select_for_update(), pk=credential.pk,
            is_active=True, employee__is_active=True,
        )
        if not credential.pin_hash:
            raise ValidationError('Esta credencial aún no tiene NIP. Utiliza el alta inicial.')

        now = timezone.now()
        PinResetAuthorization.objects.filter(
            credential=credential, used_at__isnull=True, revoked_at__isnull=True,
        ).update(revoked_at=now)
        code = f'{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}'
        PinResetAuthorization.objects.create(
            credential=credential, issued_by=operator,
            code_digest=_digest(credential.pk, code), expires_at=now + CODE_TTL,
        )
        return code


def reset_employee_pin(*, credential_id, code, new_pin):
    if not re.fullmatch(r'[0-9]{10}', code) or not re.fullmatch(r'[0-9]{6}', new_pin):
        raise ValidationError('Código o NIP con formato incorrecto.')

    invalid_code = False
    with transaction.atomic():
        credential = EmployeeCredential.objects.select_for_update().filter(
            pk=credential_id, is_active=True, employee__is_active=True,
        ).first()
        if credential is None:
            raise ValidationError('La credencial o el trabajador están inactivos.')
        authorization = PinResetAuthorization.objects.select_for_update().filter(
            credential=credential, used_at__isnull=True, revoked_at__isnull=True,
        ).order_by('-created_at', '-pk').first()
        now = timezone.now()
        if (authorization is None or authorization.expires_at <= now
                or authorization.attempts >= MAX_ATTEMPTS):
            raise ValidationError('La autorización no está disponible o ha vencido. Solicita otra a jefatura.')

        if not constant_time_compare(authorization.code_digest, _digest(credential.pk, code)):
            PinResetAuthorization.objects.filter(pk=authorization.pk, used_at__isnull=True,
                                                 revoked_at__isnull=True, attempts__lt=MAX_ATTEMPTS).update(
                attempts=F('attempts') + 1,
            )
            invalid_code = True

        if invalid_code:
            # La transacción debe terminar normalmente para guardar el intento fallido.
            pass
        elif check_password(new_pin, credential.pin_hash):
            raise ValidationError('El nuevo NIP debe ser diferente al anterior.')

        if not invalid_code:
            fingerprint = salted_hmac('stockroom.employee-pin-uniqueness.v1', new_pin, algorithm='sha256').hexdigest()
            if EmployeeCredential.objects.filter(pin_fingerprint=fingerprint).exclude(pk=credential.pk).exists():
                raise ValidationError('Elige otro NIP. Ese no está disponible.')

            # Un solo ganador incluso si dos solicitudes coinciden al mismo tiempo.
            affected = PinResetAuthorization.objects.filter(
                pk=authorization.pk, used_at__isnull=True, revoked_at__isnull=True,
                attempts__lt=MAX_ATTEMPTS, expires_at__gt=now,
            ).update(used_at=now)
            if affected != 1:
                raise ValidationError('La autorización ya fue utilizada o venció.')

            try:
                credential.pin_hash = make_password(new_pin)
                credential.pin_fingerprint = fingerprint
                credential.failed_pin_attempts = 0
                credential.pin_locked_until = None
                credential.save(update_fields=['pin_hash', 'pin_fingerprint', 'failed_pin_attempts', 'pin_locked_until'])
            except IntegrityError as exc:
                raise ValidationError('Elige otro NIP. Ese no está disponible.') from exc

    if invalid_code:
        raise ValidationError('Código incorrecto o no válido.')
    return credential.employee


@never_cache
@login_required(login_url='acceso_jefe')
@require_http_methods(['GET', 'POST'])
def autorizar_reset_nip_jefe(request, employee_id):
    if not es_jefe(request.user):
        raise PermissionDenied('Solo jefatura puede restablecer NIP.')
    credential = get_object_or_404(
        EmployeeCredential.objects.select_related('employee'), employee_id=employee_id,
    )
    code = None
    error = None
    if request.method == 'POST':
        try:
            code = create_pin_reset(credential=credential, operator=request.user)
        except ValidationError as exc:
            error = ' '.join(exc.messages)
    return render(request, 'stockroom/jefe/restablecer_nip.html', {
        'credential': credential, 'code': code, 'error': error,
    }, status=400 if error else 200)


@never_cache
@sensitive_post_parameters('code', 'pin', 'pin_confirmation')
@require_http_methods(['GET', 'POST'])
def recuperar_nip_trabajador(request):
    signed = request.session.get('pending_worker')
    if not signed:
        return redirect('acceso_empleado')
    try:
        data = signing.loads(signed, salt=WORKER_SALT, max_age=300)
        credential = EmployeeCredential.objects.select_related('employee').get(
            barcode=data['barcode'], is_active=True, employee__is_active=True,
        )
    except (signing.BadSignature, KeyError, TypeError, EmployeeCredential.DoesNotExist):
        request.session.pop('pending_worker', None)
        return redirect('acceso_empleado')

    if not credential.pin_hash:
        return redirect('acceso_empleado')

    form = ResetPinForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            reset_employee_pin(credential_id=credential.pk,
                               code=form.cleaned_data['code'], new_pin=form.cleaned_data['pin'])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            request.session.pop('pending_worker', None)
            request.session.pop('pin_setup_pending', None)
            messages.success(request, 'NIP actualizado. Ingresa nuevamente con el NIP nuevo.')
            return redirect('acceso_empleado')

    return render(request, 'stockroom/credenciales/recuperar_nip.html', {
        'credential': credential, 'form': form,
    })
