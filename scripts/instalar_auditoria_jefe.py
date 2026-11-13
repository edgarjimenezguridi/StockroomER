"""Instalación conservadora de vista de auditoría. No toca inventario ni modelos."""
from datetime import datetime
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
URLS = ROOT / 'config/urls.py'
PERSONAL = ROOT / 'stockroom/templates/stockroom/jefe/personal.html'
ONBOARD = ROOT / 'stockroom/pin_onboarding_views.py'
REQUIRED = [URLS, PERSONAL, ONBOARD,
    ROOT / 'stockroom/boss_audit_views.py',
    ROOT / 'stockroom/templates/stockroom/jefe/auditoria.html',
    ROOT / 'stockroom/tests/test_auditoria_jefe.py']
missing = [str(p) for p in REQUIRED if not p.is_file()]
if missing:
    sys.exit('Faltan archivos. No se modificó nada:\n' + '\n'.join(missing))

changes = {}
urls = URLS.read_text(encoding='utf-8-sig')
if 'name="auditoria_jefe"' not in urls and "name='auditoria_jefe'" not in urls:
    if 'urlpatterns = [' not in urls:
        sys.exit('No se encontró urlpatterns. No se modificó nada.')
    urls = urls.replace('urlpatterns = [',
        'from stockroom.boss_audit_views import auditoria_jefe\n\nurlpatterns = [\n'
        '    path("jefe/auditoria/", auditoria_jefe, name="auditoria_jefe"),', 1)
changes[URLS] = urls

personal = PERSONAL.read_text(encoding='utf-8-sig')
link = '<a class="persona-button alt" href="{% url \'auditoria_jefe\' %}">Historial de administración</a>'
if link not in personal:
    anchor = '<div class="persona-main">'
    if anchor not in personal:
        sys.exit('personal.html no coincide. No se modificó nada.')
    personal = personal.replace(anchor, anchor + '\n  <p>' + link + '</p>', 1)
changes[PERSONAL] = personal

onboard = ONBOARD.read_text(encoding='utf-8-sig')
logging_import = 'from django.contrib.admin.models import LogEntry, CHANGE\n'
if logging_import not in onboard:
    anchor = 'from django import forms\n'
    if anchor not in onboard:
        sys.exit('pin_onboarding_views.py no coincide. No se modificó nada.')
    onboard = onboard.replace(anchor, anchor + logging_import, 1)
log_code = '''            # Registrar únicamente emisión y responsable: nunca guardar token ni NIP.
            LogEntry.objects.log_actions(
                user_id=request.user.pk,
                queryset=EmployeeCredential.objects.filter(pk=credential.pk),
                action_flag=CHANGE,
                change_message="Autorización inicial de NIP emitida",
            )
'''
if 'change_message="Autorización inicial de NIP emitida"' not in onboard:
    anchor = '            authorization = authorize_pin_setup(credential=credential, operator=request.user)\n'
    if anchor not in onboard:
        sys.exit('No se encontró el punto de auditoría NIP. No se modificó nada.')
    onboard = onboard.replace(anchor, anchor + log_code, 1)
changes[ONBOARD] = onboard

modified = [(p, s) for p, s in changes.items() if p.read_text(encoding='utf-8-sig') != s]
if not modified:
    print('Fase 12 ya instalada. Sin cambios.')
    sys.exit(0)
backup = ROOT / ('backup_auditoria_fase12_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(exist_ok=False)
for p, _ in modified:
    destination = backup / p.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, destination)
for p, content in modified:
    p.write_text(content, encoding='utf-8')
print('Fase 12 instalada correctamente.')
print('Respaldos:', backup)
print('Sin cambios en modelos, migraciones ni inventario.')
