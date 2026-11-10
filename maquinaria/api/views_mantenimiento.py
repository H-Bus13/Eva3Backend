from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from maquinaria.models import Mantenimiento
from maquinaria.servicios_mantenimiento import (
    programar_mantenimiento, iniciar_mantenimiento, finalizar_mantenimiento,
)
from .permissions import CuentaHabilitada
from .permissions_mantenimiento import PermisosMantenimiento
from .serializers_mantenimiento import (
    MantenimientoLecturaSerializer, ProgramarMantenimientoSerializer,
    ConfirmarMantenimientoSerializer, FinalizarMantenimientoSerializer,
    FiltroMantenimientoSerializer,
)


class MantenimientoViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [CuentaHabilitada, PermisosMantenimiento]
    serializer_class = MantenimientoLecturaSerializer
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        consulta = Mantenimiento.objects.select_related(
            "maquinaria", "programado_por", "responsable", "finalizado_por",
        ).order_by("fecha_programada", "pk")
        if self.action != "list":
            return consulta

        filtros = FiltroMantenimientoSerializer(data=self.request.query_params)
        filtros.is_valid(raise_exception=True)
        datos = filtros.validated_data
        estado = datos.get("estado")
        if estado == "pendiente":
            consulta = consulta.filter(iniciado_en__isnull=True, finalizado_en__isnull=True)
        elif estado == "curso":
            consulta = consulta.filter(iniciado_en__isnull=False, finalizado_en__isnull=True)
        elif estado == "finalizada":
            consulta = consulta.filter(finalizado_en__isnull=False)
        if datos.get("maquinaria"):
            consulta = consulta.filter(maquinaria=datos["maquinaria"])
        return consulta

    def get_serializer_class(self):
        entradas = {
            "create": ProgramarMantenimientoSerializer,
            "iniciar": ConfirmarMantenimientoSerializer,
            "finalizar": FinalizarMantenimientoSerializer,
        }
        return entradas.get(self.action, MantenimientoLecturaSerializer)

    def validar_entrada(self, request):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        return entrada.validated_data

    def respuesta_orden(self, orden, codigo=200):
        return Response(MantenimientoLecturaSerializer(
            orden, context=self.get_serializer_context(),
        ).data, status=codigo)

    def create(self, request, format=None):
        datos = self.validar_entrada(request)
        # El servicio bloquea el equipo y comprueba disponibilidad y permisos
        # antes de crear la orden y su movimiento de historial.
        orden = programar_mantenimiento(datos=datos, responsable=request.user)
        return self.respuesta_orden(orden, status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def iniciar(self, request, pk=None, format=None):
        orden = self.get_object()
        self.validar_entrada(request)
        orden = iniciar_mantenimiento(mantenimiento_id=orden.pk, responsable=request.user)
        return self.respuesta_orden(orden)

    @action(detail=True, methods=["post"])
    def finalizar(self, request, pk=None, format=None):
        orden = self.get_object()
        datos = self.validar_entrada(request)
        # El servicio conserva las horas totales y decide si quedan otras
        # revisiones exigibles antes de liberar el equipo.
        orden = finalizar_mantenimiento(
            mantenimiento_id=orden.pk, resultado=datos["resultado"],
            apta=datos["apta_para_servicio"], responsable=request.user,
        )
        return self.respuesta_orden(orden)
