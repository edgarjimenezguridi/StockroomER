"""Instalador fase 15B. Desde la raiz de StockroomER. Sin movimientos reales."""
from datetime import datetime
from pathlib import Path
import shutil
import sys

root = Path.cwd()
source = Path(__file__).resolve().parent.parent
urls = root / "config/urls.py"
panel = root / "stockroom/templates/stockroom/almacen/panel_almacen.html"
parts = [
 ("stockroom/initial_stock_views.py", "stockroom/initial_stock_views.py"),
 ("stockroom/templates/stockroom/almacen/asignar_stock_inicial.html", "stockroom/templates/stockroom/almacen/asignar_stock_inicial.html"),
 ("stockroom/tests/test_stock_inicial_asignacion.py", "stockroom/tests/test_stock_inicial_asignacion.py"),
]
if not all((root/p).is_file() for p in ("manage.py", "stockroom/models.py", "stockroom/loan_rules.py", "stockroom/services.py", "config/urls.py")):
    sys.exit("ERROR: ejecuta desde la raiz de StockroomER.")
if not (root/"stockroom/tests/test_stock_inicial_rules.py").is_file():
    sys.exit("ERROR: falta fase 15A.")
if not all((source/src).is_file() for src, _ in parts):
    sys.exit("ERROR: falta contenido del paquete fase15B. Conserva la estructura descomprimida.")
if not panel.exists():
    sys.exit("ERROR: no existe la plantilla del panel del almacen.")
urltext = urls.read_text(encoding="utf-8-sig")
paneltext = panel.read_text(encoding="utf-8-sig")
urlmark = 'name="asignar_stock_inicial_almacen"'
if urlmark not in urltext:
    urltext += '''\n# Fase 15B - asignacion inicial\nfrom stockroom.initial_stock_views import asignar_stock_inicial_almacen\nurlpatterns += [\n    path("almacen/stock-inicial/", asignar_stock_inicial_almacen, name="asignar_stock_inicial_almacen"),\n]\n'''
link = '<a href="{% url \'asignar_stock_inicial_almacen\' %}" class="accion-almacen">Asignar stock inicial</a>'
if "asignar_stock_inicial_almacen" not in paneltext:
    if '</main>' in paneltext:
        paneltext = paneltext.replace('</main>', '<div class="acciones-almacen" style="margin:16px auto;max-width:1100px">'+link+'</div>\n</main>', 1)
    elif '</body>' in paneltext:
        paneltext = paneltext.replace('</body>', '<div class="acciones-almacen" style="margin:16px auto;max-width:1100px">'+link+'</div>\n</body>',1)
    else:
        sys.exit("ERROR: no se identifico el cierre del panel. No se cambio nada.")
# Validar codigo resultante antes de tocar los archivos.
for data, path in [(urltext, urls), (paneltext, panel)]:
    if path == urls:
        compile(data, str(path), 'exec')
backup = root / "backups" / ("stock_inicial_15b_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
backup.mkdir(parents=True, exist_ok=True)
for item in (urls, panel, *(root/d for _,d in parts)):
    if item.exists():
        dest = backup / item.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item, dest)
urls.write_text(urltext, encoding="utf-8")
panel.write_text(paneltext, encoding="utf-8")
for src, dest in parts:
    dst = root / dest
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / src, dst)
print("OK: Fase 15B instalada. No se movio inventario ni se modifico la base de datos.")
print("Respaldo del codigo:", backup)
print("Verifica: python manage.py check")
print("Verifica: python manage.py test stockroom.tests.test_stock_inicial_asignacion")
print("Verifica: python manage.py test stockroom.tests")
