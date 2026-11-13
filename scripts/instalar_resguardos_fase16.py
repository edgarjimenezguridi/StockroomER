"""Instala consulta de stock por trabajador sin tocar base de datos ni inventario."""
from pathlib import Path
from datetime import datetime
import shutil
import sys

root = Path.cwd()
source = Path(__file__).resolve().parent.parent
paths = [
    "stockroom/assigned_stock_views.py",
    "stockroom/templates/stockroom/almacen/stock_asignado.html",
    "stockroom/tests/test_stock_asignado.py",
]
urls = root / "config/urls.py"
panel = root / "stockroom/templates/stockroom/almacen/panel_almacen.html"
required = ["manage.py", "stockroom/initial_stock_views.py", "stockroom/loan_rules.py", "stockroom/models.py", "config/urls.py"]
if not all((root / f).is_file() for f in required):
    sys.exit("ERROR: ejecuta desde la raíz de StockroomER con la Fase 15 instalada.")
if not all((source / f).is_file() for f in paths):
    sys.exit("ERROR: faltan archivos del ZIP. Conserva las carpetas al descomprimir.")
if not panel.is_file():
    sys.exit("ERROR: no se encontró el panel del almacén.")
urltext = urls.read_text(encoding="utf-8-sig")
paneltext = panel.read_text(encoding="utf-8-sig")
if 'name="stock_asignado_almacen"' not in urltext:
    urltext += '''\n# Fase 16 - resguardos y stock por trabajador\nfrom stockroom.assigned_stock_views import stock_asignado_almacen, resguardo_stock_pdf_almacen\nurlpatterns += [\n    path("almacen/stock-asignado/", stock_asignado_almacen, name="stock_asignado_almacen"),\n    path("almacen/stock-asignado/<int:employee_id>/resguardo.pdf", resguardo_stock_pdf_almacen, name="resguardo_stock_pdf_almacen"),\n]\n'''
link = '<a href="{% url \'stock_asignado_almacen\' %}" class="accion-almacen">Stock asignado por trabajador</a>'
if "stock_asignado_almacen" not in paneltext:
    if "</main>" in paneltext:
        paneltext = paneltext.replace("</main>", '<div class="acciones-almacen" style="margin:16px auto;max-width:1100px">' + link + '</div>\n</main>', 1)
    else:
        sys.exit("ERROR: no se encontró </main> en el panel. No se realizaron cambios.")
compile(urltext, str(urls), "exec")
backup = root / "backups" / ("resguardos_fase16_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
backup.mkdir(parents=True, exist_ok=True)
for path in [urls, panel] + [root / f for f in paths]:
    if path.is_file():
        out = backup / path.relative_to(root)
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, out)
urls.write_text(urltext, encoding="utf-8")
panel.write_text(paneltext, encoding="utf-8")
for item in paths:
    dst = root / item
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / item, dst)
print("OK: Fase 16 instalada. Sin movimientos de inventario ni cambios en SQLite.")
print("Respaldo:", backup)
print("Pruebas: python manage.py test stockroom.tests.test_stock_asignado")
