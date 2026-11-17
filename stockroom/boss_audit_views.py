"""Auditoría de jefatura: consultas de solo lectura, sin revelar códigos de NIP."""
from heapq import merge
from itertools import islice

from django.contrib.admin.models import LogEntry
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .duplicate_authorization_admin import es_jefe
from .models import PinResetAuthorization

# Lista cerrada: nunca mostrar change_message arbitrarios.
ALLOWED = {
    'Alta de trabajador desde panel del jefe': ('Alta de trabajador', 'alta'),
    'Reactivación': ('Reactivación de trabajador', 'estado'),
    'Baja de trabajador autorizada por jefatura': ('Baja de trabajador', 'estado'),
    'Reactivación de trabajador': ('Reactivación de trabajador', 'estado'),
    'Alta de cuenta administrativa: warehouse': ('Alta de cuenta de almacén', 'cuentas'),
    'Alta de cuenta administrativa: boss': ('Alta de cuenta de jefatura', 'cuentas'),
    'Gestión de cuenta: activar': ('Cuenta reactivada', 'cuentas'),
    'Gestión de cuenta: desactivar': ('Cuenta desactivada', 'cuentas'),
    'Gestión de cuenta: warehouse': ('Permiso asignado: almacén', 'permisos'),
    'Gestión de cuenta: boss': ('Permiso asignado: jefatura', 'permisos'),
    'Autorización inicial de NIP emitida': ('Autorización de NIP inicial', 'nip'),
    'Actualización de datos de trabajador': ('Datos de trabajador actualizados', 'datos'),
}

CATEGORIAS = ('todos', 'alta', 'datos', 'estado', 'cuentas', 'permisos', 'nip')


def _queries(*, desde=None, hasta=None, categoria='todos', texto='', responsable=''):
    """Obtiene cuatro consultas filtradas por la fecha REAL de cada evento."""
    logs = LogEntry.objects.filter(change_message__in=ALLOWED).select_related('user')
    resets = PinResetAuthorization.objects.select_related(
        'issued_by', 'credential__employee'
    )

    if categoria and categoria != 'todos':
        messages = [key for key, (_, cat) in ALLOWED.items() if cat == categoria]
        logs = logs.filter(change_message__in=messages)
        if categoria != 'nip':
            resets = resets.none()

    if texto:
        logs = logs.filter(
            Q(object_repr__icontains=texto) | Q(user__username__icontains=texto)
        )
        resets = resets.filter(
            Q(credential__employee__employee_id__icontains=texto)
            | Q(credential__employee__first_name__icontains=texto)
            | Q(credential__employee__last_name__icontains=texto)
            | Q(issued_by__username__icontains=texto)
        )

    if responsable:
        logs = logs.filter(user__username__icontains=responsable)
        # Para emisión se registra el nombre del jefe; en uso y revocación,
        # el responsable mostrado es respectivamente "Trabajador" y "Sistema".
        emitted = resets.filter(issued_by__username__icontains=responsable)
        used = resets if responsable.casefold() in 'trabajador' else resets.none()
        revoked = resets if responsable.casefold() in 'sistema' else resets.none()
    else:
        emitted = used = revoked = resets

    if desde:
        logs = logs.filter(action_time__date__gte=desde)
        emitted = emitted.filter(created_at__date__gte=desde)
        used = used.filter(used_at__date__gte=desde)
        revoked = revoked.filter(revoked_at__date__gte=desde)
    if hasta:
        logs = logs.filter(action_time__date__lte=hasta)
        emitted = emitted.filter(created_at__date__lte=hasta)
        used = used.filter(used_at__date__lte=hasta)
        revoked = revoked.filter(revoked_at__date__lte=hasta)

    used = used.filter(used_at__isnull=False)
    revoked = revoked.filter(revoked_at__isnull=False)
    return logs, emitted, used, revoked


def _log_events(logs):
    for log in logs.order_by('-action_time', '-pk').iterator(chunk_size=200):
        label, category = ALLOWED[log.change_message]
        yield {
            'when': log.action_time,
            'action': label,
            'category': category,
            'actor': log.user.get_username(),
            'subject': log.object_repr,
            'detail': 'Registro administrativo',
        }


def _reset_events(resets, field):
    for reset in resets.order_by(f'-{field}', '-pk').iterator(chunk_size=200):
        employee = reset.credential.employee
        subject = f'{employee.employee_id} - {employee.first_name} {employee.last_name}'
        issuer = reset.issued_by.get_username()
        if field == 'created_at':
            action, actor, detail = 'Recuperación de NIP autorizada', issuer, 'Autorización emitida'
        elif field == 'used_at':
            action, actor, detail = 'Recuperación de NIP completada', 'Trabajador', f'Autorizado por {issuer}'
        else:
            action, actor, detail = 'Autorización de recuperación revocada', 'Sistema', f'Autorización emitida por {issuer}'
        yield {
            'when': getattr(reset, field),
            'action': action,
            'category': 'nip',
            'actor': actor,
            'subject': subject,
            'detail': detail,
        }


def _merged_events(queries):
    logs, emitted, used, revoked = queries
    # Cada iterador está ordenado DESC; merge conserva orden sin crear
    # una lista con todo el historial.
    return merge(
        _log_events(logs),
        _reset_events(emitted, 'created_at'),
        _reset_events(used, 'used_at'),
        _reset_events(revoked, 'revoked_at'),
        key=lambda event: event['when'],
        reverse=True,
    )


def audit_entries(*, desde=None, hasta=None, categoria='', texto=''):
    """Interfaz existente para otros consumidores; devuelve lista completa."""
    queries = _queries(desde=desde, hasta=hasta, categoria=categoria, texto=texto)
    return list(_merged_events(queries))


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
    if ((desde_str and not desde) or (hasta_str and not hasta)
            or (desde and hasta and desde > hasta)):
        desde_str = hasta_str = ''
        desde = hasta = timezone.localdate()

    category = request.GET.get('categoria', 'todos')
    if category not in CATEGORIAS:
        category = 'todos'
    search = request.GET.get('q', '').strip()[:80]
    responsable = request.GET.get('responsable', '').strip()[:80]

    queries = _queries(
        desde=desde,
        hasta=hasta,
        categoria=category,
        texto=search,
        responsable=responsable,
    )
    total = sum(query.count() for query in queries)

    # range() no reserva una lista de tamaño total.
    paginador = Paginator(range(total), 25)
    pagina = paginador.get_page(request.GET.get('page', '1'))
    comienzo = pagina.start_index() - 1 if total else 0
    fin = comienzo + 25
    eventos = list(islice(_merged_events(queries), comienzo, fin))

    return render(request, 'stockroom/jefe/auditoria.html', {
        'eventos': eventos,
        'pagina': pagina,
        'desde': desde_str,
        'hasta': hasta_str,
        'categoria': category,
        'q': search,
        'responsable': responsable,
        'total': total,
    })
