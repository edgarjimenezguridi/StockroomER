from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone

from .models import DuplicateLoanAuthorization


def es_jefe(user):
    return bool(user.is_active and user.is_staff and (
        user.is_superuser or user.groups.filter(name='Jefes').exists()
    ))


@admin.register(DuplicateLoanAuthorization)
class DuplicateLoanAuthorizationAdmin(admin.ModelAdmin):
    list_display = (
        'employee', 'article', 'max_quantity', 'status',
        'created_at', 'decided_by', 'decided_at', 'used_request',
    )
    list_filter = ('status', 'created_at')
    search_fields = (
        'employee__employee_id', 'employee__first_name',
        'employee__last_name', 'article__article_code', 'article__name',
    )
    readonly_fields = ('status', 'created_at', 'decided_by', 'decided_at', 'used_request')
    actions = ('aprobar', 'rechazar')

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff

    def has_add_permission(self, request):
        return es_jefe(request.user)

    def has_change_permission(self, request, obj=None):
        return es_jefe(request.user) and (obj is None or obj.status == obj.Status.PENDING)

    def has_delete_permission(self, request, obj=None):
        return False

    def get_actions(self, request):
        actions = super().get_actions(request)
        if not es_jefe(request.user):
            actions.pop('aprobar', None)
            actions.pop('rechazar', None)
        return actions

    def save_model(self, request, obj, form, change):
        if not es_jefe(request.user):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('Solo el jefe puede registrar excepciones.')
        if change and obj.pk:
            from django.core.exceptions import ValidationError
            raise ValidationError('No se pueden editar solicitudes de excepción ya creadas.')
        super().save_model(request, obj, form, change)

    @admin.action(description='Aprobar duplicados seleccionados (solo jefe)')
    def aprobar(self, request, queryset):
        self._resolver(request, queryset, DuplicateLoanAuthorization.Status.APPROVED)

    @admin.action(description='Rechazar duplicados seleccionados (solo jefe)')
    def rechazar(self, request, queryset):
        self._resolver(request, queryset, DuplicateLoanAuthorization.Status.REJECTED)

    def _resolver(self, request, queryset, status):
        if not es_jefe(request.user):
            from django.core.exceptions import PermissionDenied
            raise PermissionDenied('Solo el jefe puede resolver autorizaciones.')
        with transaction.atomic():
            count = queryset.filter(
                status=DuplicateLoanAuthorization.Status.PENDING,
                used_request__isnull=True,
            ).update(
                status=status,
                decided_at=timezone.now(),
                decided_by=request.user,
            )
        self.message_user(request, f'{count} autorización(es) resuelta(s).', messages.SUCCESS)
