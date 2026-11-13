"""Inserta dashboard sin sobreescribir el panel existente; crea backup."""
from datetime import datetime
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / 'stockroom/templates/stockroom/jefe/panel_jefe.html'
if not PANEL.exists():
    raise SystemExit(f'No existe {PANEL}; no se modificó ningún archivo.')
original = PANEL.read_text(encoding='utf-8-sig')
if '{% dashboard_ejecutivo %}' in original:
    print('El dashboard ya estaba instalado; no se modificó el panel.')
    raise SystemExit(0)
if '{% block contenido %}' not in original:
    raise SystemExit('No se encontró el bloque contenido; no se modificó el panel.')
backup = PANEL.with_name(PANEL.name + '.bak_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
shutil.copy2(PANEL, backup)
modificado = original
if '{% load jefe_dashboard %}' not in modificado:
    lineas = modificado.splitlines(keepends=True)
    for pos, linea in enumerate(lineas):
        if '{% extends ' in linea:
            lineas.insert(pos + 1, '{% load jefe_dashboard %}\n')
            modificado = ''.join(lineas)
            break
    else:
        raise SystemExit('No se encontró extends; se dejó intacto el panel original.')
modificado = modificado.replace('{% block contenido %}', '{% block contenido %}\n{% dashboard_ejecutivo %}', 1)
PANEL.write_text(modificado, encoding='utf-8')
print('Dashboard añadido al panel del jefe.')
print('Respaldo:', backup)
print('Sin cambios en modelos, vistas, rutas, permisos ni inventario.')
