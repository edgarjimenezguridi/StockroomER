"""Personal y cuentas administrativas. Solo jefatura; operaciones auditadas en Django LogEntry."""
from django import forms
from django.contrib import messages
from django.contrib.admin.models import LogEntry, CHANGE, ADDITION
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .duplicate_authorization_admin import es_jefe
from .models import Employee, EmployeeCredential, QuantityIssue, DamageResolution, DuplicateLoanAuthorization

WAREHOUSE_PERMISSIONS = (
    'view_materialrequest', 'change_materialrequest', 'view_employee',
    'view_article', 'add_article', 'view_tool', 'view_quantitystock',
    'view_quantityissue', 'add_quantityissue', 'view_quantityreturn',
    'add_quantityreturn', 'view_stockentry', 'add_stockentry',
    'view_damageresolution', 'add_damageresolution',
    'view_stockentrycorrection', 'add_stockentrycorrection',
)


def jefe_obligatorio(request):
    if not es_jefe(request.user):
        raise PermissionDenied('Solo jefatura puede administrar personal y accesos.')


class EmployeeForm(forms.ModelForm):
    class Meta:
        model = Employee
        fields = ('employee_id', 'first_name', 'last_name')
        labels = {'employee_id': 'Número de empleado'}

    def clean_employee_id(self):
        return self.cleaned_data['employee_id'].strip()

    def clean_first_name(self):
        return self.cleaned_data['first_name'].strip()

    def clean_last_name(self):
        return self.cleaned_data['last_name'].strip()


class AdminUserForm(forms.Form):
    username = forms.CharField(label='Usuario', max_length=150)
    first_name = forms.CharField(label='Nombre', max_length=150)
    last_name = forms.CharField(label='Apellidos', max_length=150)
    email = forms.EmailField(label='Correo', required=False)
    role = forms.ChoiceField(label='Rol', choices=(('warehouse', 'Almacenista'), ('boss', 'Jefe')))
    password = forms.CharField(label='Contraseña inicial', min_length=12, widget=forms.PasswordInput(render_value=False))

    def clean_password(self):
        value = self.cleaned_data['password']
        validate_password(value)
        return value

    def clean_username(self):
        value = self.cleaned_data['username'].strip()
        if get_user_model().objects.filter(username__iexact=value).exists():
            raise forms.ValidationError('Ya existe un usuario con ese nombre.')
        return value


def _audit(request, obj, message, added=False):
    LogEntry.objects.log_actions(
        user_id=request.user.pk,
        queryset=type(obj).objects.filter(pk=obj.pk),
        action_flag=ADDITION if added else CHANGE,
        change_message=message,
    )


def _warehouse_group():
    """Crea grupo con permisos funcionales necesarios; nunca permisos de cuentas/admin."""
    group, _ = Group.objects.get_or_create(name='StockroomER - Almacenistas')
    permissions = Permission.objects.filter(
        content_type__app_label='stockroom',
        codename__in=WAREHOUSE_PERMISSIONS,
    )
    found = set(permissions.values_list('codename', flat=True))
    missing = set(WAREHOUSE_PERMISSIONS) - found
    if missing:
        raise ValueError('Faltan permisos de almacén: ' + ', '.join(sorted(missing)))
    group.permissions.set(permissions)
    return group


def _jefes_activos():
    User = get_user_model()
    return User.objects.filter(is_active=True, is_staff=True, groups__name='Jefes').distinct().count() + User.objects.filter(is_active=True, is_staff=True, is_superuser=True).exclude(groups__name='Jefes').count()


@never_cache
@login_required(login_url='acceso_jefe')
@require_http_methods(['GET', 'POST'])
def personal_jefe(request):
    jefe_obligatorio(request)
    alta_empleado = EmployeeForm(prefix='empleado')
    alta_acceso = AdminUserForm(prefix='cuenta')
    if request.method == 'POST':
        tipo = request.POST.get('tipo')
        if tipo == 'empleado':
            alta_empleado = EmployeeForm(request.POST, prefix='empleado')
            if alta_empleado.is_valid():
                with transaction.atomic():
                    empleado = alta_empleado.save()
                    EmployeeCredential.objects.get_or_create(employee=empleado)
                    _audit(request, empleado, 'Alta de trabajador desde panel del jefe', added=True)
                messages.success(request, 'Trabajador dado de alta. Debe activar su NIP por el procedimiento habitual.')
                return redirect('personal_jefe')
        elif tipo == 'cuenta':
            alta_acceso = AdminUserForm(request.POST, prefix='cuenta')
            if alta_acceso.is_valid():
                with transaction.atomic():
                    data = alta_acceso.cleaned_data
                    User = get_user_model()
                    user = User.objects.create_user(
                        username=data['username'], password=data['password'],
                        first_name=data['first_name'], last_name=data['last_name'],
                        email=data['email'], is_staff=True, is_active=True,
                    )
                    group = _warehouse_group() if data['role'] == 'warehouse' else Group.objects.get_or_create(name='Jefes')[0]
                    user.groups.add(group)
                    _audit(request, user, 'Alta de cuenta administrativa: ' + data['role'], added=True)
                messages.success(request, 'Cuenta creada. Entrega la contraseña inicial por un canal seguro.')
                return redirect('personal_jefe')
        else:
            raise PermissionDenied('Acción no válida.')

    busqueda = request.GET.get('q', '').strip()[:100]
    empleados = Employee.objects.all().order_by('last_name', 'first_name')
    if busqueda:
        empleados = empleados.filter(Q(employee_id__icontains=busqueda) | Q(first_name__icontains=busqueda) | Q(last_name__icontains=busqueda))
    cuentas = get_user_model().objects.filter(is_staff=True).prefetch_related('groups').order_by('username')
    return render(request, 'stockroom/jefe/personal.html', {
        'alta_empleado': alta_empleado, 'alta_acceso': alta_acceso,
        'empleados': empleados[:150], 'cuentas': cuentas[:100], 'q': busqueda,
        'activos': Employee.objects.filter(is_active=True).count(),
        'inactivos': Employee.objects.filter(is_active=False).count(),
    })


