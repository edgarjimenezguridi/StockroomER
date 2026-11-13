"""Inserta ruta y enlace con copia previa. No altera datos ni modelos."""
from datetime import datetime
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
URLS = ROOT / 'config/urls.py'
PANEL = ROOT / 'stockroom/templates/stockroom/jefe/panel_jefe.html'
REQUIRED = [URLS, PANEL,
    ROOT / 'stockroom/boss_reports.py',
    ROOT / 'stockroom/templates/stockroom/jefe/reportes.html',
    ROOT / 'stockroom/tests/test_reportes_jefe.py']
missing = [str(x) for x in REQUIRED if not x.is_file()]
if missing:
    sys.exit('No se hicieron cambios. Faltan archivos:\n' + '\n'.join(missing))

urls = URLS.read_text(encoding='utf-8-sig')
panel = PANEL.read_text(encoding='utf-8-sig')
changes = {}

if 'name="descargar_reporte_jefe"' not in urls and "name='descargar_reporte_jefe'" not in urls:
    marker = 'urlpatterns = ['
    if marker not in urls:
        sys.exit('No se encontró urlpatterns. No se modificó nada.')
    urls = urls.replace(marker,
        'from stockroom.boss_reports import reportes_jefe, descargar_reporte_jefe\n\n'
        + marker + '\n'
        + '    path("jefe/reportes/", reportes_jefe, name="reportes_jefe"),\n'
        + '    path("jefe/reportes/pdf/", descargar_reporte_jefe, name="descargar_reporte_jefe"),', 1)
    changes[URLS] = urls

if "{% url 'reportes_jefe' %}" not in panel and '{% url "reportes_jefe" %}' not in panel:
    # Inserción al comienzo del bloque principal preservando el resto del HTML.
    marker = '{% block contenido %}'
    if marker not in panel:
        sys.exit('No se encontró el bloque de contenido del panel; no se modificó nada.')
    link = ('\n<div style="margin:12px 0">'
            '<a href="{% url \'reportes_jefe\' %}" '
            'style="display:inline-block;background:#168e25;color:white;padding:12px 19px;'
            'border-radius:10px;text-decoration:none;font-weight:700">Reportes ejecutivos PDF</a>'
            '</div>\n')
    panel = panel.replace(marker, marker + link, 1)
    changes[PANEL] = panel

modified = [(path, content) for path, content in changes.items()
            if path.read_text(encoding='utf-8-sig') != content]
if not modified:
    print('Fase 13 ya instalada. No hubo modificaciones.')
    sys.exit(0)
backup = ROOT / ('backup_reportes_fase13_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(exist_ok=False)
for path, _ in modified:
    dest = backup / path.relative_to(ROOT)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
for path, content in modified:
    path.write_text(content, encoding='utf-8')
print('Reportes del jefe instalados. Respaldos:', backup)
print('Sin modificaciones de modelos, migraciones ni inventario.')
