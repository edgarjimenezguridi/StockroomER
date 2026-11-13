"""Instalación idempotente: valida archivos, respalda, añade rutas y enlace."""
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
URLS = ROOT / 'config/urls.py'
PANEL = ROOT / 'stockroom/templates/stockroom/jefe/panel_jefe.html'
NEEDED = [
    ROOT / 'stockroom/boss_personnel_views.py',
    ROOT / 'stockroom/templates/stockroom/jefe/personal.html',
    ROOT / 'stockroom/templates/stockroom/jefe/expediente.html',
    ROOT / 'stockroom/tests/test_personal_jefe.py',
    URLS, PANEL,
]
missing = [str(p) for p in NEEDED if not p.is_file()]
if missing:
    raise SystemExit('Faltan archivos, no se modificó nada:\n' + '\n'.join(missing))
urls = URLS.read_text(encoding='utf-8-sig')
panel = PANEL.read_text(encoding='utf-8-sig')
if 'urlpatterns = [' not in urls or '{% block contenido %}' not in panel:
    raise SystemExit('Estructura inesperada; no se modificó nada.')
if 'name="acceso_jefe"' not in urls and "name='acceso_jefe'" not in urls:
    raise SystemExit('Falta la ruta acceso_jefe. Instala primero el inicio de sesión independiente del jefe.')
if 'personal_jefe' not in urls:
    imports = '''from stockroom.boss_personnel_views import (
    personal_jefe, estado_trabajador_jefe,
    expediente_trabajador_jefe, estado_cuenta_jefe,
)

'''
    routes = '''    path("jefe/personal/", personal_jefe, name="personal_jefe"),
    path("jefe/personal/<int:employee_id>/estado/", estado_trabajador_jefe, name="estado_trabajador_jefe"),
    path("jefe/personal/<int:employee_id>/expediente/", expediente_trabajador_jefe, name="expediente_trabajador_jefe"),
    path("jefe/cuentas/<int:user_id>/estado/", estado_cuenta_jefe, name="estado_cuenta_jefe"),
'''
    urls = urls.replace('urlpatterns = [', imports + 'urlpatterns = [\n' + routes, 1)
nav = '<div class="jefe-nav"><a href="{% url \'personal_jefe\' %}" style="display:inline-block;background:#0f7a18;color:white;padding:12px 18px;border-radius:10px;text-decoration:none;font-weight:700;margin:12px 0;">👥 Personal y permisos</a></div>'
if "{% url 'personal_jefe' %}" not in panel:
    panel = panel.replace('{% block contenido %}', '{% block contenido %}\n' + nav, 1)
changes = []
for path, text in ((URLS, urls), (PANEL, panel)):
    original = path.read_text(encoding='utf-8-sig')
    if text != original:
        changes.append((path, text))
if not changes:
    print('El módulo ya está instalado; no se modificó nada.')
    raise SystemExit(0)
backups = []
for path, text in changes:
    backup = path.with_name(path.name + '.bak_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    shutil.copy2(path, backup)
    backups.append(backup)
for path, text in changes:
    path.write_text(text, encoding='utf-8')
print('Personal y permisos instalado. Archivos respaldados:')
for backup in backups:
    print(' -', backup)
print('No se modificaron modelos ni se ejecutaron migraciones.')
