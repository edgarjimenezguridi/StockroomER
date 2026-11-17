
"""Reporte PDF de expediente integral. Solo lectura."""

from io import BytesIO
from xml.sax.saxutils import escape
from django.contrib.staticfiles import finders
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)

from .assigned_stock_views import _data as obtener_stock_asignado
from .boss_personnel_views import jefe_obligatorio
from .employee_history_summary import calcular_resumen_devoluciones
from .models import (
    Employee,
    QuantityReturn,
    DamageResolution,
    DuplicateLoanAuthorization,
    EmployeeOffboardingRequest,
    Loan,
    MaterialRequest,
)

def obtener_logo_empresa_pdf():
    """Obtiene el logotipo original, sin deformarlo."""

    ruta = finders.find("img/logo_empresa.png")

    if not ruta:
        return None

    try:
        ancho_original, alto_original = ImageReader(
            ruta
        ).getSize()

        if ancho_original <= 0 or alto_original <= 0:
            return None

        # Limitar el tamaño sin alterar proporciones.
        escala = min(
            210 / ancho_original,
            65 / alto_original,
            1,
        )

        logo = Image(
            ruta,
            width=ancho_original * escala,
            height=alto_original * escala,
        )

        logo.hAlign = "LEFT"
        return logo

    except (OSError, ValueError, TypeError):
        return None


