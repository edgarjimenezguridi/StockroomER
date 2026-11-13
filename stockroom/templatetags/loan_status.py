from datetime import timedelta

from django import template
from django.db.models import F, Q
from django.utils import timezone

from stockroom.models import DuplicateLoanAuthorization, Loan, QuantityIssue
from stockroom.loan_rules import PLAZO_PRESTAMO_DIAS

register = template.Library()


def _overdue_items(employee_id=None, max_rows=12):
    now = timezone.now()
    cutoff = now - timedelta(days=PLAZO_PRESTAMO_DIAS)
    issues = QuantityIssue.objects.filter(
        requires_return=True,
        returned_quantity__lt=F('quantity'),
        issued_at__lt=cutoff,
    ).select_related('employee', 'tool__article', 'stock__article')
    legacy = Loan.objects.filter(
        returned_at__isnull=True,
        unified_issue__isnull=True,
        borrowed_at__lt=cutoff,
    ).select_related('employee', 'tool__article')
    if employee_id is not None:
        issues = issues.filter(employee_id=employee_id)
        legacy = legacy.filter(employee_id=employee_id)
    overdue_employees = set(issues.values_list('employee_id', flat=True)) | set(
        legacy.values_list('employee_id', flat=True)
    )
    rows = []
    for issue in issues.order_by('issued_at', 'pk')[:max_rows]:
        article = issue.tool.article if issue.tool_id else issue.stock.article
        deadline = issue.issued_at + timedelta(days=PLAZO_PRESTAMO_DIAS)
        rows.append({
            'worker': issue.employee,
            'article': article,
            'quantity': issue.quantity - issue.returned_quantity,
            'deadline': deadline,
            'late_days': max(0, (now.date() - timezone.localtime(deadline).date()).days),
            'kind': 'Entrega',
        })
    if len(rows) < max_rows:
        for loan in legacy.order_by('borrowed_at', 'pk')[:max_rows - len(rows)]:
            deadline = loan.borrowed_at + timedelta(days=PLAZO_PRESTAMO_DIAS)
            rows.append({
                'worker': loan.employee,
                'article': loan.tool.article,
                'quantity': 1,
                'deadline': deadline,
                'late_days': max(0, (now.date() - timezone.localtime(deadline).date()).days),
                'kind': 'Préstamo anterior',
            })
    rows.sort(key=lambda x: x['deadline'])
    return rows, len(overdue_employees)


@register.inclusion_tag('stockroom/shared/loan_alerts.html', takes_context=True)
def mostrar_alertas_prestamos(context, mode):
    if mode not in ('worker', 'boss', 'warehouse'):
        return {'mode': 'invalid'}
    if mode == 'worker':
        employee = context.get('employee')
        if employee is None:
            return {'mode': 'invalid'}
        rows, count = _overdue_items(employee.pk)
        approvals = DuplicateLoanAuthorization.objects.filter(
            employee_id=employee.pk,
        ).select_related('article').order_by('-created_at', '-pk')[:8]
        pending = QuantityIssue.objects.filter(
            employee_id=employee.pk,
            requires_return=True,
            returned_quantity__lt=F('quantity'),
        ).select_related('tool__article', 'stock__article').order_by('issued_at', 'pk')[:30]
        upcoming = []
        now = timezone.now()
        for issue in pending:
            deadline = issue.issued_at + timedelta(days=PLAZO_PRESTAMO_DIAS)
            remaining = deadline - now
            if remaining.total_seconds() >= 0 and remaining <= timedelta(days=3):
                upcoming.append({'issue': issue, 'deadline': deadline})
        return {
            'mode': 'worker', 'overdue_rows': rows, 'blocked': bool(count),
            'approvals': approvals, 'upcoming': upcoming,
        }
    rows, count = _overdue_items()
    return {'mode': mode, 'overdue_rows': rows, 'overdue_workers': count}
