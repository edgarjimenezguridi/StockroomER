"""Solicitud de baja por almacén y autorización exclusiva desde el panel del jefe."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from .offboarding_services import aprobar_baja_trabajador
from .models import Employee, Loan, QuantityIssue, MaterialRequest, EmployeeOffboardingRequest


def _check_almacen(user):
    if not (user.is_authenticated and user.is_active and user.is_staff
            and user.has_perm('stockroom.view_employee')
            and user.has_perm('stockroom.view_quantityissue')):
        raise PermissionDenied('No tienes permisos para revisar bajas.')


def _check_jefe(user):
    if not (user.is_authenticated and user.is_active and user.is_staff
            and (user.is_superuser or user.groups.filter(name='Jefes').exists())):
        raise PermissionDenied('Solo el jefe puede autorizar bajas.')


def _open_issues(employee_id):
    return QuantityIssue.objects.filter(
        employee_id=employee_id, requires_return=True,
        returned_quantity__lt=F('quantity'),
    ).select_related('stock__article', 'tool__article').order_by('issued_at', 'pk')


def _legacy_loans(employee_id):
    return Loan.objects.filter(
        employee_id=employee_id, returned_at__isnull=True,
        unified_issue__isnull=True,
    ).select_related('tool__article').order_by('borrowed_at', 'pk')


def _active_requests(employee_id):
    return MaterialRequest.objects.filter(
        employee_id=employee_id,
        status__in=(MaterialRequest.Status.SUBMITTED, MaterialRequest.Status.PREPARED),
    )


def _employee_pk(raw):
    if not raw or not str(raw).isdigit():
        raise Http404('Trabajador no encontrado.')
    return int(raw)


@never_cache
@login_required(login_url='acceso_almacen')
@require_http_methods(['GET', 'POST'])
def baja_trabajador_almacen(request):
    """Almacén revisa adeudos y solicita; NO puede desactivar trabajadores."""
    _check_almacen(request.user)
    q = request.GET.get('q', '').strip()[:80]
    raw_id = request.POST.get('empleado') if request.method == 'POST' else request.GET.get('empleado')
    if request.method == 'POST':
        pk = _employee_pk(raw_id)
        if request.POST.get('confirmacion') != 'SOLICITAR':
            messages.error(request, 'Escribe SOLICITAR para enviar la solicitud al jefe.')
            return redirect(f'{request.path}?empleado={pk}')
        with transaction.atomic():
            employee = get_object_or_404(Employee.objects.select_for_update(), pk=pk)
            if not employee.is_active:
                messages.error(request, 'El trabajador ya está inactivo.')
            elif EmployeeOffboardingRequest.objects.filter(
                employee=employee, status=EmployeeOffboardingRequest.Status.PENDING
            ).exists():
                messages.warning(request, 'Ya existe una solicitud pendiente para este trabajador.')
            else:
                try:
                    EmployeeOffboardingRequest.objects.create(employee=employee, requested_by=request.user)
                    messages.success(request, 'Solicitud enviada al jefe. El trabajador sigue activo.')
                except IntegrityError:
                    messages.warning(request, 'Ya existe una solicitud pendiente.')
        return redirect(f'{request.path}?empleado={pk}')

    employees = Employee.objects.filter(is_active=True).order_by('last_name', 'first_name', 'pk')
    if q:
        for term in q.split():
            employees = employees.filter(
                Q(employee_id__icontains=term) | Q(first_name__icontains=term)
                | Q(last_name__icontains=term)
            )
    employee = None
    issues, legacy = [], []
    pending_request = None
    if raw_id:
        employee = get_object_or_404(Employee, pk=_employee_pk(raw_id))
        issues = list(_open_issues(employee.pk))
        legacy = list(_legacy_loans(employee.pk))
        pending_request = EmployeeOffboardingRequest.objects.filter(
            employee=employee, status=EmployeeOffboardingRequest.Status.PENDING,
        ).first()
    return render(request, 'stockroom/almacen/baja_trabajador.html', {
        'employees': employees[:100], 'query': q, 'employee': employee,
        'issues': issues, 'legacy': legacy,
        'pending': sum(i.quantity - i.returned_quantity for i in issues) + len(legacy),
        'pending_request': pending_request,
        'puede_devolver': request.user.has_perm('stockroom.add_quantityreturn'),
    })


@never_cache
@login_required(login_url='acceso_jefe')
@require_http_methods(['GET', 'POST'])
def solicitudes_baja_jefe(request):
    """Solo el jefe aprueba o rechaza; antes de aprobar revalida todos los adeudos."""
    _check_jefe(request.user)
    if request.method == 'POST':
        raw_id = request.POST.get('solicitud')
        if not raw_id or not raw_id.isdigit():
            return HttpResponseBadRequest('Solicitud inválida.')
        accion = request.POST.get('accion')
        if accion not in ('aprobar', 'rechazar'):
            return HttpResponseBadRequest('Acción inválida.')
        with transaction.atomic():
            obj = get_object_or_404(
                EmployeeOffboardingRequest.objects.select_for_update(), pk=int(raw_id)
            )
            employee = get_object_or_404(Employee.objects.select_for_update(), pk=obj.employee_id)
            if obj.status != EmployeeOffboardingRequest.Status.PENDING:
                messages.warning(request, 'La solicitud ya fue resuelta.')
            elif accion == 'rechazar':
                obj.status = EmployeeOffboardingRequest.Status.REJECTED
                obj.decided_by = request.user
                obj.decided_at = timezone.now()
                obj.save(update_fields=['status', 'decided_by', 'decided_at'])
                messages.success(request, 'Solicitud rechazada. El trabajador sigue activo.')
            
            else:
                try:
                    aprobar_baja_trabajador(
                        solicitud_id=obj.pk,
                        autorizado_por=request.user,
                    )
                except ValidationError as exc:
                    messages.error(
                        request,
                        " ".join(exc.messages),
                    )
                else:
                    messages.success(
                        request,
                        "Baja aprobada y trabajador desactivado. "
                        "Historial conservado.",
                    )

        return redirect('solicitudes_baja_jefe')
    solicitudes = EmployeeOffboardingRequest.objects.select_related(
        'employee', 'requested_by', 'decided_by'
    ).order_by('-requested_at', '-pk')[:150]
    pendientes = []
    historial = []
    for obj in solicitudes:
        if obj.status == EmployeeOffboardingRequest.Status.PENDING:
            obj.adeudos = (
                sum(i.quantity - i.returned_quantity for i in _open_issues(obj.employee_id))
                + _legacy_loans(obj.employee_id).count()
                + _active_requests(obj.employee_id).count()
            )
            pendientes.append(obj)
        else:
            historial.append(obj)
    return render(request, 'stockroom/jefe/solicitudes_baja.html', {
        'pendientes': pendientes, 'historial': historial,
    })
