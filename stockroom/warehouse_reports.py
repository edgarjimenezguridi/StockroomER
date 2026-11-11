
import io
from collections import defaultdict
from xml.sax.saxutils import escape

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models.functions import Coalesce, Greatest
from django.db.models import ( 
    F, 
    Count,
    Q,
    Case,
    When, 
    Value, 
    IntegerField,
)
from django.http import FileResponse, HttpResponseBadRequest
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    LongTable,
    TableStyle,
)

from .models import (
    MaterialRequest,
    QuantityIssue,
    QuantityReturn,
    DamageResolution,
    Article,
    QuantityStock,
    Tool,
)


REPORTES = {
    "adeudos": {
        "titulo": "Adeudos generales del almacen",
        "permiso": "stockroom.view_quantityissue",
    },
    "solicitudes": {
        "titulo": "Historial de solicitudes",
        "permiso": "stockroom.view_materialrequest",
    },
    "danos": {
        "titulo": "Reporte de danos y resoluciones",
        "permiso": "stockroom.view_quantityreturn",
    },
    "personal": {
        "titulo": "Adeudos por trabajador",
        "permiso": "stockroom.view_quantityissue",
    },
    "danos_personal": {
    "titulo": "Daños por trabajador",
    "permiso": "stockroom.view_quantityreturn",
    },
    "inventario": {
    "titulo": "Inventario general",
    "permiso": "stockroom.view_article",
    },
    "reabastecimiento": {
    "titulo": "Plan de reabastecimiento",
    "permiso": "stockroom.view_article",
    },
}

def puede_generar_reporte(usuario, tipo, configuracion):
    if not usuario.has_perm(configuracion["permiso"]):
        return False

    if tipo in ("danos", "danos_personal"):
        return usuario.has_perm(
            "stockroom.view_damageresolution"
        )

    if tipo in ("inventario", "reabastecimiento"):
        return usuario.has_perms([
            "stockroom.view_quantitystock",
            "stockroom.view_tool",
        ])

    return True


def verificar_acceso(request):
    if not (
        request.user.is_active
        and request.user.is_staff
        and request.user.has_perm("stockroom.view_materialrequest")
    ):
        raise PermissionDenied(
            "No tienes permiso para acceder a reportes."
        )


def filtrar_fechas(queryset, campo, desde, hasta):
    if desde:
        queryset = queryset.filter(
            **{f"{campo}__date__gte": desde}
        )

    if hasta:
        queryset = queryset.filter(
            **{f"{campo}__date__lte": hasta}
        )

    return queryset


