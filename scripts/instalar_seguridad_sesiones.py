"""Agrega validación de sesión del trabajador y actualiza fixtures de pruebas.

No modifica credenciales reales ni ejecuta migraciones.
"""
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ROOT / 'stockroom/views.py'
SETTINGS = ROOT / 'config/settings.py'
GUARD = ROOT / 'stockroom/worker_session_security.py'
TEST = ROOT / 'stockroom/tests/test_seguridad_sesiones_nip.py'
TEST4 = ROOT / 'stockroom/tests/test_worker_exceptions.py'
TEST5 = ROOT / 'stockroom/tests/test_integracion_autorizaciones.py'
required = [VIEWS, SETTINGS, GUARD, TEST]
missing = [str(p) for p in required if not p.is_file()]
if missing:
    raise SystemExit('Faltan archivos, sin cambios:\n' + '\n'.join(missing))

updates = {}
views = VIEWS.read_text(encoding='utf-8-sig')
anchor = '                    request.session["worker_credential_id"] = credential.pk'
addition = anchor + '\n                    request.session["worker_pin_version"] = pin_session_version(credential.pin_hash)'
if addition not in views:
    if views.count(anchor) != 1:
        raise SystemExit('No se encontró el único punto de autenticación en views.py. Sin cambios.')
    views = views.replace(anchor, addition, 1)
if 'from .worker_session_security import pin_session_version' not in views:
    views = 'from .worker_session_security import pin_session_version\n' + views
updates[VIEWS] = views

settings = SETTINGS.read_text(encoding='utf-8-sig')
needle = "'django.contrib.auth.middleware.AuthenticationMiddleware',"
needle2 = '"django.contrib.auth.middleware.AuthenticationMiddleware",'
line = '    "stockroom.worker_session_security.WorkerPinSessionMiddleware",'
if 'stockroom.worker_session_security.WorkerPinSessionMiddleware' not in settings:
    if needle2 in settings:
        settings = settings.replace(needle2, needle2 + '\n' + line, 1)
    elif needle in settings:
        settings = settings.replace(needle, needle + '\n' + line, 1)
    else:
        raise SystemExit('No se encontró AuthenticationMiddleware en settings.py. Sin cambios.')
updates[SETTINGS] = settings

# Las dos suites históricas creaban sesiones ficticias sin pasar por el login.
# Ahora deben incluir la nueva marca, al igual que hace el login real.
for file in (TEST4, TEST5):
    if not file.exists():
        continue
    source = file.read_text(encoding='utf-8-sig')
    if 'worker_pin_version' in source:
        continue
    if 'self.credential' not in source:
        raise SystemExit(f'No se pudo comprobar el fixture de {file}. Sin cambios.')
    injection = 'session["worker_pin_version"] = pin_session_version(self.credential.pin_hash)'
    import_line = 'from stockroom.worker_session_security import pin_session_version\n'
    if file == TEST4:
        anchor_test = "        session['worker_credential_id'] = self.credential.pk"
    else:
        anchor_test = '        session["worker_credential_id"] = self.credential.pk'
    if source.count(anchor_test) != 1:
        raise SystemExit(f'No se reconoció la sesión de prueba de {file}. Sin cambios.')
    source = import_line + source
    source = source.replace(anchor_test, anchor_test + '\n        ' + injection, 1)
    updates[file] = source

changed = [(p, s) for p,s in updates.items() if p.read_text(encoding='utf-8-sig') != s]
if not changed:
    print('Fase 11 ya instalada. Sin modificaciones.')
    raise SystemExit(0)

backup = ROOT / ('backup_sesiones_nip_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir()
for path, content in changed:
    destination = backup / path.relative_to(ROOT)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
for path, content in changed:
    path.write_text(content, encoding='utf-8')
print('Fase 11 instalada: sesiones vinculadas al NIP actual.')
print('Respaldo de archivos:', backup)
print('No se modificaron modelos ni inventario. No requiere migración.')
