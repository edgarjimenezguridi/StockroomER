"""Informes PDF ejecutivos: consultas de solo lectura y acceso exclusivo de jefatura."""
from datetime import timedelta
from io import BytesIO
from xml.sax.saxutils import escape

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import F
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from .boss_audit_views import audit_entries
from .duplicate_authorization_admin import es_jefe
from .loan_rules import fecha_limite
from .models import Loan, QuantityIssue, QuantityStock
from .templatetags.jefe_dashboard import indicadores_jefe

REPORTES = {
    'auditoria': 'Historial administrativo',
    'vencidos': 'Préstamos vencidos',
    'desechos': 'Piezas desechadas por trabajador',
    'minimos': 'Existencias bajo mínimo',
}
PERIODOS = {'7': 7, '30': 30, '90': 90, 'todo': None}


def _params(request):
    tipo = request.GET.get('tipo', '')
    periodo = request.GET.get('periodo', '30')
    if tipo not in REPORTES or periodo not in PERIODOS:
        return None
    desde_raw = request.GET.get('desde', '').strip()
    hasta_raw = request.GET.get('hasta', '').strip()
    desde = parse_date(desde_raw) if desde_raw else None
    hasta = parse_date(hasta_raw) if hasta_raw else None
    if (desde_raw and not desde) or (hasta_raw and not hasta) or (desde and hasta and desde > hasta):
        return None
    if desde and hasta and (hasta - desde).days > 366:
        return None
    return tipo, periodo, desde, hasta


def _limites(periodo, desde, hasta):
    if desde or hasta:
        return desde, hasta
    dias = PERIODOS[periodo]
    return (timezone.localdate() - timedelta(days=dias), timezone.localdate()) if dias else (None, None)


def _contenido(tipo, periodo, desde, hasta):
    """Devuelve cabeceras y filas. La ventana de fechas aplica a la fecha del evento.

    Vencidos y mínimos son fotografías actuales; no les corresponde filtrar por
    fecha de creación (se aclara expresamente en el reporte).
    """
    if tipo == 'auditoria':
        eventos = audit_entries(desde=desde, hasta=hasta)
        return ['Fecha', 'Operación', 'Responsable', 'Sujeto'], [
            [timezone.localtime(e['when']).strftime('%d/%m/%Y %H:%M'), e['action'], e['actor'], e['subject']]
            for e in eventos
        ], 'Hasta 200 registros recientes. Nunca incluye secretos ni contraseñas.'

    if tipo == 'desechos':
        # Mismo cálculo que el dashboard, para períodos predefinidos.
        # Las fechas personalizadas se resuelven por queryset separado.
        if desde or hasta:
            from django.db.models import Q, Sum
            from .models import DamageResolution
            q = DamageResolution.objects.filter(source_return__condition='damaged')
            if desde: q = q.filter(resolved_at__date__gte=desde)
            if hasta: q = q.filter(resolved_at__date__lte=hasta)
            groups = q.values('source_return__issue__employee__employee_id',
                              'source_return__issue__employee__first_name',
                              'source_return__issue__employee__last_name').annotate(
                 bajas=Sum('quantity', filter=Q(outcome=DamageResolution.Outcome.SCRAPPED)),
                 recuperadas=Sum('quantity', filter=Q(outcome=DamageResolution.Outcome.RESTORED)))
            datos = [dict(numero=g['source_return__issue__employee__employee_id'],
                          nombre=(g['source_return__issue__employee__first_name'] + ' ' + g['source_return__issue__employee__last_name']).strip(),
                          desechadas=g['bajas'] or 0, recuperadas=g['recuperadas'] or 0) for g in groups]
        else:
            datos = indicadores_jefe(periodo)['filas_desechos']
        datos = sorted(datos, key=lambda x: (-x['desechadas'], x['nombre']))
        return ['Nº empleado', 'Trabajador', 'Desechadas', 'Recuperadas'], [
            [x['numero'], x['nombre'], str(x['desechadas']), str(x['recuperadas'])] for x in datos[:200]
        ], 'Las bajas se atribuyen a quien recibió las piezas. No prueban negligencia por sí solas.'

    if tipo == 'vencidos':
        ahora = timezone.now()
        limite = ahora - timedelta(days=15)
        entregas = (QuantityIssue.objects.filter(requires_return=True,
                    returned_quantity__lt=F('quantity'), issued_at__lt=limite)
                    .select_related('employee', 'stock__article', 'tool__article')
                    .order_by('issued_at', 'pk')[:200])
        filas = []
        for issue in entregas:
            articulo = issue.stock.article if issue.stock_id else issue.tool.article
            venc = fecha_limite(issue)
            filas.append([issue.employee.employee_id,
                          f'{issue.employee.first_name} {issue.employee.last_name}',
                          articulo.name, str(issue.quantity - issue.returned_quantity),
                          timezone.localtime(venc).strftime('%d/%m/%Y') if venc else '—'])
        # Préstamos antiguos aún no migrados a entregas unificadas.
        antiguos = (Loan.objects.filter(returned_at__isnull=True,
                   unified_issue__isnull=True, borrowed_at__lt=limite)
                   .select_related('employee', 'tool__article')
                   .order_by('borrowed_at', 'pk')[:200])
        for loan in antiguos:
            nombre = loan.tool.article.name if loan.tool.article_id else loan.tool.tool_code
            filas.append([loan.employee.employee_id,
                          f'{loan.employee.first_name} {loan.employee.last_name}',
                          nombre, '1', timezone.localtime(loan.borrowed_at + timedelta(days=15)).strftime('%d/%m/%Y')])
        return ['Nº empleado', 'Trabajador', 'Artículo', 'Pendiente', 'Venció'], filas[:200], 'Situación actual; antigüedad superior a 15 días. Incluye préstamos antiguos no unificados.'

    existencias = (QuantityStock.objects.filter(article__is_active=True,
                   article__minimum_stock__gt=0,
                   available_quantity__lt=F('article__minimum_stock'))
                   .select_related('article').order_by('article__name')[:200])
    return ['Código', 'Artículo', 'Disponible', 'Mínimo', 'Ubicación'], [
        [s.article.article_code, s.article.name, str(s.available_quantity),
         str(s.article.minimum_stock), s.article.location or 'Sin ubicación']
        for s in existencias
    ], 'Situación actual. Solo artículos controlados por cantidad.'


