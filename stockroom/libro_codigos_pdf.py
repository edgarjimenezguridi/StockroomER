"""Libro corporativo de códigos de barras disponibles (Code 128).

No altera existencias. Mantiene identificadores de artículo y pieza sin prefijos.
La consulta a la base se hace únicamente en registros_disponibles().
"""
import io
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable, Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

VERDE = colors.HexColor('#087D29')
VERDE_OSCURO = colors.HexColor('#075824')
TINTA = colors.HexColor('#14243A')
GRIS = colors.HexColor('#5E6B79')
BORDE = colors.HexColor('#D8E6DC')
SUAVE = colors.HexColor('#F2F8F3')


def registros_disponibles():
    """Retorna los códigos existentes escaneables y actualmente disponibles."""
    from .models import Article, Tool

    articulos = (
        Article.objects.filter(
            is_active=True,
            tracking_mode=Article.TrackingMode.QUANTITY,
            quantity_stock__available_quantity__gt=0,
        )
        .select_related('specification__tool_type__category', 'quantity_stock')
        .order_by('article_code')
    )
    piezas = (
        Tool.objects.filter(
            is_active=True,
            inventory_status=Tool.InventoryStatus.AVAILABLE,
            article__is_active=True,
            article__tracking_mode=Article.TrackingMode.INDIVIDUAL,
        )
        .select_related(
            'article__specification__tool_type__category',
            'specification__tool_type__category',
        )
        .order_by('tool_code')
    )

    def clasificar(especificacion):
        if especificacion is None:
            return ('Sin categoría', 'Sin tipo', 'Sin clasificación')
        tipo = especificacion.tool_type
        return (tipo.category.name, tipo.name, especificacion.name)

    registros = []
    for articulo in articulos:
        registros.append((clasificar(articulo.specification), {
            'codigo': articulo.article_code,
            'nombre': articulo.name,
            'clase': 'Artículo por cantidad',
            'detalle': f'Disponibles: {articulo.quantity_stock.available_quantity}',
            'ubicacion': articulo.location or 'Sin ubicación',
        }))
    for pieza in piezas:
        articulo = pieza.article
        registros.append((clasificar(articulo.specification or pieza.specification), {
            'codigo': pieza.tool_code,
            'nombre': articulo.name,
            'clase': 'Pieza individual',
            'detalle': f'Artículo: {articulo.article_code}',
            'ubicacion': pieza.location or articulo.location or 'Sin ubicación',
        }))
    return sorted(registros, key=lambda item: (
        *(str(valor).casefold() for valor in item[0]),
        item[1]['clase'], item[1]['codigo'],
    ))


class _LibroDoc(SimpleDocTemplate):
    """Registra páginas reales de categorías para índice multipaso."""
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and getattr(flowable, '_categoria_toc', None):
            nombre = flowable._categoria_toc
            indice = getattr(flowable, '_categoria_idx', 0)
            llave = f'categoria_{indice}'
            self.canv.bookmarkPage(llave)
            self.notify('TOCEntry', (0, nombre, self.page, llave))


def _estilos():
    base = getSampleStyleSheet()
    return {
        'portada_marca': ParagraphStyle('Marca', parent=base['Normal'], fontSize=10,
                                        leading=14, textColor=VERDE_OSCURO,
                                        spaceAfter=11),
        'portada_titulo': ParagraphStyle('PortadaTitulo', parent=base['Title'], fontSize=31,
                                         leading=38, alignment=TA_LEFT, textColor=TINTA,
                                         spaceAfter=16),
        'portada_sub': ParagraphStyle('PortadaSub', parent=base['Normal'], fontSize=12,
                                      leading=19, textColor=GRIS),
        'seccion': ParagraphStyle('Seccion', parent=base['Heading1'], fontSize=17,
                                  leading=22, textColor=VERDE_OSCURO,
                                  spaceBefore=10, spaceAfter=12, keepWithNext=True),
        'tipo': ParagraphStyle('Tipo', parent=base['Heading2'], fontSize=12,
                               leading=17, textColor=TINTA, spaceBefore=12,
                               spaceAfter=5, keepWithNext=True),
        'clasificacion': ParagraphStyle('Clasificacion', parent=base['Normal'],
                                        fontSize=9.5, leading=14,
                                        textColor=VERDE_OSCURO, spaceBefore=4,
                                        spaceAfter=8, keepWithNext=True),
        'nombre': ParagraphStyle('Nombre', parent=base['Normal'], fontSize=11,
                                 leading=15, textColor=TINTA),
        'meta': ParagraphStyle('Meta', parent=base['Normal'], fontSize=8.4,
                               leading=12.5, textColor=GRIS),
        'codigo': ParagraphStyle('Codigo', parent=base['Normal'], fontSize=9,
                                 leading=12, alignment=TA_CENTER,
                                 textColor=TINTA, spaceBefore=3),
        'nota': ParagraphStyle('Nota', parent=base['Normal'], fontSize=9.5,
                               leading=15, textColor=GRIS),
        'indice': ParagraphStyle('Indice', parent=base['Normal'], fontSize=10.5,
                                 leading=17, textColor=TINTA),
    }


