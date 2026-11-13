"""Diagnostico de solo lectura para preparar acceso movil a StockroomER.

Ejecutar desde la raiz del proyecto: python scripts/verificar_preparacion_movil.py
No modifica la base de datos ni los archivos del proyecto.
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    import django
    django.setup()
    from django.conf import settings
    from django.core.checks import run_checks
    from django.urls import reverse, resolve, NoReverseMatch
    from django.contrib.auth.models import Group
    from django.db import connection
except Exception as exc:
    print('No se pudo cargar Django:', type(exc).__name__, str(exc))
    print('Ejecuta este script desde la raiz de StockroomER con el entorno virtual activo.')
    raise SystemExit(2)

print('=' * 65)
print('STOCKROOMER - DIAGNOSTICO DE PREPARACION MOVIL (SOLO LECTURA)')
print('=' * 65)

warnings = []
errors = []

def status(label, ok, detail='', *, critical=False):
    tag = 'OK' if ok else ('ERROR' if critical else 'REVISAR')
    print(f'[{tag}] {label}' + (f': {detail}' if detail else ''))
    if not ok:
        (errors if critical else warnings).append(label + (': ' + detail if detail else ''))

print('\n1. CONFIGURACION')
status('DEBUG desactivado para produccion', not settings.DEBUG,
       'DEBUG=True es aceptable solo en pruebas locales; nunca en Internet')
hosts = list(getattr(settings, 'ALLOWED_HOSTS', []))
status('ALLOWED_HOSTS definido', bool(hosts) and '*' not in hosts,
       'Configurar nombres o IP autorizados, sin comodin *')
status('HTTPS obligatorio (produccion)', bool(getattr(settings, 'SECURE_SSL_REDIRECT', False)),
       'En pruebas locales no se requiere HTTPS; en produccion si')
status('Cookie de sesion segura (produccion)', bool(getattr(settings, 'SESSION_COOKIE_SECURE', False)),
       'Activar cuando el servidor tenga HTTPS')
status('Cookie CSRF segura (produccion)', bool(getattr(settings, 'CSRF_COOKIE_SECURE', False)),
       'Activar cuando el servidor tenga HTTPS')
status('Middleware de seguridad', 'django.middleware.security.SecurityMiddleware' in settings.MIDDLEWARE)
status('Proteccion CSRF activa', 'django.middleware.csrf.CsrfViewMiddleware' in settings.MIDDLEWARE)

print('\n2. RUTAS Y CONTROL DE ACCESO')
paths = {
    'Acceso del jefe': ('acceso_jefe', None),
    'Panel del jefe': ('panel_jefe', None),
    'Personal y permisos': ('personal_jefe', '/jefe/personal/'),
    'Auditoria': ('auditoria_jefe', '/jefe/auditoria/'),
    'Reportes ejecutivos': ('reportes_jefe', '/jefe/reportes/'),
    'Acceso de trabajadores': ('acceso_empleado', None),
    'Panel de trabajadores': ('panel_empleado', None),
    'Panel del almacenista': ('panel_almacen', None),
}
for label, (name, known_path) in paths.items():
    try:
        if known_path:
            matched = resolve(known_path)
            path = known_path
        else:
            path = reverse(name)
            matched = resolve(path)
        status(label, True, f'{path} (vista: {matched.url_name})')
    except Exception as exc:
        # Los nombres pueden variar entre instalaciones. Informamos sin alterar nada.
        status(label, False, f'No se pudo resolver automaticamente ({type(exc).__name__})')

print('\n3. RECURSOS VISUALES')
templates = [
    ('Login del jefe', 'stockroom/templates/stockroom/jefe/acceso.html'),
    ('Panel del jefe', 'stockroom/templates/stockroom/jefe/panel_jefe.html'),
    ('CSS corporativo', 'stockroom/static/stockroom/css/empresa.css'),
]
for label, rel in templates:
    found = (ROOT / rel).is_file()
    status(label, found, rel)

print('\n4. COMPROBACIONES DJANGO')
checks = run_checks()
critical = [item for item in checks if item.is_serious()]
status('Django system checks', not critical,
       f'{len(checks)} observaciones, {len(critical)} criticas', critical=True)
for issue in checks[:12]:
    print('  ', issue.id, issue.msg[:180])

print('\n5. RESUMEN')
print(f'Errores criticos: {len(errors)} | Elementos por revisar: {len(warnings)}')
if settings.DEBUG:
    print('ESTADO: SERVIDOR DE DESARROLLO. NO EXPONER A INTERNET.')
else:
    print('ESTADO: Configuracion DEBUG desactivada; verificar despliegue, HTTPS y autenticacion antes de publicar.')
print('Se realizo un diagnostico de solo lectura. No se modificaron datos ni configuracion.')
if errors:
    raise SystemExit(1)
