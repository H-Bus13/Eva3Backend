from django.db.models import Q
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from maquinaria.models import Bodega, Maquinaria, Obra
from maquinaria.servicios_maquinaria import crear_maquinaria, editar_maquinaria, operar_maquinaria
from maquinaria.servicios_ubicaciones import cambiar_actividad_ubicacion, guardar_ubicacion
from .permissions import CuentaHabilitada, PermisosInventario
from .serializers import (
    BodegaLecturaSerializer, CrearBodegaSerializer, CrearMaquinariaSerializer,
    EditarMaquinariaSerializer, FiltroBodegaSerializer, FiltroMaquinariaSerializer,
    FiltroPaginaSerializer, FiltroUbicacionSerializer, HistorialUbicacionSerializer,
    MaquinariaLecturaSerializer, MotivoSerializer, MovimientoSerializer,
    ObraEntradaSerializer, ObraLecturaSerializer, TrasladarMaquinariaSerializer, UbicacionEntradaSerializer,
)


class InventarioBase(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [CuentaHabilitada, PermisosInventario]
    # No se implementan DELETE ni PUT: las bajas son acciones auditadas y
    # PATCH solo acepta los campos que corresponden a la edición normal.
    http_method_names = ["get", "post", "patch", "head", "options"]

    def historial_paginado(self, consulta, clase):
        filtros = FiltroPaginaSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(consulta)
        return self.get_paginated_response(clase(pagina, many=True).data)


class MaquinariaViewSet(InventarioBase):
    recurso = "maquinaria"
    queryset = Maquinaria.objects.select_related("bodega__obra").order_by("codigo", "pk")
    serializer_class = MaquinariaLecturaSerializer

    def get_serializer_class(self):
        return {
            "create": CrearMaquinariaSerializer, "partial_update": EditarMaquinariaSerializer,
            "trasladar": TrasladarMaquinariaSerializer, "baja": MotivoSerializer, "reactivar": MotivoSerializer,
        }.get(self.action, MaquinariaLecturaSerializer)

    def get_queryset(self):
        consulta = super().get_queryset()
        if self.action == "list":
            filtro = FiltroMaquinariaSerializer(data=self.request.query_params)
            filtro.is_valid(raise_exception=True)
            datos = filtro.validated_data
            if datos.get("q"):
                consulta = consulta.filter(Q(codigo__icontains=datos["q"]) | Q(nombre__icontains=datos["q"]))
            if datos.get("estado"):
                consulta = consulta.filter(estado=datos["estado"])
            if datos.get("bodega"):
                consulta = consulta.filter(bodega=datos["bodega"])
        return consulta

    def create(self, request, format=None):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        maquina = crear_maquinaria(datos=entrada.validated_data, responsable=request.user)
        return Response(MaquinariaLecturaSerializer(maquina).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None, format=None):
        maquina = self.get_object()
        entrada = self.get_serializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        # El servicio combina solo los campos recibidos con la fila bloqueada,
        # sin sobrescribir cambios concurrentes en los demás campos.
        datos = entrada.validated_data
        maquina = editar_maquinaria(maquinaria_id=maquina.pk, datos=datos, responsable=request.user)
        return Response(MaquinariaLecturaSerializer(maquina).data)

    def operar(self, request):
        maquina = self.get_object()
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        maquina = operar_maquinaria(maquinaria_id=maquina.pk, accion=self.action,
            motivo=entrada.validated_data["motivo"], destino=entrada.validated_data.get("destino"), responsable=request.user)
        return Response(MaquinariaLecturaSerializer(maquina).data)

    @action(detail=True, methods=["post"])
    def trasladar(self, request, pk=None, format=None):
        return self.operar(request)

    @action(detail=True, methods=["post"])
    def baja(self, request, pk=None, format=None):
        return self.operar(request)

    @action(detail=True, methods=["post"])
    def reactivar(self, request, pk=None, format=None):
        return self.operar(request)

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None, format=None):
        maquina = self.get_object()
        eventos = maquina.movimientos.select_related("registrado_por").order_by("-fecha", "-pk")
        return self.historial_paginado(eventos, MovimientoSerializer)


class UbicacionViewSetBase(InventarioBase):
    filtro_class = FiltroUbicacionSerializer

    def get_serializer_class(self):
        if self.action == "create":
            return CrearBodegaSerializer if self.recurso == "bodega" else ObraEntradaSerializer
        if self.action == "partial_update":
            return UbicacionEntradaSerializer if self.recurso == "bodega" else ObraEntradaSerializer
        if self.action in ("desactivar", "reactivar"):
            return MotivoSerializer
        return self.serializer_class

    def get_queryset(self):
        consulta = super().get_queryset()
        if self.action == "list":
            filtro = self.filtro_class(data=self.request.query_params)
            filtro.is_valid(raise_exception=True)
            datos = filtro.validated_data
            if datos["estado"] != "todas":
                consulta = consulta.filter(activa=datos["estado"] == "activas")
            if datos.get("q"):
                consulta = consulta.filter(Q(nombre__icontains=datos["q"]) | Q(direccion__icontains=datos["q"]))
            if self.recurso == "bodega" and datos.get("obra"):
                consulta = consulta.filter(obra=datos["obra"])
        # Consultar o reactivar por ID incluye ubicaciones inactivas, aunque
        # el listado por defecto solo muestre las activas.
        return consulta

    def create(self, request, format=None):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ubicacion = guardar_ubicacion(tipo=self.recurso, datos=entrada.validated_data, responsable=request.user)
        return Response(self.serializer_class(ubicacion).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None, format=None):
        ubicacion = self.get_object()
        entrada = self.get_serializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        ubicacion = guardar_ubicacion(tipo=self.recurso, pk=ubicacion.pk, datos=datos, responsable=request.user)
        return Response(self.serializer_class(ubicacion).data)

    def operar(self, request, activar):
        ubicacion = self.get_object()
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ubicacion = cambiar_actividad_ubicacion(tipo=self.recurso, pk=ubicacion.pk,
            activar=activar, motivo=entrada.validated_data["motivo"], responsable=request.user)
        return Response(self.serializer_class(ubicacion).data)

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None, format=None):
        return self.operar(request, activar=False)

    @action(detail=True, methods=["post"])
    def reactivar(self, request, pk=None, format=None):
        return self.operar(request, activar=True)

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None, format=None):
        eventos = self.get_object().historial_actividad.select_related("responsable").order_by("-fecha", "-pk")
        return self.historial_paginado(eventos, HistorialUbicacionSerializer)


class ObraViewSet(UbicacionViewSetBase):
    recurso = "obra"
    queryset = Obra.objects.order_by("nombre", "pk")
    serializer_class = ObraLecturaSerializer


class BodegaViewSet(UbicacionViewSetBase):
    recurso = "bodega"
    queryset = Bodega.objects.select_related("obra").order_by("nombre", "pk")
    serializer_class = BodegaLecturaSerializer
    filtro_class = FiltroBodegaSerializer