@never_cache
@login_required(login_url="acceso_jefe")
@require_GET
def expediente_pdf_jefe(request, employee_id):
    jefe_obligatorio(request)

    empleado = get_object_or_404(Employee, pk=employee_id)
    ahora = timezone.localtime()

    stock = obtener_stock_asignado(empleado)

    # Préstamos antiguos no migrados al sistema unificado.
    prestamos_antiguos = Loan.objects.filter(
        employee=empleado,
        returned_at__isnull=True,
        unified_issue__isnull=True,
    ).select_related(
        "tool__article",
    ).order_by("-borrowed_at", "-pk")

    # Solicitudes que todavía requieren atención.
    solicitudes_activas = MaterialRequest.objects.filter(
        employee=empleado,
        status__in=(
            MaterialRequest.Status.SUBMITTED,
            MaterialRequest.Status.PREPARED,
        ),
    ).order_by("-submitted_at", "-pk")


    devoluciones_qs = QuantityReturn.objects.filter(
        issue__employee=empleado,
    )
    resumen_bd = devoluciones_qs.aggregate(
        total=Sum("quantity"),
        danadas=Sum(
            "quantity",
            filter=Q(condition=QuantityReturn.Condition.DAMAGED),
        ),
    )

    resoluciones_qs = DamageResolution.objects.filter(
        source_return__issue__employee=empleado,
    )
    total_resueltas = (
        resoluciones_qs.aggregate(total=Sum("quantity"))["total"] or 0
    )

    resumen = calcular_resumen_devoluciones(
        total_devueltas=resumen_bd["total"],
        total_danadas=resumen_bd["danadas"],
        total_danos_resueltos=total_resueltas,
    )

    devoluciones = devoluciones_qs.select_related(
        "issue__stock__article",
        "issue__tool__article",
    ).order_by("-returned_at", "-pk")[:80]

    resoluciones = resoluciones_qs.select_related(
        "source_return__issue__stock__article",
        "source_return__issue__tool__article",
    ).order_by("-resolved_at", "-pk")[:80]

    autorizaciones = DuplicateLoanAuthorization.objects.filter(
        employee=empleado,
    ).select_related("article").order_by("-created_at", "-pk")[:20]

    bajas = EmployeeOffboardingRequest.objects.filter(
        employee=empleado,
    ).select_related(
        "requested_by", "decided_by",
    ).order_by("-requested_at", "-pk")[:20]

    buffer = BytesIO()
    pdf = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=35,
        rightMargin=35,
        topMargin=42,
        bottomMargin=42,
        title="Expediente integral del trabajador",
        author="StockroomER",
    )

    verde = colors.HexColor("#0F7A18")
    fondo = colors.HexColor("#EAF4EB")
    borde = colors.HexColor("#DCE5EB")

    estilos = getSampleStyleSheet()
    estilos.add(ParagraphStyle(
        name="TituloEmpresaER",
        parent=estilos["Heading1"],
        textColor=verde,
        fontSize=16,
        leading=20,
        spaceAfter=8,
    ))
    estilos.add(ParagraphStyle(
        name="CeldaER",
        parent=estilos["Normal"],
        fontSize=8,
        leading=11,
    ))
    estilos.add(ParagraphStyle(
        name="SeccionER",
        parent=estilos["Heading2"],
        textColor=verde,
        fontSize=11,
        spaceBefore=13,
        spaceAfter=7,
    ))

    estilos.add(ParagraphStyle(
        name="SubtituloEjecutivoER",
        parent=estilos["Normal"],
        textColor=colors.HexColor("#526174"),
        fontSize=9,
        leading=13,
        spaceAfter=8,
    ))


    def celda(valor):
        return Paragraph(
            escape(str(valor if valor is not None else "—")),
            estilos["CeldaER"],
        )

    def fecha(valor):
        if not valor:
            return "—"
        return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M")

    def articulo_de_issue(issue):
        if issue.tool_id:
            return issue.tool.article.name
        if issue.stock_id:
            return issue.stock.article.name
        return "Sin artículo"

    def tabla(columnas, filas, anchos):
        datos = [[celda(v) for v in columnas]]
        if filas:
            datos += [[celda(v) for v in fila] for fila in filas]
        else:
            datos.append(
                [celda("Sin registros")] +
                [celda("") for _ in columnas[1:]]
            )

        t = Table(
            datos,
            colWidths=anchos,
            repeatRows=1,
            hAlign="LEFT",
            splitByRow=1,
        )
        
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), fondo),
            ("TEXTCOLOR", (0, 0), (-1, 0), verde),
            ("GRID", (0, 0), (-1, -1), 0.3, borde),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        return t

    story = [
        Paragraph("ENGRANES Y RECTIFICADOS", estilos["TituloEmpresaER"]),
        Paragraph("EXPEDIENTE INTEGRAL DEL TRABAJADOR", estilos["Heading2"]),
        Spacer(1, 8),
        Paragraph(
            f"Empleado: {escape(empleado.first_name)} "
            f"{escape(empleado.last_name)}",
            estilos["Normal"],
        ),
        Paragraph(
            f"Número: {escape(empleado.employee_id)}",
            estilos["Normal"],
        ),
        Paragraph(
            "Estado: " + ("Activo" if empleado.is_active else "Inactivo"),
            estilos["Normal"],
        ),
        Paragraph(
            "Emitido: " + ahora.strftime("%d/%m/%Y %H:%M"),
            estilos["Normal"],
        ),
        Paragraph(
            "Generado por: " + escape(request.user.get_username()),
            estilos["Normal"],
        ),
    ]

    # Incorporar el logotipo original al inicio del reporte.
    logo_empresa = obtener_logo_empresa_pdf()

    if logo_empresa is not None:
        story.insert(0, Spacer(1, 8))
        story.insert(0, logo_empresa)


    total_stock = sum(f["pending"] for f in stock)
    total_inicial = sum(
        f["pending"] for f in stock if f["issue"].is_initial_stock
    )

    # Fase 19J: resumen ejecutivo.
    # Consultas de solo lectura.
    total_normales = total_stock - total_inicial
    total_antiguos = prestamos_antiguos.count()
    total_solicitudes_activas = solicitudes_activas.count()

    # Los préstamos antiguos se presentan por separado.
    # No se suman al inventario del sistema unificado.
    filas_resumen_ejecutivo = [
        ("Estado del trabajador",
         "Activo" if empleado.is_active else "Inactivo"),
        ("Piezas pendientes de devolución", total_stock),
        ("Stock inicial asignado", total_inicial),
        ("Préstamos normales pendientes", total_normales),
        ("Préstamos antiguos pendientes", total_antiguos),
        ("Solicitudes de material activas", total_solicitudes_activas),
        ("Piezas devueltas", resumen["total_devueltas"]),
        ("Piezas devueltas dañadas", resumen["total_danadas"]),
        ("Daños resueltos", resumen["total_danos_resueltos"]),
        ("Daños sin resolver", resumen["total_danos_sin_resolver"]),
    ]

    story += [
        Spacer(1, 12),
        Paragraph("RESUMEN EJECUTIVO", estilos["SeccionER"]),
            Paragraph(
            "Situación registrada del trabajador a la fecha "
            "de emisión. Los préstamos antiguos se muestran "
            "por separado de las entregas unificadas.",
            estilos["SubtituloEjecutivoER"],
        ),
        Spacer(1, 9),
        tabla(
            ["Indicador", "Resultado"],
            filas_resumen_ejecutivo,
            [355, 150],
        ),
        Spacer(1, 12),
    ]


    story += [
        Paragraph("Herramientas actualmente asignadas", estilos["SeccionER"]),
        tabla(
            ["Piezas asignadas", "Stock inicial", "Préstamos normales"],
            [[total_stock, total_inicial, total_stock - total_inicial]],
            [175, 155, 175],
        ),
        Spacer(1, 7),
        tabla(
            ["Devueltas", "Buenas", "Dañadas", "Daños resueltos", "Sin resolver"],
            [[
                resumen["total_devueltas"],
                resumen["total_buen_estado"],
                resumen["total_danadas"],
                resumen["total_danos_resueltos"],
                resumen["total_danos_sin_resolver"],
            ]],
            [101, 101, 101, 101, 101],
        ),
        Paragraph("Herramientas actualmente asignadas", estilos["SeccionER"]),
        tabla(
            ["Herramienta", "Código", "Tipo", "Pend.", "Vence"],
            [[
                f["article"].name,
                f["code"],
                f["label"],
                f["pending"],
                (
                    f["deadline"].strftime("%d/%m/%Y")
                    if f["deadline"] else "Sin vencimiento"
                ),
            ] for f in stock],
            [153, 96, 110, 48, 98],
        ),

        Paragraph("Préstamos antiguos pendientes", estilos["SeccionER"]),
        tabla(
            ["Herramienta", "Código", "Fecha de préstamo"],
            [[
                p.tool.name,
                p.tool.tool_code,
                fecha(p.borrowed_at),
            ] for p in prestamos_antiguos],
            [205, 140, 160],
        ),
        Paragraph("Solicitudes activas de material", estilos["SeccionER"]),
        tabla(
            ["Solicitud", "Estado", "Fecha de solicitud"],
            [[
                f"#{s.pk}",
                s.get_status_display(),
                fecha(s.submitted_at),
            ] for s in solicitudes_activas],
            [165, 170, 170],
        ),
        Paragraph("Historial de devoluciones", estilos["SeccionER"]),
        tabla(
            ["Artículo", "Cantidad", "Condición", "Fecha"],
            [[
                articulo_de_issue(d.issue),
                d.quantity,
                d.get_condition_display(),
                fecha(d.returned_at),
            ] for d in devoluciones],
            [175, 65, 105, 160],
        ),
        Paragraph("Resoluciones de daños", estilos["SeccionER"]),
        tabla(
            ["Artículo", "Cantidad", "Resultado", "Fecha"],
            [[
                articulo_de_issue(r.source_return.issue),
                r.quantity,
                r.get_outcome_display(),
                fecha(r.resolved_at),
            ] for r in resoluciones],
            [175, 65, 105, 160],
        ),
        Paragraph("Autorizaciones de duplicados", estilos["SeccionER"]),
        tabla(
            ["Artículo", "Estado", "Fecha"],
            [[
                a.article.name,
                a.get_status_display(),
                fecha(a.created_at),
            ] for a in autorizaciones],
            [205, 140, 160],
        ),
        Paragraph("Historial de solicitudes de baja", estilos["SeccionER"]),
        tabla(
            ["Solicitada", "Estado", "Autorizó / resolvió"],
            [[
                fecha(b.requested_at),
                b.get_status_display(),
                (
                    b.decided_by.get_username()
                    if b.decided_by_id else "Pendiente"
                ),
            ] for b in bajas],
            [165, 140, 200],
        ),
        Spacer(1, 16),
        Paragraph(
            "Documento informativo generado a partir de los registros "
            "de StockroomER. No registra entregas, devoluciones ni bajas. "
            "Los historiales muestran hasta 80 devoluciones y resoluciones, "
            "y hasta 20 autorizaciones y solicitudes de baja por sección.",
            estilos["Normal"],
        ),
    ]

    def pie_pagina(canvas, documento):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(
            35, 23, "StockroomER · Expediente de consulta"
        )
        canvas.drawRightString(
            A4[0] - 35, 23,
            f"Página {documento.page}",
        )
        canvas.restoreState()

    pdf.build(
        story,
        onFirstPage=pie_pagina,
        onLaterPages=pie_pagina,
    )

    response = HttpResponse(
        buffer.getvalue(),
        content_type="application/pdf",
    )
    response["Content-Disposition"] = (
        f'attachment; filename="expediente_{empleado.pk}.pdf"'
    )
    response["Cache-Control"] = "no-store, private"
    return response
