"""Código Code 128 compartido por etiquetas de piezas y artículos."""
import base64

from barcode import Code128
from barcode.writer import SVGWriter


def imagen_codigo_128(codigo):
    """Devuelve SVG integrado como data URI, sin escribir archivos en disco."""
    svg = Code128(str(codigo), writer=SVGWriter()).render(
        writer_options={
            "write_text": False,
            "module_height": 12,
            "module_width": 0.25,
            "quiet_zone": 2.5,
        }
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg).decode("ascii")
