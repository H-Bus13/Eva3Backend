from django.contrib.auth import views as auth_views
from django.urls import include, path

from maquinaria import views, views_solicitudes, views_maquinaria, views_ubicaciones, views_mantenimiento, views_arriendos, views_uso, views_bloqueos, views_usuarios

from maquinaria import views_solicitudes_arriendo as peticiones_views

urlpatterns = [
    path("solicitudes-arriendo/", peticiones_views.peticiones, name="peticiones"),
    path("solicitudes-arriendo/nueva/<int:maquinaria_id>/", peticiones_views.nueva_peticion, name="nueva_peticion"),
    path("solicitudes-arriendo/<int:pk>/", peticiones_views.detalle_peticion, name="detalle_peticion"),
    path("solicitudes-arriendo/<int:pk>/firma/", peticiones_views.firma_peticion, name="firma_peticion"),
    path("solicitudes-arriendo/<int:pk>/<str:accion>/", peticiones_views.operar_peticion, name="operar_peticion"),
    path("api/v1/", include("maquinaria.api.urls")),
    path("usuarios/", views_usuarios.usuarios, name="usuarios"),
    path("usuarios/nuevo/", views_usuarios.nuevo_usuario, name="nuevo_usuario"),
    path("usuarios/<int:pk>/", views_usuarios.detalle_usuario, name="detalle_usuario"),
    path("usuarios/<int:pk>/<str:accion>/", views_usuarios.editar_usuario, name="editar_usuario"),
    path("alertas/atrasos/", views_bloqueos.alertas_atraso, name="alertas_atraso"),
    path("empresas/<int:pk>/bloqueos/", views_bloqueos.detalle_bloqueo_empresa, name="detalle_bloqueo_empresa"),
    path("empresas/<int:pk>/bloqueo/<str:accion>/", views_bloqueos.bloqueo_manual_empresa, name="bloqueo_manual_empresa"),
    path("arriendos/<int:pk>/uso/estado/", views_uso.sincronizar_uso, name="sincronizar_uso"),
    path("arriendos/<int:pk>/uso/<str:accion>/", views_uso.operar_uso, name="operar_uso"),
    path("arriendos/", views_arriendos.arriendos, name="arriendos"),
    path("arriendos/entrega/nueva/", views_arriendos.nueva_entrega, name="nueva_entrega"),
    path("arriendos/solicitudes/<str:tipo>/<int:pk>/", views_arriendos.solicitud_arriendo, name="solicitud_arriendo"),
    path("arriendos/solicitudes/<str:tipo>/<int:pk>/cancelar/", views_arriendos.cancelar_solicitud_view, name="cancelar_solicitud_arriendo"),
    path("arriendos/<int:pk>/", views_arriendos.detalle_arriendo, name="detalle_arriendo"),
    path("arriendos/<int:pk>/recibir/", views_arriendos.nueva_devolucion, name="nueva_devolucion"),
    path("arriendos/<int:pk>/firma/<str:tipo>/", views_arriendos.firma_arriendo, name="firma_arriendo"),
    path("mantenciones/", views_mantenimiento.mantenciones, name="mantenciones"),
    path("mantenciones/nueva/", views_mantenimiento.nueva_mantencion, name="nueva_mantencion"),
    path("mantenciones/<int:pk>/", views_mantenimiento.detalle_mantenimiento, name="detalle_mantenimiento"),
    path("mantenciones/<int:pk>/<str:accion>/", views_mantenimiento.operacion_mantenimiento, name="operacion_mantenimiento"),
    path("ubicaciones/<str:tipo>/<int:pk>/actividad/<str:accion>/", views_ubicaciones.actividad_ubicacion, name="actividad_ubicacion"),
    path("ubicaciones/<str:tipo>/<int:pk>/historial/", views_ubicaciones.historial_ubicacion, name="historial_ubicacion"),
    path("maquinaria/", views_maquinaria.catalogo, name="catalogo"),
    path("maquinaria/nueva/", views_maquinaria.nueva_maquinaria, name="nueva_maquinaria"),
    path("maquinaria/<int:pk>/", views_maquinaria.detalle_maquinaria, name="detalle_maquinaria"),
    path("maquinaria/<int:pk>/editar/", views_maquinaria.editar_maquinaria_view, name="editar_maquinaria"),
    path("maquinaria/<int:pk>/operacion/<str:accion>/", views_maquinaria.operacion_maquinaria, name="operacion_maquinaria"),
    path("ubicaciones/", views_maquinaria.ubicaciones, name="ubicaciones"),
    path("ubicaciones/<str:tipo>/nueva/", views_maquinaria.ubicacion_form, name="nueva_ubicacion"),
    path("ubicaciones/<str:tipo>/<int:pk>/editar/", views_maquinaria.ubicacion_form, name="editar_ubicacion"),
    path("solicitud/", views_solicitudes.estado_solicitud, name="estado_solicitud"),
    path("solicitud/reenviar/", views_solicitudes.reenviar_solicitud, name="reenviar_solicitud"),
    path("perfil/", views.perfil, name="perfil"),
    path("perfil/aceptar/", views.aceptar_terminos, name="aceptar_terminos"),
    path("perfil/firmar/", views.guardar_firma, name="guardar_firma"),
    path("condiciones/publicar/", views.publicar_terminos, name="publicar_terminos"),
    path("comprobantes/<int:pk>/", views.ver_comprobante, name="ver_comprobante"),
    path("comprobantes/<int:pk>/firma/", views.ver_firma, name="ver_firma"),
    path("", views.inicio, name="inicio"),
    path("registro/", views.registro, name="registro"),
    path("ingresar/", views_solicitudes.IngresoConSolicitudView.as_view(), name="login"),
    path("salir/", auth_views.LogoutView.as_view(), name="logout"),
    path("cuentas/pendientes/", views.pendientes, name="pendientes"),
    path("cuentas/<int:pk>/revisar/", views.revisar_cuenta, name="revisar_cuenta"),
]










