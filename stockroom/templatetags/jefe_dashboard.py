"""Indicadores de dirección: solamente lectura. No altera inventario."""
from datetime import timedelta
from django import template
from django.db.models import F, Q, Sum
from django.utils import timezone
from stockroom.models import (
    Article, DamageResolution, DuplicateLoanAuthorization, Employee,
    QuantityIssue, QuantityStock,
)

register = template.Library()

PERIODOS = {'7': 7, '30': 30, '90': 90, 'todo': None}


def indicadores_jefe(periodo='30'):
    """Las bajas se atribuyen al empleado de la entrega original.

    El porcentaje usa resoluciones del mismo período (bajas / total resuelto),
    NO total de herramientas entregadas ni culpabilidad demostrada.
    """
    periodo = periodo if periodo in PERIODOS else '30'
    limite = timezone.now() - timedelta(days=PERIODOS[periodo]) if PERIODOS[periodo] else None
    resoluciones = DamageResolution.objects.filter(
        source_return__condition='damaged',
    )
    if limite:
        resoluciones = resoluciones.filter(resolved_at__gte=limite)

    filas = list(
        resoluciones.values(
            'source_return__issue__employee_id',
            'source_return__issue__employee__employee_id',
            'source_return__issue__employee__first_name',
            'source_return__issue__employee__last_name',
        ).annotate(
            desechadas=Sum('quantity', filter=Q(outcome=DamageResolution.Outcome.SCRAPPED)),
            recuperadas=Sum('quantity', filter=Q(outcome=DamageResolution.Outcome.RESTORED)),
        )
    )
    datos = []
    for fila in filas:
        desechadas = fila['desechadas'] or 0
        recuperadas = fila['recuperadas'] or 0
        total = desechadas + recuperadas
        datos.append({
            'nombre': '{} {}'.format(
                fila['source_return__issue__employee__first_name'],
                fila['source_return__issue__employee__last_name'],
            ).strip(),
            'numero': fila['source_return__issue__employee__employee_id'],
            'desechadas': desechadas,
            'recuperadas': recuperadas,
            'total': total,
            'porcentaje': round(100 * desechadas / total, 1) if total else 0,
        })
    datos.sort(key=lambda d: (-d['desechadas'], d['nombre']))
    maximo = max((d['desechadas'] for d in datos), default=0)
    for dato in datos:
        dato['ancho'] = round(100 * dato['desechadas'] / maximo, 1) if maximo else 0

    bajas = sum(d['desechadas'] for d in datos)
    restauradas = sum(d['recuperadas'] for d in datos)
    pendientes = DuplicateLoanAuthorization.objects.filter(
        status=DuplicateLoanAuthorization.Status.PENDING,
    ).count()
    vencimiento = timezone.now() - timedelta(days=15)
    vencidos = QuantityIssue.objects.filter(
        requires_return=True, returned_quantity__lt=F('quantity'),
        issued_at__lt=vencimiento,
    ).values('employee_id').distinct().count()
    bajo_minimo = QuantityStock.objects.filter(
        article__is_active=True, article__minimum_stock__gt=0,
        available_quantity__lt=F('article__minimum_stock'),
    ).count()
    return {
        'periodo': periodo,
        'personal_activo': Employee.objects.filter(is_active=True).count(),
        'articulos_activos': Article.objects.filter(is_active=True).count(),
        'autorizaciones_pendientes': pendientes,
        'trabajadores_vencidos_dashboard': vencidos,
        'bajo_minimo': bajo_minimo,
        'bajas_total': bajas,
        'recuperadas_total': restauradas,
        'filas_desechos': datos,
        'tasa_baja': round(100 * bajas / (bajas + restauradas), 1) if bajas + restauradas else 0,
    }


@register.inclusion_tag('stockroom/jefe/dashboard_ejecutivo.html', takes_context=True)
def dashboard_ejecutivo(context):
    request = context.get('request')
    periodo = request.GET.get('periodo', '30') if request else '30'
    return indicadores_jefe(periodo)
