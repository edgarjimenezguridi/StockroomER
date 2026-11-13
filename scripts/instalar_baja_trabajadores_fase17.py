"""Instala Fase 17 sin ejecutar bajas ni modificar la base de datos."""
from pathlib import Path
from datetime import datetime
import shutil
import sys

root = Path.cwd()
source = Path(__file__).resolve().parent.parent
paths = [
    "stockroom/employee_offboarding_views.py",
    "stockroom/templates/stockroom/almacen/baja_trabajador.html",
    "stockroom/tests/test_baja_trabajadores.py",
]
urls = root / "config/urls.py"
panel = root / "stockroom/templates/stockroom/almacen/panel_almacen.html"
required = ["manage.py", "config/urls.py", "stockroom/models.py", "stockroom/assigned_stock_views.py", "stockroom/initial_stock_views.py"]
if not all((root / f).is_file() for f in required):
    sys.exit("ERROR: ejecuta desde la raíz de StockroomER con Fases 15 y 16 instaladas.")
if not all((source / f).is_file() for f in paths):
    sys.exit("ERROR: archivos incompletos. Descomprime el ZIP conservando carpetas.")
if not panel.is_file():
    sys.exit("ERROR: falta panel_almacen.html")
urltext = urls.read_text(encoding="utf-8-sig")
paneltext = panel.read_text(encoding="utf-8-sig")
if 'name="baja_trabajador_almacen"' not in urltext:
    urltext += '''\n# Fase 17: baja operativa de trabajadores\nfrom stockroom.employee_offboarding_views import baja_trabajador_almacen\nurlpatterns += [\n    path("almacen/trabajadores/baja/", baja_trabajador_almacen, name="baja_trabajador_almacen"),\n]\n'''
link = '<a href="{% url \'baja_trabajador_almacen\' %}" class="accion-almacen">Baja de trabajadores</a>'
if "baja_trabajador_almacen" not in paneltext:
    if "</main>" not in paneltext:
        sys.exit("ERROR: no se encontró </main> en panel_almacen.html. No se ha modificado nada.")
    paneltext = paneltext.replace("</main>", '<div class="acciones-almacen" style="margin:16px auto;max-width:1100px">' + link + '</div>\n</main>', 1)
compile(urltext, str(urls), "exec")
for item in paths:
    compile((source / item).read_text(encoding="utf-8"), str(source / item), "exec") if item.endswith('.py') else None
backup = root / "backups" / ("baja_trabajadores_fase17_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
backup.mkdir(parents=True, exist_ok=True)
for path in [urls, panel] + [root / f for f in paths]:
    if path.is_file():
        dest = backup / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
for item in paths:
    target = root / item
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / item, target)
urls.write_text(urltext, encoding="utf-8")
panel.write_text(paneltext, encoding="utf-8")
print("OK: Fase 17 instalada. No se modificaron datos, existencias ni empleados.")
print("Respaldo de código:", backup)
print("Ahora ejecuta: python manage.py check")
print("Ahora ejecuta: python manage.py test stockroom.tests.test_baja_trabajadores")
print("Ahora ejecuta: python manage.py test stockroom.tests")
