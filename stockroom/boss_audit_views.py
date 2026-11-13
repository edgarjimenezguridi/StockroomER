"""Auditoría de jefatura: solo lectura y sin exponer códigos de NIP."""
from django.contrib.admin.models import LogEntry
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.core.exceptions import PermissionDenied

from .duplicate_authorization_admin import es_jefe
from .models import PinResetAuthorization

# Lista cerrada: no mostrar change_message arbitrarios que pudieran incluir secretos.
ALLOWED = {
    'Alta de trabajador desde panel del jefe': ('Alta de trabajador', 'alta'),
    'Reactivación': ('Reactivación de trabajador', 'estado'),
    'Baja administrativa': ('Baja de trabajador', 'estado'),
    'Alta de cuenta administrativa: warehouse': ('Alta de cuenta de almacén', 'cuentas'),
    'Alta de cuenta administrativa: boss': ('Alta de cuenta de jefatura', 'cuentas'),
    'Gestión de cuenta: activar': ('Cuenta reactivada', 'cuentas'),
    'Gestión de cuenta: desactivar': ('Cuenta desactivada', 'cuentas'),
    'Gestión de cuenta: warehouse': ('Permiso asignado: almacén', 'permisos'),
    'Gestión de cuenta: boss': ('Permiso asignado: jefatura', 'permisos'),
    'Autorización inicial de NIP emitida': ('Autorización de NIP inicial', 'nip'),
}


def audit_entries(*, desde=None, hasta=None, categoria='', texto=''):
    """Retorna eventos de administración y recuperación; no lee códigos secretos."""
    logs = LogEntry.objects.filter(change_message__in=ALLOWED).select_related('user')
    resets = PinResetAuthorization.objects.select_related('issued_by', 'credential__employee')
    if desde:
        logs = logs.filter(action_time__date__gte=desde)
        resets = resets.filter(Q(created_at__date__gte=desde) | Q(used_at__date__gte=desde) | Q(revoked_at__date__gte=desde))
    if hasta:
        logs = logs.filter(action_time__date__lte=hasta)
        resets = resets.filter(Q(created_at__date__lte=hasta) | Q(used_at__date__lte=hasta) | Q(revoked_at__date__lte=hasta))
    if categoria and categoria != 'todos':
        allowed_messages = [msg for msg, (_, cat) in ALLOWED.items() if cat == categoria]
        logs = logs.filter(change_message__in=allowed_messages)
        if categoria != 'nip':
            resets = resets.none()
    if texto:
        logs = logs.filter(Q(object_repr__icontains=texto) | Q(user__username__icontains=texto))
        resets = resets.filter(
            Q(credential__employee__employee_id__icontains=texto) |
            Q(credential__employee__first_name__icontains=texto) |
            Q(credential__employee__last_name__icontains=texto) |
            Q(issued_by__username__icontains=texto)
        )

    events = []
    for log in logs.order_by('-action_time')[:300]:
        label, category = ALLOWED[log.change_message]
        events.append({
            'when': log.action_time,
            'action': label,
            'category': category,
            'actor': log.user.get_username(),
            'subject': log.object_repr,
            'detail': 'Registro administrativo',
        })
    for reset in resets.order_by('-created_at')[:200]:
        employee = reset.credential.employee
        subject = f'{employee.employee_id} - {employee.first_name} {employee.last_name}'
        actor = reset.issued_by.get_username()
        if (not desde or timezone.localdate(reset.created_at) >= desde) and (not hasta or timezone.localdate(reset.created_at) <= hasta):
            events.append({
            'when': reset.created_at,
            'action': 'Recuperación de NIP autorizada',
            'category': 'nip',
            'actor': actor,
            'subject': subject,
            'detail': 'Autorización emitida',
            })
        if reset.used_at and (not desde or timezone.localdate(reset.used_at) >= desde) and (not hasta or timezone.localdate(reset.used_at) <= hasta):
            events.append({
                'when': reset.used_at,
                'action': 'Recuperación de NIP completada',
                'category': 'nip',
                'actor': 'Trabajador',
                'subject': subject,
                'detail': f'Autorizado por {actor}',
            })
        if reset.revoked_at and (not desde or timezone.localdate(reset.revoked_at) >= desde) and (not hasta or timezone.localdate(reset.revoked_at) <= hasta):
            events.append({
                'when': reset.revoked_at,
                'action': 'Autorización de recuperación revocada',
                'category': 'nip',
                'actor': 'Sistema',
                'subject': subject,
                'detail': f'Autorización emitida por {actor}',
            })
    events.sort(key=lambda ev: ev['when'], reverse=True)
    return events[:200]


@never_cache
@login_required(login_url='acceso_jefe')
@require_GET
def auditoria_jefe(request):
    if not es_jefe(request.user):
        raise PermissionDenied('Solo jefatura puede consultar la auditoría.')
    desde_str = request.GET.get('desde', '').strip()[:10]
    hasta_str = request.GET.get('hasta', '').strip()[:10]
    desde = parse_date(desde_str) if desde_str else None
    hasta = parse_date(hasta_str) if hasta_str else None
    # Fechas inválidas no generan una consulta sin límites inesperada.
    if (desde_str and not desde) or (hasta_str and not hasta) or (desde and hasta and desde > hasta):
        desde_str = hasta_str = ''
        desde = hasta = timezone.localdate()
    category = request.GET.get('categoria', 'todos')
    if category not in ('todos', 'alta', 'estado', 'cuentas', 'permisos', 'nip'):
        category = 'todos'
    search = request.GET.get('q', '').strip()[:80]
    events = audit_entries(desde=desde, hasta=hasta, categoria=category, texto=search)
    return render(request, 'stockroom/jefe/auditoria.html', {
        'eventos': events,
        'desde': desde_str,
        'hasta': hasta_str,
        'categoria': category,
        'q': search,
        'total': len(events),
    })
