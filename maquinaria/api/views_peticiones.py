from django.db.models import Q
from django.http import FileResponse, Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from maquinaria.servicios_solicitudes_arriendo import consultar, solicitar, revisar, cancelar, preparar_desde_solicitud
from .permissions import CuentaHabilitada
from .renderers import PNGPrivadoRenderer
from .serializers import MotivoSerializer, FiltroPaginaSerializer
from .serializers_mantenimiento import ConfirmarMantenimientoSerializer
from .serializers_arriendos import EntregaLecturaSerializer
from .serializers_peticiones import (CrearPeticionSerializer, PeticionLecturaSerializer,
                                    HistorialPeticionSerializer, FiltroPeticionSerializer)


class PermisosPeticion(BasePermission):
    def has_permission(self, request, view):
        if view.action in ("create", "enviar"):
            return (request.user.rol == "CONTRATISTA" and not request.user.is_staff and not request.user.is_superuser)
        if view.action in ("aprobar", "rechazar", "entregar"):
            return request.user.has_perm("maquinaria.gestionar_arriendos")
        return True


@method_decorator(never_cache, name="dispatch")
class PeticionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [CuentaHabilitada, PermisosPeticion]
    serializer_class = PeticionLecturaSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        consulta = consultar(self.request.user).order_by("-creada_en", "-pk")
        if self.action == "list":
            filtro = FiltroPeticionSerializer(data=self.request.query_params)
            filtro.is_valid(raise_exception=True)
            datos = filtro.validated_data
            estado = datos.get("estado")
            if estado == "VENCIDA":
                consulta = consulta.filter(Q(estado="VENCIDA") | Q(estado="APROBADA", reserva_hasta__lte=timezone.now()))
            elif estado == "APROBADA":
                consulta = consulta.filter(estado="APROBADA", reserva_hasta__gt=timezone.now())
            elif estado:
                consulta = consulta.filter(estado=estado)
            if datos.get("maquinaria"):
                consulta = consulta.filter(maquinaria_id=datos["maquinaria"])
        return consulta

    def get_serializer_class(self):
        if self.action == "create":
            return CrearPeticionSerializer
        if self.action in ("aprobar", "rechazar", "cancelar"):
            return MotivoSerializer
        if self.action == "entregar":
            return ConfirmarMantenimientoSerializer
        return PeticionLecturaSerializer

    def salida(self, solicitud):
        return Response(PeticionLecturaSerializer(solicitud, context=self.get_serializer_context()).data)

    @action(detail=False, methods=["post"], url_path="enviar", parser_classes=[MultiPartParser])
    def enviar(self, request, format=None):
        # Se usa una ruta multipart explícita para no cambiar el parser de
        # las acciones de revisión, que solo aceptan JSON.
        entrada = CrearPeticionSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        solicitud = solicitar(datos=datos, firma=datos["firma"], usuario=request.user)
        return Response(PeticionLecturaSerializer(solicitud, context=self.get_serializer_context()).data, status=201)

    def operar(self, request, accion):
        solicitud = self.get_object()
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        if accion == "cancelar":
            solicitud = cancelar(solicitud_id=solicitud.pk, motivo=entrada.validated_data["motivo"], usuario=request.user)
        elif accion == "entregar":
            entrega = preparar_desde_solicitud(solicitud_id=solicitud.pk, actor=request.user)
            return Response(EntregaLecturaSerializer(entrega, context=self.get_serializer_context()).data, status=201)
        else:
            solicitud = revisar(solicitud_id=solicitud.pk, aprobar=accion == "aprobar",
                motivo=entrada.validated_data["motivo"], actor=request.user)
        return self.salida(solicitud)

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None, format=None):
        return self.operar(request, "aprobar")

    @action(detail=True, methods=["post"])
    def rechazar(self, request, pk=None, format=None):
        return self.operar(request, "rechazar")

    @action(detail=True, methods=["post"])
    def cancelar(self, request, pk=None, format=None):
        return self.operar(request, "cancelar")

    @action(detail=True, methods=["post"])
    def entregar(self, request, pk=None, format=None):
        return self.operar(request, "entregar")

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None, format=None):
        consulta = self.get_object().historial.order_by("-fecha", "-pk")
        filtro = FiltroPaginaSerializer(data=request.query_params)
        filtro.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(consulta)
        return self.get_paginated_response(HistorialPeticionSerializer(pagina, many=True).data)

    @action(detail=True, methods=["get"], renderer_classes=[JSONRenderer, PNGPrivadoRenderer])
    def firma(self, request, pk=None, format=None):
        try:
            archivo = self.get_object().firma_solicitud.open("rb")
        except (OSError, ValueError):
            raise Http404("No se encontró la firma.")
        respuesta = FileResponse(archivo, content_type="image/png", filename="firma-solicitud.png")
        respuesta["Cache-Control"] = "private, no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta
