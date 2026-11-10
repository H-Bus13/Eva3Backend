from rest_framework import serializers

from maquinaria.models import Empresa, HistorialBloqueoEmpresa
from .serializers import EntradaEstricta, FiltroPaginaSerializer


class EmpresaLecturaSerializer(serializers.ModelSerializer):
    bloqueo_por_atraso_actual = serializers.BooleanField(source="atraso_actual", read_only=True)
    tiene_bloqueo = serializers.SerializerMethodField()

    class Meta:
        model = Empresa
        fields = ("id", "rut", "razon_social", "bloqueada", "motivo_bloqueo",
                  "bloqueada_por_atraso", "bloqueo_por_atraso_actual", "tiene_bloqueo")
        read_only_fields = fields

    def get_tiene_bloqueo(self, obj):
        # La consulta aporta el atraso actual sin depender de la última
        # ejecución de la revisión automática guardada en la empresa.
        return obj.bloqueada or obj.atraso_actual


class HistorialBloqueoSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistorialBloqueoEmpresa
        fields = ("id", "empresa", "origen", "accion", "motivo", "fecha", "responsable")
        read_only_fields = fields


class CambioBloqueoSerializer(EntradaEstricta):
    motivo = serializers.CharField(max_length=1000)


class FiltroEmpresaSerializer(FiltroPaginaSerializer):
    q = serializers.CharField(required=False, allow_blank=True, max_length=150)
    estado = serializers.ChoiceField(
        choices=["todas", "bloqueadas", "habilitadas"], required=False, default="todas",
    )
