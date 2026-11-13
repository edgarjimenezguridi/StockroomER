"""Inserta exclusivamente bloques de interfaz. Ejecutar desde la raíz del proyecto."""
from datetime import datetime
from pathlib import Path
import shutil

root = Path.cwd()
paths = {
    'worker': root / 'stockroom/templates/stockroom/empleados/panel_empleado.html',
    'boss': root / 'stockroom/templates/stockroom/jefe/panel_jefe.html',
    'warehouse': root / 'stockroom/templates/stockroom/almacen/panel_almacen.html',
}
anchors = {
    'worker': '<div class="layout">',
    'boss': '<section class="jefe-card">',
    'warehouse': '</main>',
}
block = {
    'worker': "{% mostrar_alertas_prestamos 'worker' %}",
    'boss': "{% mostrar_alertas_prestamos 'boss' %}",
    'warehouse': "{% mostrar_alertas_prestamos 'warehouse' %}",
}
tag = root / 'stockroom/templatetags/loan_status.py'
partial = root / 'stockroom/templates/stockroom/shared/loan_alerts.html'
for p in [tag, partial, *paths.values()]:
    if not p.is_file():
        raise SystemExit(f'Falta archivo: {p}. No se modificó nada.')
updates = {}
for role, path in paths.items():
    data = path.read_text(encoding='utf-8-sig')
    if block[role] in data:
        print(f'{role}: ya instalado; sin cambios.')
        continue
    if anchors[role] not in data:
        raise SystemExit(f'No encuentro el marcador en {path}; no se modificó nada.')
    if '{% load loan_status %}' not in data:
        if data.lstrip().startswith('{% extends '):
            lines = data.splitlines(keepends=True)
            lines.insert(1, '{% load loan_status %}\n')
            data = ''.join(lines)
        else:
            data = '{% load loan_status %}\n' + data
    # Antes del cierre del main en el panel del almacenista.
    if role == 'warehouse':
        data = data.replace(anchors[role], '    ' + block[role] + '\n' + anchors[role], 1)
    else:
        data = data.replace(anchors[role], block[role] + '\n' + anchors[role], 1)
    updates[path] = data
if not updates:
    print('Los tres paneles ya tienen las alertas. No se realizaron cambios.')
    raise SystemExit(0)
backup = root / ('backup_alertas_paneles_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir()
for path, data in updates.items():
    relative = path.relative_to(root)
    destination = backup / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, destination)
    path.write_text(data, encoding='utf-8')
    print('Actualizado:', relative)
print('Copias de seguridad:', backup)
print('No se modificaron modelos, rutas, permisos ni base de datos.')
