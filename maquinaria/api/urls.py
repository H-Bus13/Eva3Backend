from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BodegaViewSet, MaquinariaViewSet, ObraViewSet
from .views_arriendos import ArriendoViewSet, DevolucionViewSet, EntregaViewSet

from .views_mantenimiento import MantenimientoViewSet

from .views_empresas import EmpresaViewSet

from .views_cuentas import (UsuarioViewSet, SolicitudViewSet, TerminosViewSet, ComprobanteViewSet,
    AccesoAPI, PerfilAPI, AceptarAPI, FirmarAPI)

from .views_peticiones import PeticionViewSet

router = DefaultRouter()
router.register("maquinaria", MaquinariaViewSet, basename="api-maquinaria")
router.register("obras", ObraViewSet, basename="api-obra")
router.register("bodegas", BodegaViewSet, basename="api-bodega")
router.register("arriendos", ArriendoViewSet, basename="api-arriendo")
router.register("entregas", EntregaViewSet, basename="api-entrega")
router.register("devoluciones", DevolucionViewSet, basename="api-devolucion")
router.register("mantenimientos", MantenimientoViewSet, basename="api-mantenimiento")
router.register("empresas", EmpresaViewSet, basename="api-empresa")
router.register("usuarios", UsuarioViewSet, basename="api-usuario")
router.register("solicitudes", SolicitudViewSet, basename="api-solicitud")
router.register("condiciones", TerminosViewSet, basename="api-condiciones")
router.register("comprobantes", ComprobanteViewSet, basename="api-comprobante")
router.register("solicitudes-arriendo", PeticionViewSet, basename="api-peticion")
urlpatterns = [
    path("acceso/<str:operacion>/", AccesoAPI.as_view(), name="api-acceso"),
    path("perfil/", PerfilAPI.as_view(), name="api-perfil"),
    path("perfil/aceptar/", AceptarAPI.as_view(), name="api-perfil-aceptar"),
    path("perfil/firmar/", FirmarAPI.as_view(), name="api-perfil-firmar"),
] + router.urls



