from decimal import Decimal
from collections.abc import Mapping

from rest_framework import serializers

from maquinaria.models import Bodega, HistorialUbicacion, Maquinaria, MovimientoMaquinaria, Obra
from maquinaria.servicios_ubicaciones import bodegas_habilitadas


class EntradaEstricta(serializers.Serializer):
    def to_internal_value(self, data):
        # DRF normalmente ignora campos desconocidos. Aquí se rechazan para
        # que enviar estado, horas o privilegios no parezca una edición válida.
        if isinstance(data, Mapping):
            extras = set(data) - set(self.fields)
            if extras:
                raise serializers.ValidationError({campo: ["Este campo no se admite en esta operación."] for campo in sorted(extras)})
        return super().to_internal_value(data)


class MaquinariaLecturaSerializer(serializers.ModelSerializer):
    bodega_nombre = serializers.CharField(source="bodega.nombre", read_only=True)
    estado_nombre = serializers.CharField(source="get_estado_display", read_only=True)
    reservada = serializers.BooleanField(source="reserva_vigente", read_only=True)
    segundos_uso_total = serializers.SerializerMethodField()

    class Meta:
        model = Maquinaria
        fields = ("id", "codigo", "nombre", "marca", "modelo", "estado", "estado_nombre",
                  "bodega", "bodega_nombre", "revision_pendiente", "ultima_mantencion_conocida",
                  "tiempo_uso_inicial", "tiempo_uso_ultima_mantencion", "segundos_uso_total", "precio_diario", "moneda", "reservada")
        read_only_fields = fields

    def get_segundos_uso_total(self, obj):
        return obj.tiempo_uso_total.total_seconds()


class CrearMaquinariaSerializer(EntradaEstricta):
    precio_diario = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    codigo = serializers.CharField(max_length=30)
    nombre = serializers.CharField(max_length=120)
    marca = serializers.CharField(max_length=80, allow_blank=True, required=False, default="")
    modelo = serializers.CharField(max_length=80, allow_blank=True, required=False, default="")
    bodega = serializers.PrimaryKeyRelatedField(queryset=bodegas_habilitadas())
    horas_iniciales = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0)
    horas_ultima_mantencion = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0, allow_null=True, required=False, default=None)

    def validate_codigo(self, valor):
        codigo = valor.strip().upper()
        if Maquinaria.objects.filter(codigo__iexact=codigo).exists():
            raise serializers.ValidationError("Ya existe una máquina con este código.")
        return codigo

    def validate(self, datos):
        lectura = datos.get("horas_ultima_mantencion")
        if lectura is not None and lectura > datos["horas_iniciales"]:
            raise serializers.ValidationError({"horas_ultima_mantencion": "La lectura no puede superar las horas totales."})
        return datos


class EditarMaquinariaSerializer(EntradaEstricta):
    precio_diario = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"), required=False)
    nombre = serializers.CharField(max_length=120)
    marca = serializers.CharField(max_length=80, allow_blank=True)
    modelo = serializers.CharField(max_length=80, allow_blank=True)


class MotivoSerializer(EntradaEstricta):
    motivo = serializers.CharField(max_length=1000)


class TrasladarMaquinariaSerializer(MotivoSerializer):
    destino = serializers.PrimaryKeyRelatedField(queryset=bodegas_habilitadas())


class ObraLecturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Obra
        fields = ("id", "nombre", "direccion", "activa")
        read_only_fields = fields


class BodegaLecturaSerializer(serializers.ModelSerializer):
    obra_nombre = serializers.CharField(source="obra.nombre", read_only=True, allow_null=True, default=None)

    class Meta:
        model = Bodega
        fields = ("id", "nombre", "direccion", "obra", "obra_nombre", "activa")
        read_only_fields = fields


class UbicacionEntradaSerializer(EntradaEstricta):
    nombre = serializers.CharField(max_length=100)
    direccion = serializers.CharField(max_length=250)


class ObraEntradaSerializer(UbicacionEntradaSerializer):
    nombre = serializers.CharField(max_length=120)


class CrearBodegaSerializer(UbicacionEntradaSerializer):
    obra = serializers.PrimaryKeyRelatedField(queryset=Obra.objects.filter(activa=True), allow_null=True, required=False, default=None)


class FiltroPaginaSerializer(EntradaEstricta):
    page = serializers.IntegerField(min_value=1, required=False)
    format = serializers.ChoiceField(choices=["json"], required=False)


class FiltroMaquinariaSerializer(FiltroPaginaSerializer):
    q = serializers.CharField(max_length=100, required=False, allow_blank=True)
    estado = serializers.ChoiceField(choices=Maquinaria.Estado.choices, required=False, allow_blank=True)
    bodega = serializers.PrimaryKeyRelatedField(queryset=Bodega.objects.all(), required=False)


class FiltroUbicacionSerializer(FiltroPaginaSerializer):
    q = serializers.CharField(max_length=100, required=False, allow_blank=True)
    estado = serializers.ChoiceField(choices=["activas", "inactivas", "todas"], default="activas", required=False)


class FiltroBodegaSerializer(FiltroUbicacionSerializer):
    obra = serializers.PrimaryKeyRelatedField(queryset=Obra.objects.all(), required=False)


class MovimientoSerializer(serializers.ModelSerializer):
    tipo_nombre = serializers.CharField(source="get_tipo_display", read_only=True)
    responsable_nombre = serializers.CharField(source="registrado_por.username", read_only=True)

    class Meta:
        model = MovimientoMaquinaria
        fields = ("id", "tipo", "tipo_nombre", "origen", "destino", "estado_anterior", "estado_nuevo", "registrado_por", "responsable_nombre", "fecha", "motivo")
        read_only_fields = fields


class HistorialUbicacionSerializer(serializers.ModelSerializer):
    responsable_nombre = serializers.CharField(source="responsable.username", read_only=True)

    class Meta:
        model = HistorialUbicacion
        fields = ("id", "accion", "motivo", "fecha", "responsable", "responsable_nombre")
        read_only_fields = fields
