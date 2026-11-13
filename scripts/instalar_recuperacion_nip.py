"""Instala recuperación segura de NIP. Ejecutar desde la raíz de StockroomER."""
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / 'stockroom/models.py'
URLS = ROOT / 'config/urls.py'
ACCESS = ROOT / 'stockroom/templates/stockroom/empleados/acceso_empleado.html'
PERSONNEL = ROOT / 'stockroom/templates/stockroom/jefe/personal.html'
MIGRATION = ROOT / 'stockroom/migrations/0036_pinresetauthorization.py'
required = [MODELS, URLS, ACCESS, PERSONNEL, MIGRATION,
            ROOT / 'stockroom/pin_reset_views.py',
            ROOT / 'stockroom/templates/stockroom/credenciales/recuperar_nip.html',
            ROOT / 'stockroom/templates/stockroom/jefe/restablecer_nip.html',
            ROOT / 'stockroom/tests/test_recuperacion_nip.py']
missing = [str(p) for p in required if not p.is_file()]
if missing:
    raise SystemExit('Faltan archivos. No se aplicó ningún cambio:\n' + '\n'.join(missing))

changes = {}
models = MODELS.read_text(encoding='utf-8-sig')
model_code = '''\n\nclass PinResetAuthorization(models.Model):
    """Autorización auditada para restablecer un NIP: no almacena el código en claro."""
    credential = models.ForeignKey(
        "EmployeeCredential", on_delete=models.PROTECT, related_name="pin_resets"
    )
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="authorized_pin_resets"
    )
    code_digest = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["-created_at", "-pk"]
'''
if 'class PinResetAuthorization(' not in models:
    if 'from django.db import models' not in models or 'from django.conf import settings' not in models:
        raise SystemExit('models.py no tiene las importaciones esperadas; se canceló todo.')
    models += model_code
changes[MODELS] = models

urls = URLS.read_text(encoding='utf-8-sig')
import_line = 'from stockroom.pin_reset_views import autorizar_reset_nip_jefe, recuperar_nip_trabajador\n'
route_lines = '''    path("trabajadores/recuperar-nip/", recuperar_nip_trabajador, name="recuperar_nip_trabajador"),
    path("jefe/personal/<int:employee_id>/restablecer-nip/", autorizar_reset_nip_jefe, name="autorizar_reset_nip_jefe"),
'''
if 'name="recuperar_nip_trabajador"' not in urls:
    if 'urlpatterns = [' not in urls or 'from django.urls import path' not in urls:
        raise SystemExit('No se encontraron los puntos de inserción de urls.py; no se aplicó nada.')
    urls = urls.replace('urlpatterns = [', import_line + '\nurlpatterns = [\n' + route_lines, 1)
changes[URLS] = urls

access = ACCESS.read_text(encoding='utf-8-sig')
forgot_link = '''<p style="margin:14px 0"><a href="{% url 'recuperar_nip_trabajador' %}">Olvidé mi NIP</a></p>'''
if forgot_link not in access:
    anchor = '{{ pin_form.as_p }}'
    if anchor not in access:
        raise SystemExit('No se encontró el formulario NIP en acceso_empleado.html; se canceló todo.')
    access = access.replace(anchor, anchor + '\n' + forgot_link, 1)
changes[ACCESS] = access

personnel = PERSONNEL.read_text(encoding='utf-8-sig')
boss_link = '''{% if e.is_active %}<a class="persona-button alt" href="{% url 'autorizar_reset_nip_jefe' e.pk %}">Restablecer NIP</a>{% endif %}'''
if boss_link not in personnel:
    anchor = '<a class="persona-button alt" href="{% url \'expediente_trabajador_jefe\' e.pk %}">Expediente</a>'
    if anchor not in personnel:
        raise SystemExit('No se encontró Expediente en personal.html; se canceló todo.')
    personnel = personnel.replace(anchor, anchor + '\n    ' + boss_link, 1)
changes[PERSONNEL] = personnel

modified = [(p, content) for p, content in changes.items() if p.read_text(encoding='utf-8-sig') != content]
if not modified:
    print('Fase 10 ya instalada. No hubo cambios.')
    raise SystemExit(0)

backup = ROOT / ('backup_recuperacion_nip_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir()
for p, content in modified:
    target = backup / p.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, target)
for p, content in modified:
    p.write_text(content, encoding='utf-8')
print('Fase 10 instalada. Respaldo de archivos:', backup)
print('Ejecuta: python manage.py makemigrations --check --dry-run')
print('Luego: python manage.py migrate')
