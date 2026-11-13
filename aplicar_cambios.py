"""Aplica cambios de autorizaciones al repo StockroomER. No toca la DB.
Ejecutar desde raiz con: python aplicar_cambios.py
"""
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path.cwd()
S = ROOT / 'stockroom'
expected = ['models.py', 'admin.py', 'loan_rules.py', 'cart.py', 'fulfillment.py']
if not (S / 'tests').is_dir():
    raise SystemExit('No se encontró stockroom/tests.')
if (S / 'tests' / 'test_duplicate_authorizations.py').exists():
    raise SystemExit('Ya existe el archivo test_duplicate_authorizations.py; no se sobrescribe.')
for n in expected:
    if not (S / n).is_file():
        raise SystemExit(f'No encuentro stockroom/{n}. Ejecuta desde raiz del proyecto.')

original = {n: (S / n).read_text(encoding='utf-8-sig') for n in expected}

def once(data, old, new, label):
    count = data.count(old)
    if count != 1:
        raise RuntimeError(f'Patrón inesperado {label}: coincidencias={count}. No se modificó ningún archivo.')
    return data.replace(old, new, 1)

model = '''\n\nclass DuplicateLoanAuthorization(models.Model):
    """Excepción puntual del jefe para solicitar un artículo repetido."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        APPROVED = "approved", "Aprobada"
        REJECTED = "rejected", "Rechazada"

    employee = models.ForeignKey(
        Employee, on_delete=models.PROTECT,
        related_name="duplicate_authorizations", verbose_name="Trabajador",
    )
    article = models.ForeignKey(
        Article, on_delete=models.PROTECT,
        related_name="duplicate_authorizations", verbose_name="Artículo",
    )
    max_quantity = models.PositiveIntegerField(
        "Cantidad máxima autorizada", validators=[MinValueValidator(1)]
    )
    reason = models.TextField("Motivo de la excepción")
    status = models.CharField(
        "Estado", max_length=12, choices=Status.choices,
        default=Status.PENDING, editable=False,
    )
    created_at = models.DateTimeField("Solicitada el", auto_now_add=True)
    decided_at = models.DateTimeField("Resuelta el", null=True, blank=True, editable=False)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="duplicate_authorizations_decided",
        null=True, blank=True, editable=False,
        verbose_name="Autorizada o rechazada por",
    )
    used_request = models.ForeignKey(
        MaterialRequest, on_delete=models.PROTECT,
        related_name="duplicate_authorizations_used",
        null=True, blank=True, editable=False,
        verbose_name="Solicitud que utilizó la autorización",
    )

    class Meta:
        verbose_name = "Autorización de préstamo duplicado"
        verbose_name_plural = "Autorizaciones de préstamos duplicados"
        ordering = ["-created_at", "-pk"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(max_quantity__gte=1),
                name="duplicate_authorization_quantity_positive",
            ),
            models.UniqueConstraint(
                fields=["used_request", "article"],
                condition=models.Q(used_request__isnull=False),
                name="one_duplicate_authorization_per_line",
            ),
        ]

    def __str__(self):
        return f"{self.employee.employee_id} / {self.article.article_code} / {self.get_status_display()}"
'''

if 'class DuplicateLoanAuthorization(' in original['models.py']:
    raise RuntimeError('El modelo ya existe: no ejecutar dos veces.')
original['models.py'] += model

rules = original['loan_rules.py']
needle = 'from .models import Article, Loan, MaterialRequest, MaterialRequestLine, QuantityIssue'
rules = once(rules, needle,
    'from .models import Article, Loan, MaterialRequest, MaterialRequestLine, QuantityIssue, DuplicateLoanAuthorization', 'import reglas')

