"""Asignaciones de stock inicial, sin vencimiento, con control de duplicados."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .loan_rules import motivo_duplicado
from .models import Article, Employee, QuantityIssue, QuantityStock, Tool
from .services import register_individual_issue, register_quantity_issue


class InitialStockForm(forms.Form):
    employee = forms.ModelChoiceField(
        label="Trabajador", queryset=Employee.objects.filter(is_active=True).order_by("last_name", "first_name"),
        empty_label="Selecciona un trabajador",
    )
    article = forms.ModelChoiceField(
        label="Artículo", queryset=Article.objects.filter(
            is_active=True, return_mode=Article.ReturnMode.RETURNABLE
        ).order_by("name", "article_code"), empty_label="Selecciona una herramienta",
    )
    quantity = forms.IntegerField(label="Cantidad", min_value=1, initial=1)
    tool = forms.ModelChoiceField(
        label="Pieza individual (si corresponde)", required=False,
        queryset=Tool.objects.filter(is_active=True, inventory_status=Tool.InventoryStatus.AVAILABLE)
        .select_related("article").order_by("tool_code"),
        empty_label="Sin pieza individual",
    )

    def clean(self):
        data = super().clean()
        article, tool, qty = data.get("article"), data.get("tool"), data.get("quantity")
        if not article or qty is None:
            return data
        if article.tracking_mode == Article.TrackingMode.INDIVIDUAL:
            if qty != 1:
                self.add_error("quantity", "Una pieza individual se asigna de una en una.")
            if not tool or tool.article_id != article.pk:
                self.add_error("tool", "Selecciona una pieza disponible perteneciente al artículo elegido.")
        elif tool:
            self.add_error("tool", "Los artículos por cantidad no requieren pieza individual.")
        return data


def registrar_stock_inicial(*, employee_id, article_id, quantity, tool_id=None, user):
    """Movimiento atómico de inventario. Nunca consume excepciones de duplicado."""
    if not (user.is_authenticated and user.is_active and user.is_staff and
            user.has_perm("stockroom.add_quantityissue") and
            user.has_perm("stockroom.view_employee") and
            user.has_perm("stockroom.view_materialrequest")):
        raise PermissionDenied("No tienes permisos para asignar stock inicial.")
    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        raise ValidationError("La cantidad debe ser un entero positivo.")
    with transaction.atomic():
        employee = Employee.objects.select_for_update().filter(pk=employee_id, is_active=True).first()
        article = Article.objects.filter(
            pk=article_id, is_active=True, return_mode=Article.ReturnMode.RETURNABLE,
        ).first()
        if employee is None or article is None:
            raise ValidationError("El trabajador o la herramienta no están activos o no admiten devolución.")
        duplicate = motivo_duplicado(employee_id=employee.pk, article_id=article.pk)
        if duplicate:
            raise ValidationError(
                f"{duplicate} La asignación inicial no puede saltarse la regla de duplicados."
            )
        issue = QuantityIssue(
            employee=employee, quantity=quantity, is_initial_stock=True,
            notes=f"Stock inicial. Registró: {user.get_username()} (usuario #{user.pk}).",
        )
        if article.tracking_mode == Article.TrackingMode.QUANTITY:
            if tool_id is not None:
                raise ValidationError("No selecciones una pieza individual para un artículo por cantidad.")
            stock = QuantityStock.objects.select_for_update().filter(article=article).first()
            if stock is None:
                raise ValidationError("El artículo no cuenta con registro de existencias.")
            issue.stock = stock
            register_quantity_issue(issue)
        elif article.tracking_mode == Article.TrackingMode.INDIVIDUAL:
            if quantity != 1 or tool_id is None:
                raise ValidationError("Selecciona exactamente una pieza individual.")
            tool = Tool.objects.select_for_update().filter(
                pk=tool_id, article=article, is_active=True,
                inventory_status=Tool.InventoryStatus.AVAILABLE,
            ).first()
            if tool is None:
                raise ValidationError("La pieza no está disponible o no corresponde al artículo.")
            issue.tool = tool
            register_individual_issue(issue)
        else:
            raise ValidationError("Modalidad de control desconocida.")
        return issue


@never_cache
@login_required(login_url="acceso_almacen")
@require_http_methods(["GET", "POST"])
def asignar_stock_inicial_almacen(request):
    if not (request.user.is_active and request.user.is_staff and
            request.user.has_perm("stockroom.add_quantityissue") and
            request.user.has_perm("stockroom.view_employee") and
            request.user.has_perm("stockroom.view_materialrequest")):
        raise PermissionDenied("No tienes permiso para asignar stock inicial.")
    form = InitialStockForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            issue = registrar_stock_inicial(
                employee_id=data["employee"].pk, article_id=data["article"].pk,
                quantity=data["quantity"],
                tool_id=data["tool"].pk if data.get("tool") else None,
                user=request.user,
            )
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, f"Stock inicial asignado correctamente. Entrega #{issue.pk}.")
            return redirect("asignar_stock_inicial_almacen")
    return render(request, "stockroom/almacen/asignar_stock_inicial.html", {
        "form": form,
        "ultimas": QuantityIssue.objects.filter(is_initial_stock=True)
        .select_related("employee", "stock__article", "tool__article")
        .order_by("-issued_at", "-pk")[:15],
    })
