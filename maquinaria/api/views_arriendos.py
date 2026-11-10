from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from maquinaria.consultas_arriendos import consulta_arriendos, consulta_solicitudes
from maquinaria.servicios_arriendos import cancelar_solicitud, confirmar_devolucion, confirmar_entrega, preparar_devolucion, preparar_entrega
from maquinaria.servicios_uso import estado_uso, iniciar_trabajo, pausar_trabajo
from .permissions import CuentaHabilitada
from .permissions_arriendos import PermisosArriendos
from .renderers import PNGPrivadoRenderer
from .serializers import FiltroPaginaSerializer, MotivoSerializer
from .serializers_arriendos import (ArriendoLecturaSerializer, DevolucionLecturaSerializer, EntregaLecturaSerializer,
    EntradaVaciaSerializer, FiltroArriendoSerializer, FiltroSolicitudSerializer, FirmaArriendoSerializer,
    PrepararEntregaSerializer, RecepcionSerializer, SesionLecturaSerializer)


@method_decorator(never_cache, name="dispatch")
class ArriendosBase(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [CuentaHabilitada, PermisosArriendos]
    http_method_names = ["get", "post", "head", "options"]

    def salida(self, objeto, clase, codigo=200):
        return Response(clase(objeto, context=self.get_serializer_context()).data, status=codigo)

    def historial_paginado(self, consulta, clase):
        filtro = FiltroPaginaSerializer(data=self.request.query_params)
        filtro.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(consulta)
        return self.get_paginated_response(clase(pagina, many=True, context=self.get_serializer_context()).data)


class ArriendoViewSet(ArriendosBase):
    serializer_class = ArriendoLecturaSerializer

    def get_queryset(self):
        # La consulta se comparte con los templates. No basta comprobar el
        # permiso en el detalle: también el listado debe filtrar por dueño.
        consulta = consulta_arriendos(self.request.user).order_by("-entregado_en", "-pk")
        if self.action == "list":
            filtro = FiltroArriendoSerializer(data=self.request.query_params)
            filtro.is_valid(raise_exception=True)
            datos = filtro.validated_data
            if datos.get("estado") == "abierto":
                consulta = consulta.filter(devuelto_en__isnull=True)
            elif datos.get("estado") == "firma":
                consulta = consulta.filter(devuelto_en__isnull=True, recibido_en__isnull=False)
            elif datos.get("estado") == "cerrado":
                consulta = consulta.filter(devuelto_en__isnull=False)
            if datos.get("maquinaria"):
                consulta = consulta.filter(maquinaria=datos["maquinaria"])
        return consulta

    def get_serializer_class(self):
        return RecepcionSerializer if self.action == "recibir" else ArriendoLecturaSerializer

    @action(detail=True, methods=["post"])
    def recibir(self, request, pk=None, format=None):
        arriendo = self.get_object()
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        solicitud = preparar_devolucion(arriendo_id=arriendo.pk, datos=entrada.validated_data, responsable=request.user)
        return self.salida(solicitud, DevolucionLecturaSerializer, status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def sesiones(self, request, pk=None, format=None):
        sesiones = self.get_object().sesiones_uso.order_by("-inicio", "-pk")
        return self.historial_paginado(sesiones, SesionLecturaSerializer)

    def operar_uso(self, request, operacion):
        arriendo = self.get_object()
        entrada = EntradaVaciaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        if operacion == "iniciar":
            iniciar_trabajo(arriendo_id=arriendo.pk, usuario=request.user)
        elif operacion == "pausar":
            pausar_trabajo(arriendo_id=arriendo.pk, usuario=request.user)
        datos = estado_uso(arriendo_id=arriendo.pk, usuario=request.user, sincronizar=operacion == "sincronizar")
        return Response(datos)

    @action(detail=True, methods=["post"], url_path="uso/iniciar", url_name="uso-iniciar")
    def iniciar_uso(self, request, pk=None, format=None):
        return self.operar_uso(request, "iniciar")

    @action(detail=True, methods=["post"], url_path="uso/pausar", url_name="uso-pausar")
    def pausar_uso(self, request, pk=None, format=None):
        return self.operar_uso(request, "pausar")

    @action(detail=True, methods=["post"], url_path="uso/sincronizar", url_name="uso-sincronizar")
    def sincronizar_uso(self, request, pk=None, format=None):
        return self.operar_uso(request, "sincronizar")

    def archivo_firma(self, tipo):
        arriendo = self.get_object()
        campo = arriendo.firma_entrega if tipo == "entrega" else arriendo.firma_devolucion
        try:
            archivo = campo.open("rb")
        except (OSError, ValueError):
            raise Http404("No se encontró la firma.")
        respuesta = FileResponse(archivo, content_type="image/png", filename=f"firma-{tipo}.png")
        respuesta["Cache-Control"] = "private, no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta

    @action(detail=True, methods=["get"], url_path="firmas/entrega", url_name="firma-entrega", renderer_classes=[JSONRenderer, PNGPrivadoRenderer])
    def firma_entrega(self, request, pk=None, format=None):
        return self.archivo_firma("entrega")

    @action(detail=True, methods=["get"], url_path="firmas/devolucion", url_name="firma-devolucion", renderer_classes=[JSONRenderer, PNGPrivadoRenderer])
    def firma_devolucion(self, request, pk=None, format=None):
        return self.archivo_firma("devolucion")


class SolicitudViewSetBase(ArriendosBase):
    def get_queryset(self):
        consulta = consulta_solicitudes(self.request.user, self.tipo).order_by("-creada_en", "-pk")
        if self.action == "list":
            filtro = FiltroSolicitudSerializer(data=self.request.query_params)
            filtro.is_valid(raise_exception=True)
            estado = filtro.validated_data.get("estado")
            campo = "arriendo" if self.tipo == "entrega" else "confirmada_en"
            if estado == "confirmada":
                consulta = consulta.filter(**{campo + "__isnull": False})
            elif estado == "cancelada":
                consulta = consulta.filter(cancelada_en__isnull=False)
            elif estado in ("pendiente", "vencida"):
                consulta = consulta.filter(cancelada_en__isnull=True, **{campo + "__isnull": True})
                consulta = consulta.filter(vence_en__gt=timezone.now()) if estado == "pendiente" else consulta.filter(vence_en__lte=timezone.now())
        return consulta

    def get_serializer_class(self):
        if self.action == "confirmar":
            return FirmaArriendoSerializer
        if self.action == "cancelar":
            return MotivoSerializer
        return self.serializer_class

    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser])
    def confirmar(self, request, pk=None, format=None):
        solicitud = self.get_object()  # Comprueba también quién puede firmar.
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        servicio = confirmar_entrega if self.tipo == "entrega" else confirmar_devolucion
        arriendo = servicio(solicitud_id=solicitud.pk, usuario=request.user, firma=entrada.validated_data["firma"])
        codigo = status.HTTP_201_CREATED if self.tipo == "entrega" else status.HTTP_200_OK
        return self.salida(arriendo, ArriendoLecturaSerializer, codigo)

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None, format=None):
        solicitud = self.get_object()
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        solicitud = cancelar_solicitud(tipo=self.tipo, pk=solicitud.pk,
            motivo=entrada.validated_data["motivo"], responsable=request.user)
        return self.salida(solicitud, self.serializer_class)


class EntregaViewSet(SolicitudViewSetBase):
    tipo = "entrega"
    serializer_class = EntregaLecturaSerializer

    def get_serializer_class(self):
        return PrepararEntregaSerializer if self.action == "create" else super().get_serializer_class()

    def create(self, request, format=None):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        solicitud = preparar_entrega(datos=entrada.validated_data, responsable=request.user)
        return self.salida(solicitud, EntregaLecturaSerializer, status.HTTP_201_CREATED)


class DevolucionViewSet(SolicitudViewSetBase):
    tipo = "devolucion"
    serializer_class = DevolucionLecturaSerializer