start = rules.index('def validar_sin_duplicado(')
end = rules.index('\ndef fecha_limite(', start)
rules = rules[:start] + '''def autorizacion_aprobada(*, employee_id, article_id, quantity, request_id=None):
    """Busca una autorización libre o ya vinculada a esta solicitud.

    No permite usar una autorización de otra solicitud o por más cantidad.
    """
    aprobadas = DuplicateLoanAuthorization.objects.filter(
        employee_id=employee_id,
        article_id=article_id,
        status=DuplicateLoanAuthorization.Status.APPROVED,
        max_quantity__gte=quantity,
    )
    if request_id is not None:
        vinculada = aprobadas.filter(used_request_id=request_id).first()
        if vinculada:
            return vinculada
    return aprobadas.filter(used_request__isnull=True).first()


def validar_sin_duplicado(
    *, employee_id, article_id, excluir_solicitud_id=None,
    quantity=1, require_bound=False,
):
    """Valida duplicidad; una autorización aprobada permite excepción puntual."""
    motivo = motivo_duplicado(
        employee_id=employee_id,
        article_id=article_id,
        excluir_solicitud_id=excluir_solicitud_id,
    )
    if not motivo:
        return None

    autorizacion = autorizacion_aprobada(
        employee_id=employee_id,
        article_id=article_id,
        quantity=quantity,
        request_id=excluir_solicitud_id,
    )
    if autorizacion is not None and (
        not require_bound or autorizacion.used_request_id == excluir_solicitud_id
    ):
        return autorizacion

    raise ValidationError(
        f"{motivo} Se requiere autorización aprobada del jefe para el duplicado."
    )


def vincular_autorizacion_si_necesaria(*, employee_id, article_id, quantity, request_id):
    """Reserva una aprobación una sola vez, dentro de la transacción del envío."""
    autorizacion = validar_sin_duplicado(
        employee_id=employee_id, article_id=article_id,
        excluir_solicitud_id=request_id, quantity=quantity,
    )
    if autorizacion is None:
        return None
    updated = DuplicateLoanAuthorization.objects.filter(
        pk=autorizacion.pk,
        status=DuplicateLoanAuthorization.Status.APPROVED,
        used_request__isnull=True,
    ).update(used_request_id=request_id)
    if updated != 1:
        # La misma autorización fue usada por otra comanda o invalidada.
        if autorizacion.used_request_id != request_id:
            raise ValidationError("La autorización ya fue utilizada o dejó de estar vigente.")
    return autorizacion

''' + rules[end:]
start = rules.index('def validar_articulo_solicitable(')
rules = rules[:start] + '''def validar_articulo_solicitable(
    *, employee_id, article_id, exclude_request_id=None,
    quantity=1, require_bound=False,
):
    """Control de adeudos y duplicados antes de la entrega."""
    validar_bloqueo_vencimiento(employee_id)
    return validar_sin_duplicado(
        employee_id=employee_id,
        article_id=article_id,
        excluir_solicitud_id=exclude_request_id,
        quantity=quantity,
        require_bound=require_bound,
    )
'''
rules += '''\n\n# Compatibilidad con las propiedades QuantityIssue.fecha_limite / estado_plazo.
def fecha_limite_prestamo(issue):
    return fecha_limite(issue)


def estado_plazo_prestamo(issue):
    return estado_prestamo(issue)
'''

original['loan_rules.py'] = rules

cart = original['cart.py']
cart = once(cart,
    '    validar_sin_duplicado,\n)',
    '    validar_sin_duplicado,\n    vincular_autorizacion_si_necesaria,\n)', 'import carrito')
cart = once(cart,
    '            excluir_solicitud_id=cart.pk,\n        )\n\n        if quantity > article.available_quantity:',
    '            excluir_solicitud_id=cart.pk,\n            quantity=quantity,\n        )\n\n        if quantity > article.available_quantity:', 'carrito cantidad')
cart = once(cart,
    '''        for article_id in lines.values_list(
            "article_id", flat=True
        ):
            validar_sin_duplicado(
                employee_id=employee_id,
                article_id=article_id,
                excluir_solicitud_id=cart.pk,
            )''',
    '''        for line in lines:
            vincular_autorizacion_si_necesaria(
                employee_id=employee_id,
                article_id=line.article_id,
                quantity=line.requested_quantity,
                request_id=cart.pk,
            )''', 'envío')
original['cart.py'] = cart

ful = original['fulfillment.py']
ful = once(ful,
    '''                    exclude_request_id=request_id,
                )''',
    '''                    exclude_request_id=request_id,
                    quantity=line.prepared_quantity,
                    require_bound=True,
                )''', 'entrega autorización')
original['fulfillment.py'] = ful

# admin registration added at end, separate module to avoid editing existing admin classes.
admin_import = '\n# Administración protegida de autorizaciones de duplicados.\nfrom . import duplicate_authorization_admin  # noqa: E402,F401\n'
if 'duplicate_authorization_admin' in original['admin.py']:
    raise RuntimeError('Admin de duplicados ya integrado.')
original['admin.py'] += admin_import

# Only after all validations succeeded, back up and write.
backup_dir = ROOT / ('backup_autorizaciones_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup_dir.mkdir(exist_ok=False)
for n in expected:
    shutil.copy2(S / n, backup_dir / n)
for n in expected:
    (S / n).write_text(original[n], encoding='utf-8')
shutil.copy2(Path(__file__).parent / 'duplicate_authorization_admin.py', S / 'duplicate_authorization_admin.py')
shutil.copy2(Path(__file__).parent / 'test_duplicate_authorizations.py', S / 'tests' / 'test_duplicate_authorizations.py')
print('Cambios aplicados. Respaldo en:', backup_dir.name)
print('No se modificó la base de datos.')
