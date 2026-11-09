"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from stockroom.warehouse_views import (
    WarehouseLoginView,
    panel_almacen,
    detalle_solicitud_almacen,
    preparar_articulo_almacen,
    terminar_preparacion_almacen,
    confirmar_entrega_almacen,
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

urlpatterns = [
    path('admin/', admin.site.urls),
    path("trabajadores/acceso/", acceso_empleado, name="acceso_empleado"),
    path(
        "credenciales/<uuid:barcode>/activar/",
        activar_nip,
        name="activar_nip",
    ),
    path("trabajadores/panel/", panel_empleado, name="panel_empleado"),
    path("trabajadores/salir/", salir_empleado, name="salir_empleado"),
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
    path(
        "almacen/escanear/",
        escanear_comanda,
        name="escanear_comanda",
    ),
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

]