def _logo(logo_path, ancho):
    path = Path(logo_path)
    if not path.is_file():
        return None
    imagen = Image(str(path), width=ancho, height=ancho / 3.0)
    imagen.hAlign = 'LEFT'
    return imagen


def _cabeza_y_pie(canvas, doc, *, logo_path, fecha):
    canvas.saveState()
    ancho, alto = A4
    if doc.page > 1:
        logo = Path(logo_path)
        if logo.is_file():
            canvas.drawImage(str(logo), 37, alto - 78, width=124, height=41.4,
                             preserveAspectRatio=True, mask='auto')
        canvas.setStrokeColor(BORDE)
        canvas.setLineWidth(0.8)
        canvas.line(37, alto - 84, ancho - 37, alto - 84)
        canvas.setFillColor(GRIS)
        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(ancho - 38, alto - 60, 'LIBRO DE CÓDIGOS DE BARRAS')
        canvas.drawRightString(ancho - 38, alto - 72, fecha)
    canvas.setStrokeColor(BORDE)
    canvas.line(37, 41, ancho - 37, 41)
    canvas.setFillColor(GRIS)
    canvas.setFont('Helvetica', 8)
    canvas.drawString(38, 27, 'StockroomER  |  Documento de consulta y escaneo')
    canvas.drawRightString(ancho - 38, 27, f'Página {doc.page}')
    canvas.restoreState()


def _tarjeta(dato, estilos, ancho):
    codigo = str(dato['codigo'])
    # Se codifica exactamente el identificador, sin espacios ni prefijos añadidos.
    base = createBarcodeDrawing('Code128', value=codigo, barHeight=33,
                                barWidth=0.90, humanReadable=False)
    disponible = 205
    # Ajusta solo códigos excepcionales; preserva tamaño normal para escaneo.
    if base.width > disponible:
        base = createBarcodeDrawing('Code128', value=codigo, barHeight=33,
                                    barWidth=0.90 * disponible / base.width,
                                    humanReadable=False)
    etiqueta = [
        Paragraph(f'<b>{escape(str(dato["nombre"]))}</b>', estilos['nombre']),
        Spacer(1, 4),
        Paragraph(escape(str(dato['clase'])), estilos['meta']),
        Paragraph(escape(str(dato['detalle'])), estilos['meta']),
        Paragraph(f'Ubicación: {escape(str(dato["ubicacion"]))}', estilos['meta']),
    ]
    barcode = [base, Paragraph(escape(codigo), estilos['codigo'])]
    tarjeta = Table([[etiqueta, barcode]], colWidths=[ancho - 233, 233], hAlign='LEFT')
    tarjeta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.white),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDE),
        ('LINEBEFORE', (1, 0), (1, 0), 0.6, BORDE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (0, 0), 13),
        ('RIGHTPADDING', (0, 0), (0, 0), 9),
        ('LEFTPADDING', (1, 0), (1, 0), 13),
        ('RIGHTPADDING', (1, 0), (1, 0), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
    ]))
    return KeepTogether([tarjeta, Spacer(1, 8)])


