"""Añade ruta y enlace desde catálogo. Ejecutar desde raíz de StockroomER."""
from pathlib import Path
from datetime import datetime
import shutil

root = Path.cwd()
urls = root / 'config' / 'urls.py'
panel = root / 'stockroom' / 'templates' / 'stockroom' / 'empleados' / 'panel_empleado.html'
views = root / 'stockroom' / 'worker_exception_views.py'
page = root / 'stockroom' / 'templates' / 'stockroom' / 'empleados' / 'solicitar_duplicado.html'
for source in [urls, panel, views, page]:
    if not source.is_file():
        raise SystemExit(f'Falta archivo: {source}')

urls_txt = urls.read_text(encoding='utf-8-sig')
panel_txt = panel.read_text(encoding='utf-8-sig')
if 'name="solicitar_duplicado_empleado"' in urls_txt or 'name=\'solicitar_duplicado_empleado\'' in urls_txt:
    raise SystemExit('La ruta ya está instalada. No se realizaron cambios.')
if 'urlpatterns = [' not in urls_txt:
    raise SystemExit('No se encontró urlpatterns. No se realizaron cambios.')

insert = '''\n# Peticiones de duplicados iniciadas por trabajadores.\nfrom stockroom.worker_exception_views import solicitar_duplicado_empleado\n\n'''
urls_txt = urls_txt.replace('urlpatterns = [', insert + 'urlpatterns = [', 1)
route = '''    path(\n        "trabajadores/duplicados/solicitar/",\n        solicitar_duplicado_empleado,\n        name="solicitar_duplicado_empleado",\n    ),\n'''
urls_txt = urls_txt.replace('urlpatterns = [', 'urlpatterns = [\n' + route, 1)

# No cambiar formularios existentes; solo agregar enlace de navegación.
marker = '<a href="#catalogo">Catálogo</a>'
if marker not in panel_txt:
    raise SystemExit('No encontré el enlace Catálogo del panel. No se realizaron cambios.')
panel_txt = panel_txt.replace(marker, marker + '\n            <a href="{% url \'solicitar_duplicado_empleado\' %}">Solicitar duplicado</a>', 1)

# Acceso directo contextual por artículo (sin cambiar el POST del carrito).
row_marker = '<td class="num">\n                                {% if article.available_quantity > 0 %}'
if row_marker in panel_txt:
    panel_txt = panel_txt.replace(
        row_marker,
        '<td class="num">\n                                {% if article.available_quantity > 0 %}', 1,
    )
# Insertar link al final del td de solicitar usando marcador estable por fila.
end_marker = '                            </td>\n                        </tr>\n                        {% empty %}'
if end_marker in panel_txt:
    panel_txt = panel_txt.replace(
        end_marker,
        '                                <div style="margin-top:7px;font-size:12px"><a href="{% url \'solicitar_duplicado_empleado\' %}?article={{ article.pk }}">Pedir autorización de duplicado</a></div>\n' + end_marker,
        1,
    )

backup = root / ('backup_excepciones_trabajador_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
backup.mkdir(exist_ok=False)
shutil.copy2(urls, backup / 'urls.py')
shutil.copy2(panel, backup / 'panel_empleado.html')
urls.write_text(urls_txt, encoding='utf-8')
panel.write_text(panel_txt, encoding='utf-8')
print('Instalación lista. Copias en:', backup)
print('Ruta nueva: /trabajadores/duplicados/solicitar/')
print('No se modificaron modelos ni base de datos.')
