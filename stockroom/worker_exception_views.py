"""Solicitud de préstamo duplicado iniciada por el propio trabajador.

Nunca aprueba excepciones ni modifica existencias: solo crea solicitudes
pendientes para revisión en el panel del jefe.
"""
from django import forms
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .loan_rules import motivo_duplicado, validar_bloqueo_vencimiento
from .models import Article, DuplicateLoanAuthorization, Employee, EmployeeCredential


class WorkerExceptionForm(forms.Form):
    article = forms.ModelChoiceField(
        label="Artículo a solicitar nuevamente",
        queryset=Article.objects.filter(is_active=True).order_by("article_code"),
        empty_label="Selecciona un artículo",
    )
    max_quantity = forms.IntegerField(
        label="Cantidad adicional que necesitas",
        min_value=1,
        max_value=100000,
        widget=forms.NumberInput(attrs={"min": "1", "step": "1"}),
    )
    reason = forms.CharField(
        label="Motivo de la solicitud",
        max_length=1000,
        min_length=10,
        widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Explica por qué necesitas otra pieza del mismo artículo"}),
    )


def _empleado_autenticado(request):
    employee_id = request.session.get("worker_employee_id")
    credential_id = request.session.get("worker_credential_id")
    if not employee_id or not credential_id:
        return None
    credential = EmployeeCredential.objects.select_related("employee").filter(
        pk=credential_id,
        employee_id=employee_id,
        is_active=True,
        employee__is_active=True,
    ).exclude(pin_hash="").first()
    return credential.employee if credential is not None else None


@never_cache
@require_http_methods(["GET", "POST"])
def solicitar_duplicado_empleado(request):
    employee = _empleado_autenticado(request)
    if employee is None:
        return redirect("acceso_empleado")

    inicial = {}
    article_id = request.GET.get("article")
    if article_id and article_id.isdecimal():
        inicial["article"] = article_id
    form = WorkerExceptionForm(
        request.POST if request.method == "POST" else None,
        initial=inicial,
    )

    if request.method == "POST" and form.is_valid():
        article = form.cleaned_data["article"]
        try:
            with transaction.atomic():
                # Misma serialización por empleado que carrito y envío.
                Employee.objects.select_for_update().get(pk=employee.pk, is_active=True)
                validar_bloqueo_vencimiento(employee.pk)

                if not motivo_duplicado(employee_id=employee.pk, article_id=article.pk):
                    raise ValidationError(
                        "Todavía no existe un préstamo o solicitud activa de este artículo. "
                        "Puedes solicitarlo normalmente desde el catálogo."
                    )

                pendiente_o_aprobada = DuplicateLoanAuthorization.objects.filter(
                    employee_id=employee.pk,
                    article_id=article.pk,
                    status__in=[
                        DuplicateLoanAuthorization.Status.PENDING,
                        DuplicateLoanAuthorization.Status.APPROVED,
                    ],
                    used_request__isnull=True,
                ).exists()
                if pendiente_o_aprobada:
                    raise ValidationError(
                        "Ya existe una petición pendiente o una autorización aprobada "
                        "sin utilizar para este artículo."
                    )

                DuplicateLoanAuthorization.objects.create(
                    employee_id=employee.pk,
                    article_id=article.pk,
                    max_quantity=form.cleaned_data["max_quantity"],
                    reason=form.cleaned_data["reason"].strip(),
                )
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(
                request,
                "Solicitud enviada al jefe. Podrás pedir el duplicado cuando sea aprobada.",
            )
            return redirect("solicitar_duplicado_empleado")

    historial = DuplicateLoanAuthorization.objects.filter(
        employee_id=employee.pk
    ).select_related("article").order_by("-created_at", "-pk")[:30]
    return render(request, "stockroom/empleados/solicitar_duplicado.html", {
        "employee": employee,
        "form": form,
        "historial": historial,
    })