def generar_libro_codigos_pdf(registros=None, generado=None, logo_path=None):
    """Retorna PDF de portada, índice y códigos, sin efectos secundarios.

    Los parámetros opcionales permiten construir una muestra sin base de datos.
    """
    if registros is None:
        registros = registros_disponibles()
    registros = list(registros)
    if generado is None:
        from django.utils import timezone
        generado = timezone.localtime()
    fecha = generado.strftime('%d/%m/%Y %H:%M')
    if logo_path is None:
        logo_path = Path(__file__).resolve().parent / 'static' / 'img' / 'logo_empresa.png'

    buffer = io.BytesIO()
    doc = _LibroDoc(buffer, pagesize=A4, leftMargin=38, rightMargin=38,
                    topMargin=98, bottomMargin=58,
                    title='Libro de códigos de barras | StockroomER',
                    author='Engranes y Rectificado')
    estilos = _estilos()
    grupos = defaultdict(list)
    for grupo, dato in registros:
        grupos[tuple(grupo)].append(dato)
    categorias = sorted({grupo[0] for grupo in grupos}, key=lambda x: x.casefold())
    cantidades = sum(d['clase'] == 'Artículo por cantidad' for _, d in registros)
    individuales = sum(d['clase'] == 'Pieza individual' for _, d in registros)

    story = []
    story.append(Spacer(1, 65))
    logo = _logo(logo_path, 390)
    if logo is not None:
        story += [logo, Spacer(1, 55)]
    else:
        story += [Paragraph('ENGRANES Y RECTIFICADO', estilos['portada_marca']), Spacer(1, 62)]
    story += [
        Paragraph('LIBRO DE<br/>CÓDIGOS DE BARRAS', estilos['portada_titulo']),
        HRFlowable(width=120, thickness=4, color=VERDE, hAlign='LEFT'),
        Spacer(1, 18),
        Paragraph('Inventario disponible · Catálogo para consulta y escaneo de artículos y herramientas individuales.', estilos['portada_sub']),
        Spacer(1, 35),
    ]
    resumen = Table([[
        Paragraph(f'<font color="#087D29" size="18"><b>{len(registros)}</b></font><br/>Códigos disponibles', estilos['nota']),
        Paragraph(f'<font color="#087D29" size="18"><b>{cantidades}</b></font><br/>Artículos por cantidad', estilos['nota']),
        Paragraph(f'<font color="#087D29" size="18"><b>{individuales}</b></font><br/>Piezas individuales', estilos['nota']),
    ]], colWidths=[doc.width / 3] * 3)
    resumen.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SUAVE),
        ('BOX', (0, 0), (-1, -1), 0.8, BORDE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
    ]))
    story += [resumen, Spacer(1, 24),
              Paragraph(f'<b>Fecha de emisión:</b> {escape(fecha)}', estilos['nota']),
              Spacer(1, 7),
              Paragraph('Solo incluye artículos y piezas disponibles a la hora de generación. Si hay movimientos posteriores, genere una edición actualizada.', estilos['nota']),
              PageBreak()]

    story += [Paragraph('Índice por categoría', estilos['seccion']),
              Paragraph('Seleccione una categoría en el PDF para ir a su sección. El número indica la página de inicio.', estilos['nota']),
              Spacer(1, 18)]
    toc = TableOfContents()
    toc.levelStyles = [estilos['indice']]
    story += [toc, Spacer(1, 25),
              Paragraph('Cómo utilizar este libro', estilos['tipo']),
              Paragraph('Escanee las barras negras del código Code 128. Para artículos por cantidad, el código identifica el artículo; para piezas individuales, identifica cada herramienta específica. El escaneo no registra movimientos por sí mismo.', estilos['nota']),
              PageBreak()]

    if not registros:
        story += [Paragraph('Inventario disponible', estilos['seccion']),
                  Paragraph('No hay artículos ni piezas disponibles para incluir en esta edición.', estilos['nota'])]
    else:
        indice_categoria = 0
        for categoria in categorias:
            if indice_categoria:
                story.append(PageBreak())
            indice_categoria += 1
            titulo_categoria = Paragraph('Categoría: ' + escape(str(categoria)), estilos['seccion'])
            titulo_categoria._categoria_toc = str(categoria)
            titulo_categoria._categoria_idx = indice_categoria
            story.append(titulo_categoria)
            grupo_previo = None
            for grupo in sorted((g for g in grupos if g[0] == categoria),
                                key=lambda x: (x[1].casefold(), x[2].casefold())):
                if grupo_previo is None or grupo[1] != grupo_previo[1]:
                    story.append(Paragraph('Tipo: ' + escape(str(grupo[1])), estilos['tipo']))
                story.append(Paragraph('Clasificación / especificación: ' + escape(str(grupo[2])), estilos['clasificacion']))
                for dato in grupos[grupo]:
                    story.append(_tarjeta(dato, estilos, doc.width))
                grupo_previo = grupo

    cb = lambda canvas, documento: _cabeza_y_pie(canvas, documento, logo_path=logo_path, fecha=fecha)
    doc.multiBuild(story, onFirstPage=cb, onLaterPages=cb, maxPasses=4)
    buffer.seek(0)
    return buffer