def datos_reporte(tipo, desde, hasta, empleado):
    filas = []

    if tipo in ("adeudos", "personal"):
        entregas = (
            QuantityIssue.objects.filter(
                requires_return=True,
                returned_quantity__lt=F("quantity"),
            )
            .select_related(
                "employee",
                "stock__article",
                "tool__article",
            )
            .order_by("employee__employee_id", "issued_at")
        )

        entregas = filtrar_fechas(
            entregas, "issued_at", desde, hasta
        )

        if tipo == "personal" and empleado:
            entregas = entregas.filter(
                employee__employee_id=empleado
            )

        
        if tipo == "adeudos":
            resumen = defaultdict(lambda: [0, 0])

            for entrega in entregas:
                if entrega.tool_id:
                    codigo = entrega.tool.tool_code
                    nombre = entrega.tool.name
                else:
                    articulo = entrega.stock.article
                    codigo = articulo.article_code
                    nombre = articulo.name

                clave = (
                    entrega.employee.employee_id,
                    str(entrega.employee),
                    codigo,
                    nombre,
                )

                resumen[clave][0] += 1
                resumen[clave][1] += (
                    entrega.quantity - entrega.returned_quantity
                )

            for (numero, trabajador, codigo, nombre), cantidades in sorted(
                resumen.items()
            ):
                filas.append([
                    f"{numero} - {trabajador}",
                    f"{codigo} - {nombre}",
                    str(cantidades[0]),
                    str(cantidades[1]),
                ])

            encabezados = [
                "Trabajador",
                "Artículo / Pieza",
                "Entregas abiertas",
                "Piezas pendientes",
            ]


        else:
            for entrega in entregas:
                codigo = (
                    entrega.tool.tool_code
                    if entrega.tool_id
                    else entrega.stock.article.article_code
                )
                nombre = (
                    entrega.tool.name
                    if entrega.tool_id
                    else entrega.stock.article.name
                )

                filas.append([
                    str(entrega.employee),
                    codigo,
                    nombre,
                    str(entrega.quantity - entrega.returned_quantity),
                ])

            encabezados = [
                "Trabajador", "Codigo",
                "Articulo", "Pendientes",
            ]

        nota = (
            "Adeudos actuales. Las fechas filtran "
            "la fecha original de entrega."
        )

    elif tipo == "solicitudes":
        solicitudes = (
            MaterialRequest.objects
            .exclude(status=MaterialRequest.Status.DRAFT)
            .select_related("employee")
            .order_by("-submitted_at", "-pk")
        )

        solicitudes = filtrar_fechas(
            solicitudes, "submitted_at", desde, hasta
        )

        for solicitud in solicitudes:
            filas.append([
                str(solicitud.pk),
                str(solicitud.employee),
                solicitud.get_status_display(),
                (
                    timezone.localtime(solicitud.submitted_at)
                    .strftime("%d/%m/%Y %H:%M")
                    if solicitud.submitted_at
                    else "Sin fecha"
                ),
            ])

        encabezados = [
            "Folio", "Trabajador", "Estado", "Fecha de solicitud",
        ]
        nota = "Solicitudes registradas en el periodo seleccionado."

    
    elif tipo == "reabastecimiento":
        articulos = Article.objects.filter(
            is_active=True,
            minimum_stock__gt=0,
        ).annotate(
            disponibles_individuales=Count(
                "individual_tools",
                filter=Q(
                    individual_tools__inventory_status=(
                        Tool.InventoryStatus.AVAILABLE
                    ),
                    individual_tools__is_active=True,
                ),
                distinct=True,
            ),
            prestadas_individuales=Count(
                "individual_tools",
                filter=Q(
                    individual_tools__inventory_status=(
                        Tool.InventoryStatus.LOANED
                    ),
                ),
                distinct=True,
            ),
        ).annotate(
            disponibles_actuales=Case(
                When(
                    tracking_mode=Article.TrackingMode.QUANTITY,
                    then=Coalesce(
                        F("quantity_stock__available_quantity"),
                        Value(0),
                    ),
                ),
                default=F("disponibles_individuales"),
                output_field=IntegerField(),
            ),
            prestadas_actuales=Case(
                When(
                    tracking_mode=Article.TrackingMode.QUANTITY,
                    then=Coalesce(
                        F("quantity_stock__loaned_quantity"),
                        Value(0),
                    ),
                ),
                default=F("prestadas_individuales"),
                output_field=IntegerField(),
            ),
        ).annotate(
            faltante=(
                F("minimum_stock") - F("disponibles_actuales")
            ),
        ).filter(
            faltante__gt=0,
        ).annotate(
            compra_estimada=Greatest(
                Value(0),
                F("faltante") - Case(
                    When(
                        return_mode=Article.ReturnMode.RETURNABLE,
                        then=F("prestadas_actuales"),
                    ),
                    default=Value(0),
                    output_field=IntegerField(),
                ),
                output_field=IntegerField(),
            ),
        ).order_by("-faltante", "article_code")

        for articulo in articulos:
            filas.append([
                articulo.article_code,
                articulo.name,
                str(articulo.disponibles_actuales),
                str(articulo.prestadas_actuales),
                str(articulo.minimum_stock),
                str(articulo.faltante),
                str(articulo.compra_estimada),
            ])

        encabezados = [
            "Codigo",
            "Articulo",
            "Disponibles",
            "Prestadas",
            "Minimo",
            "Faltante",
            "Compra estimada",
        ]

        nota = (
            "Plan calculado con las existencias actuales. "
            "Faltante: piezas necesarias para alcanzar "
            "el minimo disponible. "
            "La compra estimada considera el posible regreso "
            "de piezas prestadas que requieren devolucion. "
            "Es una propuesta, no una orden de compra. "
            "No se aplican filtros de fecha."
        )


    
    elif tipo == "inventario":
        articulos = Article.objects.all().order_by(
            "article_code"
        )

        existencias = {
            stock.article_id: stock
            for stock in QuantityStock.objects.all()
        }

        # Contar las piezas individuales por estado
        piezas = defaultdict(lambda: defaultdict(int))

        conteos = (
            Tool.objects
            .filter(article_id__isnull=False)
            .values(
                "article_id",
                "inventory_status",
                "is_active",
            )
            .annotate(cantidad=Count("pk"))
        )

        for registro in conteos:
            estado = registro["inventory_status"]

            # Una pieza disponible pero desactivada
            # no debe contarse como disponible.
            if (
                estado == Tool.InventoryStatus.AVAILABLE
                and not registro["is_active"]
            ):
                estado = "inactive"

            piezas[registro["article_id"]][estado] += (
                registro["cantidad"]
            )

        for articulo in articulos:
            nombre = articulo.name

            if not articulo.is_active:
                nombre += " (Inactivo)"

            if (
                articulo.tracking_mode
                == Article.TrackingMode.QUANTITY
            ):
                stock = existencias.get(articulo.pk)

                if stock is None:
                    nombre += " (Sin registro de existencias)"

                disponibles = (
                    stock.available_quantity if stock else 0
                )
                prestadas = (
                    stock.loaned_quantity if stock else 0
                )
                cuarentena = (
                    stock.quarantine_quantity if stock else 0
                )
                bajas = (
                    stock.scrapped_quantity if stock else 0
                )

                sin_devolucion = 0
                inactivas = 0
                control = "Cantidad"

            else:
                estados = piezas[articulo.pk]

                disponibles = estados[
                    Tool.InventoryStatus.AVAILABLE
                ]
                prestadas = estados[
                    Tool.InventoryStatus.LOANED
                ]
                cuarentena = estados[
                    Tool.InventoryStatus.QUARANTINE
                ]
                bajas = estados[
                    Tool.InventoryStatus.SCRAPPED
                ]
                sin_devolucion = estados[
                    Tool.InventoryStatus.CONSUMED
                ]
                inactivas = estados["inactive"]

                control = "Individual"

            filas.append([
                articulo.article_code,
                nombre,
                control,
                str(disponibles),
                str(prestadas),
                str(cuarentena),
                str(bajas),
                str(sin_devolucion),
                str(inactivas),
            ])

        encabezados = [
            "Código",
            "Artículo",
            "Control",
            "Disponibles",
            "Prestadas",
            "En revisión",
            "Bajas",
            "Sin devolución",
            "Inactivas",
        ]

        nota = (
            "Inventario al momento de generar el reporte. "
            "Las bajas son acumuladas. "
            "La columna Sin devolución corresponde únicamente "
            "a piezas individuales; los consumibles controlados "
            "por cantidad se descuentan al entregarse. "
            "Inactivas corresponde a piezas individuales "
            "deshabilitadas que conservan estado disponible. "
            "Este reporte no utiliza filtros de fecha."
        )


    
    elif tipo == "danos_personal":
        devoluciones = (
            QuantityReturn.objects.filter(
                condition=QuantityReturn.Condition.DAMAGED
            )
            .select_related("issue__employee")
            .prefetch_related("resolutions")
            .order_by("issue__employee__employee_id", "pk")
        )

        devoluciones = filtrar_fechas(
            devoluciones, "returned_at", desde, hasta
        )

        if empleado:
            devoluciones = devoluciones.filter(
                issue__employee__employee_id=empleado
            )

        resumen = defaultdict(
            lambda: {
                "incidencias": 0,
                "danadas": 0,
                "recuperadas": 0,
                "bajas": 0,
                "pendientes": 0,
            }
        )

        for devolucion in devoluciones:
            trabajador = devolucion.issue.employee

            clave = (
                trabajador.employee_id,
                str(trabajador),
            )

            datos = resumen[clave]

            datos["incidencias"] += 1
            datos["danadas"] += devolucion.quantity
            datos["pendientes"] += (
                devolucion.quantity
                - devolucion.resolved_quantity
            )

            for resolucion in devolucion.resolutions.all():
                if (
                    resolucion.outcome
                    == DamageResolution.Outcome.RESTORED
                ):
                    datos["recuperadas"] += resolucion.quantity

                elif (
                    resolucion.outcome
                    == DamageResolution.Outcome.SCRAPPED
                ):
                    datos["bajas"] += resolucion.quantity

        for (numero, trabajador), datos in sorted(
            resumen.items()
        ):
            filas.append([
                f"{numero} - {trabajador}",
                str(datos["incidencias"]),
                str(datos["danadas"]),
                str(datos["recuperadas"]),
                str(datos["bajas"]),
                str(datos["pendientes"]),
            ])

        encabezados = [
            "Trabajador",
            "Incidencias",
            "Dañadas",
            "Recuperadas",
            "Bajas",
            "Pendientes",
        ]

        nota = (
            "Daños registrados por trabajador. "
            "Las fechas filtran la devolución dañada; "
            "las resoluciones muestran su estado actual."
        )


    else:
        devoluciones = (
            QuantityReturn.objects.filter(
                condition=QuantityReturn.Condition.DAMAGED
            )
            .select_related(
                "issue__employee",
                "issue__tool",
                "issue__stock__article",
            )
            .prefetch_related("resolutions")
            .order_by("-returned_at", "-pk")
        )

        devoluciones = filtrar_fechas(
            devoluciones, "returned_at", desde, hasta
        )

        for devolucion in devoluciones:
            entrega = devolucion.issue

            articulo = (
                str(entrega.tool)
                if entrega.tool_id
                else str(entrega.stock.article)
            )

            resoluciones = "; ".join(
                f"{r.get_outcome_display()}: {r.quantity}"
                for r in devolucion.resolutions.all()
            )

            pendientes = (
                devolucion.quantity - devolucion.resolved_quantity
            )

            filas.append([
                str(entrega.employee),
                articulo,
                devolucion.reason,
                (
                    f"{resoluciones or 'Sin resolucion'} "
                    f"| Pendientes: {pendientes}"
                ),
            ])

        encabezados = [
            "Trabajador", "Articulo",
            "Motivo del dano", "Resoluciones",
        ]
        nota = "Danos registrados y sus resoluciones acumuladas."

    return encabezados, filas, nota


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def generar_reportes_almacen(request):
    verificar_acceso(request)

    opciones = [
        {"valor": clave, "titulo": datos["titulo"]}
        for clave, datos in REPORTES.items()
        if puede_generar_reporte(
            request.user, clave, datos
        )
    ]

    return render(
        request,
        "stockroom/almacen/generar_reportes_almacen.html",
        {"opciones": opciones},
    )


