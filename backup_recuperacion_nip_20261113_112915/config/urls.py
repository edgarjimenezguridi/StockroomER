
"""
URL configuration for StockroomER.
"""

from django.contrib import admin
from stockroom.boss_auth import AccesoJefeView
from django.urls import path
from stockroom.boss_views import (
    panel_jefe,
    resolver_autorizacion_jefe,
)

from stockroom.warehouse_views import (
    WarehouseLoginView,
    panel_almacen,
    detalle_solicitud_almacen,
    preparar_articulo_almacen,
    terminar_preparacion_almacen,
    confirmar_entrega_almacen,
    adeudos_almacen,
    registrar_devolucion_almacen,
    salir_almacen,
    registrar_entrada_almacen,
    resolver_dano_almacen,
    corregir_existencia_almacen,
    historial_almacen,
    consultar_existencias_almacen,
    reabastecimiento_almacen,
    agregar_articulo_almacen,
)

from stockroom.classification_views import (
    administrar_clasificaciones_almacen,
    
)

from stockroom.individual_tool_views import (
    registrar_pieza_individual_almacen,
)

from stockroom.individual_tool_management_views import (
    consultar_piezas_individuales_almacen,
    editar_pieza_individual_almacen,
)
from stockroom.tool_label_views import (
    imprimir_etiqueta_pieza_almacen,
)


from stockroom.views import (
    activar_nip,
    acceso_empleado,
    panel_empleado,
    salir_empleado,
    guardar_articulo_carrito,
    quitar_articulo_carrito,
    enviar_solicitud,
    confirmar_recibido,
    comanda_empleado,
    escanear_comanda,
)

from stockroom.warehouse_reports import (
    generar_reportes_almacen,
    descargar_reporte_almacen,
)

from stockroom.article_management_views import (
    editar_articulo_almacen,
)




# Peticiones de duplicados iniciadas por trabajadores.
from stockroom.worker_exception_views import solicitar_duplicado_empleado

from stockroom.boss_personnel_views import (
    personal_jefe, estado_trabajador_jefe,
    expediente_trabajador_jefe, estado_cuenta_jefe,
)

from stockroom.pin_onboarding_views import inicio_nip_trabajador, autorizar_nip_jefe

