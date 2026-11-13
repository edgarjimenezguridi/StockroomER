"""Panel exclusivo del jefe para autorizaciones de préstamos duplicados."""
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .duplicate_authorization_admin import es_jefe
from .loan_rules import motivo_duplicado, tiene_adeudos_vencidos
from .models import (
    Article, DuplicateLoanAuthorization, Employee, QuantityIssue,
)


class SolicitudExcepcionForm(forms.Form):
    employee = forms.ModelChoiceField(
        label="Trabajador", queryset=Employee.objects.filter(is_active=True),
    )
    article = forms.ModelChoiceField(
        label="Artículo", queryset=Article.objects.filter(is_active=True),
    )
    max_quantity = forms.IntegerField(label="Cantidad máxima a autorizar", min_value=1)
    reason = forms.CharField(
        label="Motivo de la excepción", max_length=1000,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def clean(self):
        data = super().clean()
        employee = data.get("employee")
        article = data.get("article")
        if employee and article:
            if tiene_adeudos_vencidos(employee.pk):
                raise forms.ValidationError(
                    "Este trabajador tiene adeudos vencidos. Primero debe regularizarlos."
                )
            if not motivo_duplicado(employee_id=employee.pk, article_id=article.pk):
                raise forms.ValidationError(
                    "No existe un duplicado activo para este artículo y trabajador. "
                    "Puede solicitarlo normalmente."
                )
        return data


def _exigir_jefe(request):
    if not es_jefe(request.user):
        raise PermissionDenied("Solo el jefe puede administrar autorizaciones.")


@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def panel_jefe(request):
    _exigir_jefe(request)
    form = SolicitudExcepcionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        employee = form.cleaned_data["employee"]
        article = form.cleaned_data["article"]
        try:
            with transaction.atomic():
                # Serializa altas de autorizaciones del mismo trabajador en PostgreSQL.
                Employee.objects.select_for_update().get(pk=employee.pk)
                if tiene_adeudos_vencidos(employee.pk):
                    raise ValidationError("El trabajador tiene préstamos vencidos.")
                if not motivo_duplicado(employee_id=employee.pk, article_id=article.pk):
                    raise ValidationError("El artículo ya no tiene un conflicto de duplicidad.")
                if DuplicateLoanAuthorization.objects.filter(
                    employee=employee, article=article,
                    status__in=[
                        DuplicateLoanAuthorization.Status.PENDING,
                        DuplicateLoanAuthorization.Status.APPROVED,
                    ], used_request__isnull=True,
                ).exists():
                    raise ValidationError(
                        "Ya existe una autorización pendiente o aprobada sin usar para este artículo."
                    )
                DuplicateLoanAuthorization.objects.create(
                    employee=employee, article=article,
                    max_quantity=form.cleaned_data["max_quantity"],
                    reason=form.cleaned_data["reason"].strip(),
                )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, "Excepción registrada. El jefe puede revisarla y autorizarla.")
            return redirect("panel_jefe")

    autorizaciones = DuplicateLoanAuthorization.objects.select_related(
        "employee", "article", "decided_by", "used_request"
    ).order_by("-created_at", "-pk")
    pendientes = autorizaciones.filter(status=DuplicateLoanAuthorization.Status.PENDING)
    historial = autorizaciones.exclude(status=DuplicateLoanAuthorization.Status.PENDING)[:40]
    vencidas = QuantityIssue.objects.filter(
        requires_return=True,
        returned_quantity__lt=F("quantity"),
        issued_at__lt=timezone.now() - timedelta(days=15),
    ).values("employee_id").distinct().count()
    return render(request, "stockroom/jefe/panel_jefe.html", {
        "form": form, "pendientes": pendientes, "historial": historial,
        "total_pendientes": pendientes.count(), "trabajadores_vencidos": vencidas,
    })


@never_cache
@login_required(login_url="acceso_jefe")
@require_POST
def resolver_autorizacion_jefe(request, authorization_id):
    _exigir_jefe(request)
    action = request.POST.get("decision")
    if action not in ("approve", "reject"):
        raise ValidationError("Decisión de autorización no válida.")
    status = (
        DuplicateLoanAuthorization.Status.APPROVED
        if action == "approve"
        else DuplicateLoanAuthorization.Status.REJECTED
    )
    with transaction.atomic():
        auth = get_object_or_404(
            DuplicateLoanAuthorization.objects.select_for_update(), pk=authorization_id
        )
        # No se resuelven nuevamente las autorizaciones ya usadas o decididas.
        if auth.status != DuplicateLoanAuthorization.Status.PENDING or auth.used_request_id:
            messages.error(request, "Esta autorización ya fue resuelta o utilizada.")
            return redirect("panel_jefe")
        # Una autorización nunca anula el bloqueo global de 15 días.
        if status == DuplicateLoanAuthorization.Status.APPROVED:
            if tiene_adeudos_vencidos(auth.employee_id):
                messages.error(request, "El trabajador tiene adeudos vencidos: no se puede aprobar.")
                return redirect("panel_jefe")
            if not motivo_duplicado(employee_id=auth.employee_id, article_id=auth.article_id):
                messages.error(request, "Ya no existe duplicado; no hace falta autorizar.")
                return redirect("panel_jefe")
        updated = DuplicateLoanAuthorization.objects.filter(
            pk=auth.pk, status=DuplicateLoanAuthorization.Status.PENDING,
            used_request__isnull=True,
        ).update(status=status, decided_by=request.user, decided_at=timezone.now())
        if updated != 1:
            messages.error(request, "Otra operación resolvió esta autorización.")
        else:
            messages.success(request, "Autorización aprobada." if action == "approve" else "Autorización rechazada.")
    return redirect("panel_jefe")
