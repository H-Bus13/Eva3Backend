from rest_framework import serializers

from maquinaria.models import Maquinaria, Mantenimiento
from .serializers import EntradaEstricta, FiltroPaginaSerializer


class MantenimientoLecturaSerializer(serializers.ModelSerializer):
    maquinaria_nombre = serializers.CharField(source="maquinaria.nombre", read_only=True)
    estado = serializers.CharField(read_only=True)
    vencida = serializers.BooleanField(read_only=True)

    class Meta:
        model = Mantenimiento
        fields = (
            "id", "maquinaria", "maquinaria_nombre", "fecha_programada", "descripcion",
            "estado", "vencida", "iniciado_en", "finalizado_en", "lectura_uso",
            "resultado", "apta_para_servicio", "programado_por", "responsable", "finalizado_por",
        )
        read_only_fields = fields


class ProgramarMantenimientoSerializer(EntradaEstricta):
    maquinaria = serializers.PrimaryKeyRelatedField(queryset=Maquinaria.objects.all())
    fecha_programada = serializers.DateField()
    descripcion = serializers.CharField(max_length=3000)


class ConfirmarMantenimientoSerializer(EntradaEstricta):
    confirmar = serializers.BooleanField()

    def validate_confirmar(self, valor):
        if not valor:
            raise serializers.ValidationError("Debes confirmar la operación.")
        return valor


class FinalizarMantenimientoSerializer(ConfirmarMantenimientoSerializer):
    resultado = serializers.CharField(max_length=3000)
    apta_para_servicio = serializers.BooleanField()


class FiltroMantenimientoSerializer(FiltroPaginaSerializer):
    estado = serializers.ChoiceField(
        choices=["pendiente", "curso", "finalizada"], required=False, allow_blank=True,
    )
    maquinaria = serializers.PrimaryKeyRelatedField(queryset=Maquinaria.objects.all(), required=False)