urlpatterns = [
    path("trabajadores/activar-mi-nip/", inicio_nip_trabajador, name="inicio_nip_trabajador"),
    path("jefe/personal/<int:employee_id>/autorizar-nip/", autorizar_nip_jefe, name="autorizar_nip_jefe"),

    path("jefe/personal/", personal_jefe, name="personal_jefe"),
    path("jefe/personal/<int:employee_id>/estado/", estado_trabajador_jefe, name="estado_trabajador_jefe"),
    path("jefe/personal/<int:employee_id>/expediente/", expediente_trabajador_jefe, name="expediente_trabajador_jefe"),
    path("jefe/cuentas/<int:user_id>/estado/", estado_cuenta_jefe, name="estado_cuenta_jefe"),

    path(
        "trabajadores/duplicados/solicitar/",
        solicitar_duplicado_empleado,
        name="solicitar_duplicado_empleado",
    ),

    # Administrador técnico
    path(
        "admin/",
        admin.site.urls,
    ),

    # Trabajadores
    path(
        "trabajadores/acceso/",
        acceso_empleado,
        name="acceso_empleado",
    ),
    path(
        "credenciales/<uuid:barcode>/activar/",
        activar_nip,
        name="activar_nip",
    ),
    path(
        "trabajadores/panel/",
        panel_empleado,
        name="panel_empleado",
    ),
    path(
        "trabajadores/salir/",
        salir_empleado,
        name="salir_empleado",
    ),
    path(
        "trabajadores/carrito/articulo/<int:article_id>/",
        guardar_articulo_carrito,
        name="guardar_articulo_carrito",
    ),
    path(
        "trabajadores/carrito/quitar/<int:line_id>/",
        quitar_articulo_carrito,
        name="quitar_articulo_carrito",
    ),
    path(
        "trabajadores/carrito/<int:cart_id>/enviar/",
        enviar_solicitud,
        name="enviar_solicitud",
    ),
    path(
        "trabajadores/solicitudes/<int:request_id>/confirmar/",
        confirmar_recibido,
        name="confirmar_recibido",
    ),
    path(
        "trabajadores/solicitudes/<int:request_id>/comanda/",
        comanda_empleado,
        name="comanda_empleado",
    ),

    # Acceso al almacén
    path(
        "almacen/acceso/",
        WarehouseLoginView.as_view(),
        name="acceso_almacen",
    ),
    path(
        "almacen/panel/",
        panel_almacen,
        name="panel_almacen",
    ),
    path(
        "almacen/salir/",
        salir_almacen,
        name="salir_almacen",
    ),
    path(
        "almacen/escanear/",
        escanear_comanda,
        name="escanear_comanda",
    ),

    # Solicitudes
    path(
        "almacen/solicitudes/<int:request_id>/",
        detalle_solicitud_almacen,
        name="detalle_solicitud_almacen",
    ),
    path(
        "almacen/solicitudes/<int:request_id>/articulos/<int:line_id>/preparar/",
        preparar_articulo_almacen,
        name="preparar_articulo_almacen",
    ),
    path(
        "almacen/solicitudes/<int:request_id>/terminar-preparacion/",
        terminar_preparacion_almacen,
        name="terminar_preparacion_almacen",
    ),
    path(
        "almacen/solicitudes/<int:request_id>/confirmar-entrega/",
        confirmar_entrega_almacen,
        name="confirmar_entrega_almacen",
    ),

    # Adeudos y devoluciones
    path(
        "almacen/adeudos/",
        adeudos_almacen,
        name="adeudos_almacen",
    ),
    path(
        "almacen/entregas/<int:issue_id>/devolver/",
        registrar_devolucion_almacen,
        name="registrar_devolucion_almacen",
    ),

    # Catálogo de artículos
    path(
        "almacen/articulos/nuevo/",
        agregar_articulo_almacen,
        name="agregar_articulo_almacen",
    ),

    # Nueva administración de clasificaciones
    path(
        "almacen/clasificaciones/",
        administrar_clasificaciones_almacen,
        name="administrar_clasificaciones_almacen",
    ),

    # Entradas y correcciones
    path(
        "almacen/entradas/nueva/",
        registrar_entrada_almacen,
        name="registrar_entrada_almacen",
    ),
    path(
        "almacen/existencias/corregir/",
        corregir_existencia_almacen,
        name="corregir_existencia_almacen",
    ),
    path(
        "almacen/danos/resolver/",
        resolver_dano_almacen,
        name="resolver_dano_almacen",
    ),

    # Consultas
    path(
        "almacen/existencias/",
        consultar_existencias_almacen,
        name="consultar_existencias_almacen",
    ),
    path(
        "almacen/reabastecimiento/",
        reabastecimiento_almacen,
        name="reabastecimiento_almacen",
    ),
    path(
        "almacen/historial/",
        historial_almacen,
        name="historial_almacen",
    ),

    # Reportes
    path(
        "almacen/reportes/",
        generar_reportes_almacen,
        name="generar_reportes_almacen",
    ),
    path(
        "almacen/reportes/pdf/",
        descargar_reporte_almacen,
        name="descargar_reporte_almacen",
    ),
    # Registro de piezas individuales
    path(
        "almacen/piezas/nueva/",
        registrar_pieza_individual_almacen,
        name="registrar_pieza_individual_almacen",
    ),

    # Consulta de herramientas individuales
    path(
        "almacen/piezas/",
        consultar_piezas_individuales_almacen,
        name="consultar_piezas_individuales_almacen",
    ),

    # Edición de herramientas individuales
    path(
        "almacen/piezas/<int:tool_id>/editar/",
        editar_pieza_individual_almacen,
        name="editar_pieza_individual_almacen",
    ),


    path(
        "almacen/articulos/<int:article_id>/editar/",
        editar_articulo_almacen,
        name="editar_articulo_almacen",
    ),

    # Impresion de etiqueta de herramienta individual
    path(
        "almacen/piezas/<int:tool_id>/etiqueta/",
        imprimir_etiqueta_pieza_almacen,
        name="imprimir_etiqueta_pieza_almacen",
    ),

    # Panel del jefe
    path(
        "jefe/panel/",
        panel_jefe,
        name="panel_jefe",
    ),
    path(
        "jefe/autorizaciones/<int:authorization_id>/resolver/",
        resolver_autorizacion_jefe,
        name="resolver_autorizacion_jefe",
    ),
    path(
        "jefe/acceso/",
        AccesoJefeView.as_view(),
        name="acceso_jefe",
    ),




]
