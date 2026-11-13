"""Instalador conservador: valida marcas, respalda y aplica integración sin migraciones."""
from pathlib import Path
from datetime import datetime
import shutil

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ROOT / 'stockroom/views.py'
CREDS = ROOT / 'stockroom/credentials.py'
URLS = ROOT / 'config/urls.py'
PERSONAL = ROOT / 'stockroom/templates/stockroom/jefe/personal.html'
NEEDED = [
    VIEWS, CREDS, URLS, PERSONAL,
    ROOT / 'stockroom/pin_onboarding_views.py',
    ROOT / 'stockroom/templates/stockroom/credenciales/inicio_nip.html',
    ROOT / 'stockroom/templates/stockroom/jefe/autorizar_nip.html',
    ROOT / 'stockroom/tests/test_autoregistro_nip.py',
]
missing = [str(x) for x in NEEDED if not x.is_file()]
if missing:
    raise SystemExit('Faltan archivos. No se modificó nada:\n' + '\n'.join(missing))

changes = {}
view = VIEWS.read_text(encoding='utf-8-sig')
old = '''                elif not credential.pin_hash:
                    selected_form.add_error(
                        None, "Solicita al almacenista activar tu NIP."
                    )
                    credential = None'''
new = '''                elif not credential.pin_hash:
                    # Solo identifica al trabajador. NO permite crear el NIP
                    # sin la autorización temporal emitida por jefatura.
                    request.session["pin_setup_pending"] = signing.dumps(
                        {"barcode": str(credential.barcode)},
                        salt="stockroom.worker-pin-onboarding",
                    )
                    return redirect("inicio_nip_trabajador")'''
if old in view:
    view = view.replace(old, new, 1)
elif new not in view:
    raise SystemExit('views.py no coincide con la versión esperada. No se modificó nada.')

old_success = '''            request.session.pop("pin_setup_authorization", None)
            return HttpResponse("Tu NIP quedó activado.")'''
new_success = '''            request.session.pop("pin_setup_authorization", None)
            request.session.pop("pin_setup_pending", None)
            messages.success(request, "NIP registrado correctamente. Identifícate para ingresar.")
            return redirect("acceso_empleado")'''
if old_success in view:
    view = view.replace(old_success, new_success, 1)
elif new_success not in view:
    raise SystemExit('No se encontró el final de activar_nip. No se modificó nada.')
changes[VIEWS] = view

creds = CREDS.read_text(encoding='utf-8-sig')
old_role = '''        and operator.has_perm("stockroom.change_employeecredential")'''
new_role = '''        and (
            operator.is_superuser
            or operator.groups.filter(name="Jefes").exists()
            or operator.has_perm("stockroom.change_employeecredential")
        )'''
if old_role in creds:
    creds = creds.replace(old_role, new_role, 1)
elif new_role not in creds:
    raise SystemExit('credentials.py tiene otro control de permisos. No se modificó nada.')
changes[CREDS] = creds

urls = URLS.read_text(encoding='utf-8-sig')
route_import = 'from stockroom.pin_onboarding_views import inicio_nip_trabajador, autorizar_nip_jefe\n\n'
route_lines = '''    path("trabajadores/activar-mi-nip/", inicio_nip_trabajador, name="inicio_nip_trabajador"),
    path("jefe/personal/<int:employee_id>/autorizar-nip/", autorizar_nip_jefe, name="autorizar_nip_jefe"),
'''
if 'name="inicio_nip_trabajador"' not in urls and "name='inicio_nip_trabajador'" not in urls:
    if 'urlpatterns = [' not in urls:
        raise SystemExit('No se encontró urlpatterns en urls.py. No se modificó nada.')
    urls = urls.replace('urlpatterns = [', route_import + 'urlpatterns = [\n' + route_lines, 1)
changes[URLS] = urls

personal = PERSONAL.read_text(encoding='utf-8-sig')
button = '''{% if e.is_active %}<a class="persona-button alt" href="{% url 'autorizar_nip_jefe' e.pk %}">Activación NIP</a>{% endif %}'''
anchor = '<a class="persona-button alt" href="{% url \'expediente_trabajador_jefe\' e.pk %}">Expediente</a>'
if button not in personal:
    if anchor not in personal:
        raise SystemExit('No se encontró el enlace a Expediente en personal.html. No se modificó nada.')
    personal = personal.replace(anchor, anchor + '\n    ' + button, 1)
changes[PERSONAL] = personal

modified = [(p, content) for p, content in changes.items() if p.read_text(encoding='utf-8-sig') != content]
if not modified:
    print('La fase 9 ya está instalada. No hubo modificaciones.')
    raise SystemExit(0)

backup_dir = ROOT / ('backup_nip_fase9_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup_dir.mkdir(parents=True, exist_ok=False)
for p, content in modified:
    target = backup_dir / p.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(p, target)
for p, content in modified:
    p.write_text(content, encoding='utf-8')
print('Activación automática de NIP instalada.')
print('Respaldo:', backup_dir)
print('No se modificaron modelos ni inventario, y no se ejecutaron migraciones.')