@never_cache
@login_required(login_url="acceso_almacen")
@require_GET
def descargar_reporte_almacen(request):
    verificar_acceso(request)

    tipo = request.GET.get("tipo", "")
    configuracion = REPORTES.get(tipo)

    
    if configuracion is None:
        return HttpResponseBadRequest("Tipo de reporte no valido.")

    if not puede_generar_reporte(
        request.user, tipo, configuracion
    ):
        raise PermissionDenied(
            "No tienes permiso para generar este reporte."
        )


    desde_texto = request.GET.get("desde", "")
    hasta_texto = request.GET.get("hasta", "")
    empleado = request.GET.get("employee_id", "").strip()[:20]

    desde = parse_date(desde_texto) if desde_texto else None
    hasta = parse_date(hasta_texto) if hasta_texto else None

    if (desde_texto and desde is None) or (
        hasta_texto and hasta is None
    ):
        return HttpResponseBadRequest("Fecha no valida.")

    if desde and hasta and desde > hasta:
        return HttpResponseBadRequest(
            "La fecha inicial no puede superar a la final."
        )

    encabezados, filas, nota = datos_reporte(
        tipo, desde, hasta, empleado
    )

    buffer = io.BytesIO()

    documento = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=36,
        rightMargin=36,
        topMargin=40,
        bottomMargin=40,
    )

    estilos = getSampleStyleSheet()

    titulo_estilo = ParagraphStyle(
        "TituloStockroom",
        parent=estilos["Heading1"],
        fontSize=17,
        leading=21,
        textColor=colors.HexColor("#195578"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    celda_estilo = ParagraphStyle(
        "CeldaStockroom",
        parent=estilos["Normal"],
        fontSize=8,
        leading=11,
        wordWrap="LTR",
        splitLongWords=True,
    )

    elementos = [
        Paragraph(
            "ENGRANES Y RECTIFICADOS",
            titulo_estilo,
        ),
        Paragraph(
            escape(configuracion["titulo"]),
            estilos["Heading2"],
        ),
        Paragraph(
            "StockroomER | Generado: "
            + timezone.localtime().strftime("%d/%m/%Y %H:%M"),
            estilos["Normal"],
        ),
        Spacer(1, 8),
        Paragraph(escape(nota), estilos["Normal"]),
        Spacer(1, 14),
    ]

    tabla_datos = [
        [
            Paragraph(
                f"<b>{escape(str(valor))}</b>",
                celda_estilo,
            )
            for valor in encabezados
        ]
    ]

    for fila in filas:
        tabla_datos.append([
            Paragraph(escape(str(valor)), celda_estilo)
            for valor in fila
        ])

    if not filas:
        elementos.append(
            Paragraph(
                "No existen registros para los filtros seleccionados.",
                estilos["Normal"],
            )
        )
    else:
        
        if tipo == "inventario":
            proporciones = [
                1.3, 3.0, 1.2,
                1.0, 1.0, 1.1,
                0.9, 1.3, 1.0,
            ]

            factor = documento.width / sum(proporciones)

            anchos = [
                proporcion * factor
                for proporcion in proporciones
            ]

        elif tipo == "reabastecimiento":
            proporciones = [
                1.3, 3.0, 1.0, 1.0,
                1.0, 1.0, 1.3,
            ]

            factor = documento.width / sum(proporciones)

            anchos = [
                proporcion * factor
                for proporcion in proporciones
            ]

        else:
            ancho = documento.width / len(encabezados)
            anchos = [ancho] * len(encabezados)

        

        tabla = LongTable(
            tabla_datos,
            colWidths=anchos,
            repeatRows=1,
        )


        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0),
             colors.HexColor("#dcecf5")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f3f7fa")]),
            ("GRID", (0, 0), (-1, -1),
             0.3, colors.HexColor("#d1dbe5")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ]))

        elementos.append(tabla)

    
    resumen_final = f"Total de registros: {len(filas)}"

    

    if tipo in ("adeudos", "personal"):
        total_pendientes = sum(
            int(fila[-1]) for fila in filas
        )

        resumen_final += (
            f" | Total de piezas pendientes: {total_pendientes}"
        )

    
    elif tipo == "danos_personal":
        total_danadas = sum(int(fila[2]) for fila in filas)
        total_recuperadas = sum(int(fila[3]) for fila in filas)
        total_bajas = sum(int(fila[4]) for fila in filas)
        total_pendientes = sum(int(fila[5]) for fila in filas)

        resumen_final += (
            f" | Dañadas: {total_danadas}"
            f" | Recuperadas: {total_recuperadas}"
            f" | Bajas: {total_bajas}"
            f" | Pendientes: {total_pendientes}"
        )

    
    elif tipo == "inventario":
        columnas = [
            ("Disponibles", 3),
            ("Prestadas", 4),
            ("En revisión", 5),
            ("Bajas", 6),
            ("Sin devolución", 7),
            ("Inactivas", 8),
        ]

        for nombre, indice in columnas:
            total = sum(
                int(fila[indice]) for fila in filas
            )

            resumen_final += f" | {nombre}: {total}"

    elif tipo == "reabastecimiento":
        total_faltante = sum(
            int(fila[5]) for fila in filas
        )
        total_compra = sum(
            int(fila[6]) for fila in filas
        )

        resumen_final += (
            f" | Piezas faltantes: {total_faltante}"
            f" | Compra estimada: {total_compra}"
        )



    elementos.extend([
        Spacer(1, 18),
        Paragraph(
            f"<b>{escape(resumen_final)}</b>",
            estilos["Normal"],
        ),
    ])


    
    def dibujar_encabezado_pie(canvas, doc):
        canvas.saveState()

        ancho, alto = doc.pagesize

        # Encabezado de cada página
        canvas.setStrokeColor(
            colors.HexColor("#195578")
        )
        canvas.setLineWidth(1.2)

        canvas.line(
            36, alto - 28,
            ancho - 36, alto - 28
        )

        canvas.setFont("Helvetica-Bold", 9)
        canvas.setFillColor(
            colors.HexColor("#195578")
        )

        canvas.drawString(
            36,
            alto - 22,
            "STOCKROOMER | ENGRANES Y RECTIFICADOS",
        )

        # Pie de página
        canvas.setStrokeColor(
            colors.HexColor("#cbd5e1")
        )

        canvas.line(
            36, 30,
            ancho - 36, 30
        )

        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(
            colors.HexColor("#64748b")
        )

        canvas.drawString(
            36,
            18,
            "Documento generado por StockroomER"
        )

        canvas.drawRightString(
            ancho - 36,
            18,
            f"Página {doc.page}"
        )

        canvas.restoreState()

    documento.build(
        elementos,
        onFirstPage=dibujar_encabezado_pie,
        onLaterPages=dibujar_encabezado_pie,
    )

    buffer.seek(0)

    nombre = (
        f"StockroomER_{tipo}_"
        f"{timezone.localdate():%Y%m%d}.pdf"
    )

    return FileResponse(
        buffer,
        as_attachment=True,
        filename=nombre,
    )