@never_cache
@login_required(login_url='acceso_jefe')
@require_POST
def estado_trabajador_jefe(request, employee_id):
    jefe_obligatorio(request)
    with transaction.atomic():
        empleado = get_object_or_404(Employee.objects.select_for_update(), pk=employee_id)
        activar = request.POST.get('accion') == 'activar'
        if request.POST.get('accion') not in ('activar', 'desactivar'):
            raise PermissionDenied('Acción inválida.')
        empleado.is_active = activar
        empleado.save(update_fields=['is_active'])
        # No se borran credenciales, historial, préstamos ni adeudos.
        EmployeeCredential.objects.filter(employee=empleado).update(is_active=activar)
        if activar:
            EmployeeCredential.objects.get_or_create(employee=empleado)
        _audit(request, empleado, 'Reactivación' if activar else 'Baja administrativa')
    messages.success(request, 'Trabajador reactivado.' if activar else 'Trabajador desactivado. Sus adeudos se conservan.')
    return redirect('personal_jefe')


@never_cache
@login_required(login_url='acceso_jefe')
@require_http_methods(['GET'])
def expediente_trabajador_jefe(request, employee_id):
    jefe_obligatorio(request)
    empleado = get_object_or_404(Employee, pk=employee_id)
    issues = QuantityIssue.objects.filter(employee=empleado).select_related('stock__article', 'tool__article').order_by('-issued_at')
    damaged = DamageResolution.objects.filter(source_return__issue__employee=empleado)
    return render(request, 'stockroom/jefe/expediente.html', {
        'empleado': empleado, 'issues': issues[:80],
        'pendientes': issues.filter(requires_return=True, returned_quantity__lt=F('quantity')).count(),
        'desechadas': damaged.filter(outcome=DamageResolution.Outcome.SCRAPPED).aggregate(total=Sum('quantity'))['total'] or 0,
        'autorizaciones': DuplicateLoanAuthorization.objects.filter(employee=empleado).select_related('article').order_by('-created_at')[:20],
    })


@never_cache
@login_required(login_url='acceso_jefe')
@require_POST
def estado_cuenta_jefe(request, user_id):
    jefe_obligatorio(request)
    with transaction.atomic():
        User = get_user_model()
        target = get_object_or_404(User.objects.select_for_update(), pk=user_id)
        if target.pk == request.user.pk or target.is_superuser:
            raise PermissionDenied('No puedes modificar tu propia cuenta ni una cuenta superusuario.')
        accion = request.POST.get('accion')
        if accion not in ('activar', 'desactivar', 'warehouse', 'boss'):
            raise PermissionDenied('Acción inválida.')
        if (accion in ('desactivar', 'warehouse') and target.is_active and
            target.is_staff and (target.groups.filter(name='Jefes').exists()) and _jefes_activos() <= 1):
            raise PermissionDenied('No puedes desactivar al último jefe activo.')
        if accion in ('warehouse', 'boss') and (
            target.user_permissions.exists() or
            target.groups.exclude(name__in=('Jefes', 'StockroomER - Almacenistas')).exists()
        ):
            raise PermissionDenied('Esta cuenta tiene permisos avanzados: edítala en Django Admin.')
        if accion in ('activar', 'desactivar'):
            target.is_active = accion == 'activar'
            target.save(update_fields=['is_active'])
        else:
            group = _warehouse_group() if accion == 'warehouse' else Group.objects.get_or_create(name='Jefes')[0]
            # Revoca grupos de acceso previamente administrados; no altera superusuarios.
            target.groups.remove(*Group.objects.filter(name__in=('Jefes', 'StockroomER - Almacenistas')))
            target.groups.add(group)
            target.is_staff = True
            target.save(update_fields=['is_staff'])
        _audit(request, target, 'Gestión de cuenta: ' + accion)
    messages.success(request, 'Permisos o estado de cuenta actualizados.')
    return redirect('personal_jefe')