def _pdf(tipo, periodo, desde, hasta, user):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

    columnas, registros, nota = _contenido(tipo, periodo, desde, hasta)
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=16*mm, rightMargin=16*mm,
                            topMargin=16*mm, bottomMargin=16*mm)
    styles = getSampleStyleSheet()
    small = ParagraphStyle('filas', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=11)
    title_style = ParagraphStyle('titulo_reporte', parent=styles['Heading1'],
                                 textColor=colors.HexColor('#0f7a18'), fontSize=17, leading=22)
    note_style = ParagraphStyle('nota_reporte', parent=styles['Normal'], fontSize=9, leading=13)
    story = [Paragraph('ENGRANES Y RECTIFICADOS', title_style),
             Paragraph(escape(REPORTES[tipo]), styles['Heading2']),
             Paragraph(f"Generado: {timezone.localtime().strftime('%d/%m/%Y %H:%M')} | Responsable: {escape(user.get_username())}", small)]
    if tipo in ('auditoria', 'desechos'):
        periodo_txt = (f'Desde {desde or "inicio"} hasta {hasta or "hoy"}' if desde or hasta else
                       ('Histórico completo' if periodo == 'todo' else f'Últimos {PERIODOS[periodo]} días'))
        story.append(Paragraph(escape(periodo_txt), small))
    story.extend([Spacer(1, 9*mm), Paragraph(escape(nota), note_style), Spacer(1, 5*mm)])
    data = [[Paragraph(escape(str(c)), small) for c in columnas]]
    for registro in registros:
        data.append([Paragraph(escape(str(c or '')), small) for c in registro])
    if not registros:
        data.append([Paragraph('No hay registros para esta consulta.', small)] + [Paragraph('', small)]*(len(columnas)-1))
    total_width = 265*mm
    widths = [total_width / len(columnas)]*len(columnas)
    table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#e8f3e9')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#0f6419')),
        ('GRID', (0,0), (-1,-1), 0.3, colors.HexColor('#d9e4da')),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f7faf8')]),
        ('LEFTPADDING', (0,0), (-1,-1), 6), ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6), ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


@never_cache
@login_required(login_url='acceso_jefe')
@require_GET
def reportes_jefe(request):
    if not es_jefe(request.user):
        raise PermissionDenied('Solo jefatura puede consultar los reportes.')
    return render(request, 'stockroom/jefe/reportes.html', {'tipos': REPORTES})


@never_cache
@login_required(login_url='acceso_jefe')
@require_GET
def descargar_reporte_jefe(request):
    if not es_jefe(request.user):
        raise PermissionDenied('Solo jefatura puede descargar reportes.')
    try:
        params = _params(request)
    except ValueError:
        return HttpResponseBadRequest(
            "La fecha proporcionada no es válida."
        )
    if params is None:
        return HttpResponseBadRequest('Tipo de reporte, período o fechas inválidas.')
    tipo, periodo, raw_desde, raw_hasta = params
    desde, hasta = _limites(periodo, raw_desde, raw_hasta)
    pdf = _pdf(tipo, periodo, desde, hasta, request.user)
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="stockroom_jefe_{tipo}.pdf"'
    response['Cache-Control'] = 'no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    return response
