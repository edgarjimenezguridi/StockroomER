"""Consulta y resguardo de herramientas a cargo del trabajador.

No registra movimientos: las devoluciones se realizan con la vista existente.
"""
from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import F, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .loan_rules import estado_prestamo
from .models import Employee, QuantityIssue


def _can_view(user):
    return bool(user.is_authenticated and user.is_active and user.is_staff and
                user.has_perm("stockroom.view_employee") and
                user.has_perm("stockroom.view_quantityissue") and
                user.has_perm("stockroom.view_materialrequest"))


def _guard(user):
    if not _can_view(user):
        raise PermissionDenied("No tienes permiso para consultar herramientas asignadas.")


def _open_issues(employee):
    return (QuantityIssue.objects.filter(
        employee=employee, requires_return=True,
        returned_quantity__lt=F("quantity"),
    ).select_related("stock__article", "tool__article", "employee")
     .order_by("is_initial_stock", "issued_at", "pk"))


def _data(employee):
    issues = list(_open_issues(employee))
    now = timezone.now()
    rows = []
    for issue in issues:
        pending = issue.quantity - issue.returned_quantity
        status = estado_prestamo(issue, now=now)
        rows.append({
            "issue": issue,
            "article": issue.tool.article if issue.tool_id else issue.stock.article,
            "code": issue.tool.tool_code if issue.tool_id else issue.stock.article.article_code,
            "pending": pending,
            "status": status,
            "label": "Stock inicial" if issue.is_initial_stock else "Préstamo normal",
            "deadline": issue.fecha_limite,
        })
    return rows


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def stock_asignado_almacen(request):
    _guard(request.user)
    query = request.GET.get("q", "").strip()[:80]
    workers = Employee.objects.filter(is_active=True).order_by("last_name", "first_name", "pk")
    if query:
        for term in query.split():
            workers = workers.filter(
                Q(employee_id__icontains=term) | Q(first_name__icontains=term) |
                Q(last_name__icontains=term)
            )
    workers = workers[:100]
    raw_id = request.GET.get("empleado", "")
    employee = None
    rows = []
    if raw_id:
        employee = get_object_or_404(Employee, pk=raw_id)
        rows = _data(employee)
    return render(request, "stockroom/almacen/stock_asignado.html", {
        "workers": workers, "query": query, "employee": employee, "rows": rows,
        "total_piezas": sum(row["pending"] for row in rows),
        "total_inicial": sum(row["pending"] for row in rows if row["issue"].is_initial_stock),
        "total_normales": sum(row["pending"] for row in rows if not row["issue"].is_initial_stock),
        "puede_devolver": request.user.has_perm("stockroom.add_quantityreturn"),
    })


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def resguardo_stock_pdf_almacen(request, employee_id):
    _guard(request.user)
    employee = get_object_or_404(Employee, pk=employee_id)
    rows = _data(employee)
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    except ImportError as exc:
        raise RuntimeError(
            "ReportLab no está instalado. Ejecuta: python -m pip install reportlab"
        ) from exc

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=35, leftMargin=35,
                                 topMargin=35, bottomMargin=35)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ResguardoTitulo", parent=styles["Heading1"],
                              alignment=TA_CENTER, textColor=colors.HexColor("#0F7A18"), spaceAfter=12))
    styles.add(ParagraphStyle(name="ResguardoCelda", parent=styles["Normal"],
                              fontSize=8, leading=11))
    cell = lambda value: Paragraph(escape(str(value)), styles["ResguardoCelda"])
    story = [
        Paragraph("ENGRANES Y RECTIFICADOS", styles["ResguardoTitulo"]),
        Paragraph("RESGUARDO DE HERRAMIENTAS ASIGNADAS", styles["Heading2"]),
        Spacer(1, 10),
        Paragraph(f"Trabajador: {escape(employee.first_name)} {escape(employee.last_name)}", styles["Normal"]),
        Paragraph(f"Número de empleado: {escape(employee.employee_id)}", styles["Normal"]),
        Paragraph(f"Fecha de consulta: {timezone.localtime().strftime('%d/%m/%Y %H:%M')}", styles["Normal"]),
        Spacer(1, 14),
    ]
    table_data = [[cell(s) for s in ("Tipo", "Herramienta / código", "Cant.", "Entrega", "Vence")]]
    for row in rows:
        issue = row["issue"]
        due = row["deadline"]
        table_data.append([
            cell(row["label"]),
            cell(f'{row["article"].name} / {row["code"]}'),
            cell(row["pending"]),
            cell(timezone.localtime(issue.issued_at).strftime("%d/%m/%Y")),
            cell(due.strftime("%d/%m/%Y") if due else "Sin vencimiento"),
        ])
    if not rows:
        table_data.append([cell("Sin herramientas pendientes"), "", "", "", ""])
    table = Table(table_data, colWidths=[77, 194, 38, 88, 96], repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8F5EA")),
        ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#CCD9D0")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story += [table, Spacer(1, 15), Paragraph(
        f"Total de piezas pendientes: <b>{sum(r['pending'] for r in rows)}</b>.", styles["Normal"]),
        Spacer(1, 15), Paragraph(
            "Este documento refleja los registros del sistema al momento de su emisión. "
            "La firma acredita conocimiento del resguardo; no registra una entrega o devolución.",
            styles["Normal"]), Spacer(1, 45),
        Paragraph("_____________________________                      _____________________________", styles["Normal"]),
        Paragraph("Firma del trabajador                                          Entregó / verificó (almacén)", styles["Normal"]),
    ]
    document.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="resguardo_{employee.pk}.pdf"'
    response["Cache-Control"] = "no-store, private"
    return response
