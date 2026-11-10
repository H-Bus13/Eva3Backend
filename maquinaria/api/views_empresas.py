from django.db.models import Exists, OuterRef, Q
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from maquinaria.models import Empresa
from maquinaria.servicios_bloqueos import arriendos_atrasados, cambiar_bloqueo_manual
from .permissions import CuentaHabilitada
from .permissions_empresas import PermisosEmpresa
from .serializers import FiltroPaginaSerializer
from .serializers_arriendos import ArriendoLecturaSerializer
from .serializers_empresas import (
    EmpresaLecturaSerializer, HistorialBloqueoSerializer,
    CambioBloqueoSerializer, FiltroEmpresaSerializer,
)


@method_decorator(never_cache, name="dispatch")
class EmpresaViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [CuentaHabilitada, PermisosEmpresa]
    serializer_class = EmpresaLecturaSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        # EXISTS evalúa el atraso actual sin cargar los arriendos ni crear
        # cambios de estado/historial durante una consulta GET.
        consulta = Empresa.objects.annotate(atraso_actual=Exists(
            arriendos_atrasados().filter(empresa_id=OuterRef("pk")),
        )).order_by("razon_social", "pk")
        if self.action != "list":
            return consulta
        filtros = FiltroEmpresaSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        datos = filtros.validated_data
        if datos.get("q"):
            consulta = consulta.filter(Q(rut__icontains=datos["q"]) | Q(razon_social__icontains=datos["q"]))
        bloqueo = Q(bloqueada=True) | Q(atraso_actual=True)
        if datos["estado"] == "bloqueadas":
            consulta = consulta.filter(bloqueo)
        elif datos["estado"] == "habilitadas":
            consulta = consulta.exclude(bloqueo)
        return consulta

    def get_serializer_class(self):
        return CambioBloqueoSerializer if self.action in ("bloquear", "desbloquear") else EmpresaLecturaSerializer

    def cambiar_bloqueo(self, request, bloquear):
        empresa = self.get_object()
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        # El servicio conserva el bloqueo automático y registra el cambio
        # manual, su motivo y su autor dentro de una transacción.
        cambiar_bloqueo_manual(empresa_id=empresa.pk, bloquear=bloquear,
            motivo=entrada.validated_data["motivo"], responsable=request.user)
        empresa = self.get_queryset().get(pk=empresa.pk)
        return Response(EmpresaLecturaSerializer(empresa, context=self.get_serializer_context()).data)

    @action(detail=True, methods=["post"])
    def bloquear(self, request, pk=None, format=None):
        return self.cambiar_bloqueo(request, bloquear=True)

    @action(detail=True, methods=["post"])
    def desbloquear(self, request, pk=None, format=None):
        return self.cambiar_bloqueo(request, bloquear=False)

    def listado_paginado(self, consulta, serializer):
        filtros = FiltroPaginaSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(consulta)
        datos = serializer(pagina, many=True, context=self.get_serializer_context()).data
        return self.get_paginated_response(datos)

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None, format=None):
        consulta = self.get_object().historial_bloqueos.select_related("responsable").order_by("-fecha", "-pk")
        return self.listado_paginado(consulta, HistorialBloqueoSerializer)

    @action(detail=True, methods=["get"])
    def atrasos(self, request, pk=None, format=None):
        empresa = self.get_object()
        consulta = arriendos_atrasados(empresa.pk).select_related(
            "maquinaria", "empresa", "responsable", "obra_destino",
            "bodega_origen", "bodega_recepcion", "aceptacion__terminos",
        ).order_by("devolucion_prevista", "pk")
        return self.listado_paginado(consulta, ArriendoLecturaSerializer)
