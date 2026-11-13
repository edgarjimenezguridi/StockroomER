"""Ubica enlaces de las fases 15 a 17 dentro de Consultas y administración.

Ejecutar desde la raíz de StockroomER: python scripts/ajustar_botones_almacen_fase17.py
No modifica URLs, permisos ni base de datos.
"""
from datetime import datetime
from pathlib import Path
import re
import shutil
import sys

ROOT = Path.cwd()
PANEL = ROOT / "stockroom/templates/stockroom/almacen/panel_almacen.html"
URLS = ROOT / "config/urls.py"

BOTONES = (
    ("asignar_stock_inicial_almacen", "🧰 Asignar stock inicial"),
    ("stock_asignado_almacen", "📋 Stock asignado por trabajador"),
    ("baja_trabajador_almacen", "👤 Baja de trabajadores"),
)


def ajustar(texto: str) -> str:
    # Retirar los enlaces flotantes que insertaron los instaladores anteriores.
    for nombre, _ in BOTONES:
        patron_flotante = (
            r'<div\s+class=["\']acciones-almacen["\']\s+'
            r'style=["\']margin:16px auto;max-width:1100px["\']\s*>\s*'
            r'<a\s+href=["\']\{%\s*url\s+["\']' + re.escape(nombre) +
            r'["\']\s*%\}["\']\s+class=["\']accion-almacen["\'][^>]*>.*?</a>\s*</div>'
        )
        texto = re.sub(patron_flotante, "", texto, flags=re.DOTALL | re.IGNORECASE)

    # Ubicar el bloque ya existente, respetando los estilos CSS del proyecto.
    nav_inicio = re.search(
        r'<nav\b[^>]*\baria-label\s*=\s*["\']Consultas y administración["\'][^>]*>',
        texto, flags=re.DOTALL | re.IGNORECASE,
    )
    if not nav_inicio:
        raise ValueError("No encontré el menú 'Consultas y administración'. No se modificó nada.")
    nav_cierre = re.search(r'</nav\s*>', texto[nav_inicio.end():], flags=re.IGNORECASE)
    if not nav_cierre:
        raise ValueError("No encontré el cierre </nav> de Consultas y administración.")
    fin = nav_inicio.end() + nav_cierre.start()
    contenido_nav = texto[nav_inicio.end():fin]

    nuevos = []
    for nombre, etiqueta in BOTONES:
        if re.search(r'\{%\s*url\s+["\']' + re.escape(nombre) + r'["\']\s*%\}', contenido_nav):
            continue
        nuevos.append(
            f"                            <a class=\"accion-almacen\" href=\"{{% url '{nombre}' %}}\">{etiqueta}</a>"
        )
    if nuevos:
        texto = texto[:fin] + '\n\n' + '\n\n'.join(nuevos) + '\n\n' + texto[fin:]
    return texto


def main():
    if not PANEL.is_file() or not URLS.is_file():
        sys.exit("ERROR: ejecuta desde la raíz de StockroomER; no se encontró el panel o urls.py.")
    urls = URLS.read_text(encoding="utf-8-sig")
    for nombre, _ in BOTONES:
        if f'name="{nombre}"' not in urls:
            sys.exit(f"ERROR: falta la ruta {nombre} en config/urls.py. No se modificó nada.")
    original = PANEL.read_text(encoding="utf-8-sig")
    try:
        actualizado = ajustar(original)
    except ValueError as exc:
        sys.exit(f"ERROR: {exc}")
    if actualizado == original:
        print("OK: los tres botones ya están en su lugar. No hubo cambios.")
        return
    backup_dir = ROOT / 'backups' / ('botones_almacen_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup_dir.mkdir(parents=True, exist_ok=True)
    respaldo = backup_dir / 'panel_almacen.html'
    shutil.copy2(PANEL, respaldo)
    PANEL.write_text(actualizado, encoding='utf-8')
    print('OK: botones ubicados en Consultas y administración.')
    print('Respaldo:', respaldo)
    print('Se modificó únicamente:', PANEL)
    print('Ahora ejecuta: python manage.py check')
    print('Y: python manage.py test stockroom.tests')


if __name__ == '__main__':
    main()
