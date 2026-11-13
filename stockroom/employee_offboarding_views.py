"""Baja operativa: bloquea desactivación si existen herramientas sin devolver.

No altera el inventario ni elimina movimientos históricos.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import Employee, Loan, QuantityIssue


def _check_access(user):
    if not (user.is_authenticated and user.is_active and user.is_staff and
            user.has_perm("stockroom.change_employee") and
            user.has_perm("stockroom.view_quantityissue") and
            user.has_perm("stockroom.view_employee")):
        raise PermissionDenied("No tienes permiso para dar de baja trabajadores.")


def _open_issues(employee_id):
    return (QuantityIssue.objects.filter(
        employee_id=employee_id, requires_return=True,
        returned_quantity__lt=F("quantity"),
    ).select_related("stock__article", "tool__article")
     .order_by("issued_at", "pk"))


def _legacy_loans(employee_id):
    return (Loan.objects.filter(
        employee_id=employee_id, returned_at__isnull=True,
        unified_issue__isnull=True,
    ).select_related("tool__article").order_by("borrowed_at", "pk"))


@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def baja_trabajador_almacen(request):
    _check_access(request.user)
    q = request.GET.get("q", "").strip()[:80]
    raw_id = request.POST.get("empleado") if request.method == "POST" else request.GET.get("empleado")
    employees = Employee.objects.filter(is_active=True).order_by("last_name", "first_name", "pk")
    if q:
        for term in q.split():
            employees = employees.filter(
                Q(employee_id__icontains=term) | Q(first_name__icontains=term) |
                Q(last_name__icontains=term)
            )
    employees = employees[:100]
    employee = None
    issues = []
    legacy = []
    if raw_id:
        # Valida identificador en vez de permitir ValueError en PK numérica.
        if not str(raw_id).isdigit():
            from django.http import Http404
            raise Http404("Trabajador no encontrado")
        employee = get_object_or_404(Employee, pk=raw_id)
        issues = list(_open_issues(employee.pk))
        legacy = list(_legacy_loans(employee.pk))

    if request.method == "POST":
        if employee is None:
            from django.http import HttpResponseBadRequest
            return HttpResponseBadRequest("Selecciona un trabajador.")
        if request.POST.get("confirmacion") != "BAJA":
            messages.error(request, "Escribe BAJA para confirmar la desactivación.")
        else:
            # Serializar la validación y la desactivación en una transacción.
            with transaction.atomic():
                locked = get_object_or_404(Employee.objects.select_for_update(), pk=employee.pk)
                if not locked.is_active:
                    messages.error(request, "El trabajador ya se encontraba inactivo.")
                elif _open_issues(locked.pk).exists() or _legacy_loans(locked.pk).exists():
                    messages.error(request, "No se puede dar de baja: todavía tiene herramientas pendientes de devolución.")
                else:
                    locked.is_active = False
                    locked.save(update_fields=["is_active"])
                    messages.success(request, "Trabajador dado de baja. Se conservó todo su historial.")
                    return redirect("baja_trabajador_almacen")
        return redirect(f"{request.path}?empleado={employee.pk}")

    pending = sum(i.quantity - i.returned_quantity for i in issues) + len(legacy)
    return render(request, "stockroom/almacen/baja_trabajador.html", {
        "employees": employees, "query": q, "employee": employee,
        "issues": issues, "legacy": legacy, "pending": pending,
        "puede_devolver": request.user.has_perm("stockroom.add_quantityreturn"),
    })
