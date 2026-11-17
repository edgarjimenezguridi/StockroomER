"""Instalador de Fase 18. Ejecutar desde la raíz de StockroomER. No migra ni edita datos."""
from pathlib import Path
from datetime import datetime
import shutil
import sys

ROOT = Path.cwd()
SRC = Path(__file__).resolve().parent.parent
paths = [
    'stockroom/employee_offboarding_views.py',
    'stockroom/templates/stockroom/almacen/baja_trabajador.html',
    'stockroom/templates/stockroom/jefe/solicitudes_baja.html',
    'stockroom/tests/test_baja_trabajadores.py',
]
model_path = ROOT / 'stockroom/models.py'
urls_path = ROOT / 'config/urls.py'
admin_path = ROOT / 'stockroom/admin.py'
if not all((ROOT / f).is_file() for f in ['manage.py', 'config/urls.py', 'stockroom/models.py', 'stockroom/employee_offboarding_views.py']):
    sys.exit('ERROR: ejecuta desde la raíz de StockroomER con la Fase 17 instalada.')
if not all((SRC / p).is_file() for p in paths):
    sys.exit('ERROR: descomprime el paquete completo conservando carpetas.')
model_text = model_path.read_text(encoding='utf-8-sig')
url_text = urls_path.read_text(encoding='utf-8-sig')
if 'class EmployeeOffboardingRequest(' not in model_text:
    model_text += '''\n\n# Fase 18: trazabilidad de solicitudes de baja de trabajadores\nclass EmployeeOffboardingRequest(models.Model):\n    class Status(models.TextChoices):\n        PENDING = "pending", "Pendiente"\n        APPROVED = "approved", "Aprobada"\n        REJECTED = "rejected", "Rechazada"\n\n    employee = models.ForeignKey("Employee", on_delete=models.PROTECT, related_name="offboarding_requests")\n    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="requested_employee_offboardings")\n    requested_at = models.DateTimeField(default=timezone.now)\n    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)\n    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="decided_employee_offboardings", null=True, blank=True)\n    decided_at = models.DateTimeField(null=True, blank=True)\n\n    class Meta:\n        ordering = ["-requested_at", "-pk"]\n        constraints = [\n            models.UniqueConstraint(fields=["employee"], condition=models.Q(status="pending"), name="unique_pending_employee_offboarding"),\n        ]\n\n    def __str__(self):\n        return f"Baja #{self.pk} - {self.employee}"\n'''
    # Robust import: no assumption that settings already imported elsewhere in models.py.
    model_text = 'from django.conf import settings\n' + model_text if 'from django.conf import settings' not in model_text else model_text
    # Respect future imports if present by inserting after them.
    if model_text.startswith('from django.conf import settings\nfrom __future__ import'):
        model_text = model_text.replace('from django.conf import settings\nfrom __future__ import', 'from __future__ import', 1)
        i = model_text.find('\n', model_text.find('from __future__ import'))
        model_text = model_text[:i+1] + 'from django.conf import settings\n' + model_text[i+1:]
if 'name="solicitudes_baja_jefe"' not in url_text and "name='solicitudes_baja_jefe'" not in url_text:
    url_text += '''\n# Fase 18: revisión final del jefe\nfrom stockroom.employee_offboarding_views import solicitudes_baja_jefe\nurlpatterns += [\n    path("jefe/solicitudes-baja/", solicitudes_baja_jefe, name="solicitudes_baja_jefe"),\n]\n'''
compile(model_text, str(model_path), 'exec')
compile(url_text, str(urls_path), 'exec')
for p in paths:
    if p.endswith('.py'):
        compile((SRC / p).read_text(encoding='utf-8'), p, 'exec')

# Localiza automáticamente el panel de jefe sin asumir su nombre de archivo.
boss_panels = list((ROOT / 'stockroom/templates').rglob('*jefe*.html'))
selected = None
for p in boss_panels:
    if 'panel' in p.name.lower() and '</main>' in p.read_text(encoding='utf-8-sig'):
        selected = p
        break
backup = ROOT / 'backups' / ('fase18_autorizacion_bajas_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(parents=True, exist_ok=True)
for p in [model_path, urls_path, admin_path] + [ROOT / x for x in paths] + ([selected] if selected else []):
    if p.is_file():
        target = backup / p.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
for x in paths:
    dest = ROOT / x
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC / x, dest)
model_path.write_text(model_text, encoding='utf-8')
urls_path.write_text(url_text, encoding='utf-8')
# Evita la desactivación manual desde el formulario estándar del admin.
# La autorización final se realiza solamente en la bandeja del jefe.
if admin_path.is_file():
    admin_text = admin_path.read_text(encoding='utf-8-sig')
    marker = '# Fase 18: bloquear edición manual de is_active de Employee en admin'
    if marker not in admin_text:
        admin_text += """

# Fase 18: bloquear edición manual de is_active de Employee en admin
from django.contrib import admin as _offboarding_admin
from .models import Employee as _OffboardingEmployee
_offboarding_registered_admin = _offboarding_admin.site._registry.get(_OffboardingEmployee)
if _offboarding_registered_admin is not None:
    _offboarding_registered_admin.readonly_fields = tuple(
        dict.fromkeys(tuple(_offboarding_registered_admin.readonly_fields) + ("is_active",))
    )
"""
        compile(admin_text, str(admin_path), 'exec')
        admin_path.write_text(admin_text, encoding='utf-8')
if selected:
    markup = selected.read_text(encoding='utf-8-sig')
    if "solicitudes_baja_jefe" not in markup:
        markup = markup.replace('</main>', '<div style="max-width:1100px;margin:18px auto"><a class="accion-almacen" href="{% url \'solicitudes_baja_jefe\' %}">Solicitudes de baja de trabajadores</a></div>\n</main>', 1)
        selected.write_text(markup, encoding='utf-8')
print('OK: Fase 18 instalada en código. Ningún empleado fue desactivado y no se modificó inventario.')
print('Respaldo:', backup)
print('Panel del jefe enlazado:', selected if selected else 'No se encontró panel apto; usar ruta /jefe/solicitudes-baja/')
print('IMPORTANTE: Ejecuta python manage.py makemigrations stockroom y python manage.py migrate.')
print('Luego: python manage.py check; python manage.py test stockroom.tests')
