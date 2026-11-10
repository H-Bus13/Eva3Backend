from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from rest_framework.reverse import reverse

from maquinaria.forms import FirmaPerfilForm
from maquinaria.models import Arriendo, Empresa, Maquinaria, Obra, SesionUso, SolicitudDevolucion, SolicitudEntrega, Usuario
from maquinaria.servicios_ubicaciones import bodegas_habilitadas
from .serializers import EntradaEstricta, FiltroPaginaSerializer, MotivoSerializer


class ArriendoLecturaSerializer(serializers.ModelSerializer):
    maquinaria_nombre = serializers.CharField(source="maquinaria.nombre", read_only=True)
    estado = serializers.SerializerMethodField()
    condiciones_version = serializers.CharField(source="aceptacion.terminos.version", read_only=True)
    condiciones_contenido = serializers.CharField(source="aceptacion.terminos.contenido", read_only=True)
    firma_entrega_url = serializers.SerializerMethodField()
    firma_devolucion_url = serializers.SerializerMethodField()

    class Meta:
        model = Arriendo
        fields = ("id", "maquinaria", "maquinaria_nombre", "empresa", "responsable", "obra_destino", "direccion_uso", "comuna_uso", "indicaciones_acceso", "destino_legacy",
                  "entregado_en", "devolucion_prevista", "recibido_en", "devuelto_en", "estado",
                  "bodega_origen", "bodega_recepcion", "tarifa_diaria", "observaciones", "aceptacion",
                  "condiciones_version", "condiciones_contenido", "firma_entrega_url", "firma_devolucion_url")
        read_only_fields = fields

    def get_estado(self, obj):
        return "Cerrado" if obj.devuelto_en else "Recibido pendiente de firma" if obj.recibido_en else "Abierto"

    def get_firma_entrega_url(self, obj):
        return reverse("api-arriendo-firma-entrega", kwargs={"pk": obj.pk}, request=self.context.get("request")) if obj.firma_entrega else None

    def get_firma_devolucion_url(self, obj):
        return reverse("api-arriendo-firma-devolucion", kwargs={"pk": obj.pk}, request=self.context.get("request")) if obj.firma_devolucion else None


class PrepararEntregaSerializer(EntradaEstricta):
    maquinaria = serializers.PrimaryKeyRelatedField(queryset=Maquinaria.objects.all())
    empresa = serializers.PrimaryKeyRelatedField(queryset=Empresa.objects.all())
    responsable = serializers.PrimaryKeyRelatedField(queryset=Usuario.objects.all())
    direccion_uso = serializers.CharField(max_length=255)
    comuna_uso = serializers.CharField(max_length=100)
    indicaciones_acceso = serializers.CharField(max_length=3000, required=False, default="", allow_blank=True)
    devolucion_prevista = serializers.DateTimeField()
    tarifa_diaria = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    observaciones = serializers.CharField(allow_blank=True, required=False, default="", max_length=3000)

    def validate(self, datos):
        if datos["responsable"].empresa_id != datos["empresa"].pk:
            raise serializers.ValidationError({"responsable": "El responsable no pertenece a esa empresa."})
        if datos["devolucion_prevista"] <= timezone.now():
            raise serializers.ValidationError({"devolucion_prevista": "La fecha de devolución debe ser futura."})
        # El servicio vuelve a comprobar aprobación, bloqueos y disponibilidad
        # bajo transacción; no dependemos de un queryset que pudo quedar viejo.
        return datos


class EntregaLecturaSerializer(serializers.ModelSerializer):
    estado = serializers.CharField(read_only=True)
    maquinaria_nombre = serializers.CharField(source="maquinaria.nombre", read_only=True)
    condiciones_version = serializers.CharField(source="terminos.version", read_only=True)
    condiciones_contenido = serializers.CharField(source="terminos.contenido", read_only=True)

    class Meta:
        model = SolicitudEntrega
        fields = ("id", "maquinaria", "maquinaria_nombre", "empresa", "responsable", "obra_destino", "direccion_uso", "comuna_uso", "indicaciones_acceso", "destino_legacy", "terminos",
                  "condiciones_version", "condiciones_contenido", "devolucion_prevista", "tarifa_diaria", "observaciones",
                  "preparada_por", "creada_en", "vence_en", "cancelada_en", "cancelada_por", "motivo_cancelacion", "arriendo", "solicitud_arriendo", "estado")
        read_only_fields = fields


class RecepcionSerializer(EntradaEstricta):
    bodega = serializers.PrimaryKeyRelatedField(queryset=bodegas_habilitadas())
    observaciones = serializers.CharField(max_length=3000)
    requiere_revision = serializers.BooleanField(default=False)
    confirmar = serializers.BooleanField()

    def validate_confirmar(self, valor):
        if not valor:
            raise serializers.ValidationError("Confirma que recibiste físicamente el equipo.")
        return valor


class DevolucionLecturaSerializer(serializers.ModelSerializer):
    estado = serializers.CharField(read_only=True)
    maquinaria = serializers.IntegerField(source="arriendo.maquinaria_id", read_only=True)
    responsable = serializers.IntegerField(source="arriendo.responsable_id", read_only=True)

    class Meta:
        model = SolicitudDevolucion
        fields = ("id", "arriendo", "maquinaria", "responsable", "bodega", "observaciones", "requiere_revision",
                  "preparada_por", "creada_en", "vence_en", "cancelada_en", "cancelada_por", "motivo_cancelacion", "confirmada_en", "estado")
        read_only_fields = fields


class FirmaArriendoSerializer(EntradaEstricta):
    firma = serializers.FileField()
    confirmar = serializers.BooleanField()

    def validate_confirmar(self, valor):
        if not valor:
            raise serializers.ValidationError("Debes confirmar que revisaste la operación.")
        return valor

    def validate_firma(self, archivo):
        formulario = FirmaPerfilForm(data={}, files={"firma": archivo})
        if not formulario.is_valid():
            raise serializers.ValidationError(list(formulario.errors["firma"]))
        return formulario.cleaned_data["firma"]


class EntradaVaciaSerializer(EntradaEstricta):
    # Iniciar, pausar o sincronizar no acepta duraciones del navegador.
    pass


class FiltroArriendoSerializer(FiltroPaginaSerializer):
    estado = serializers.ChoiceField(choices=["", "abierto", "firma", "cerrado"], required=False)
    maquinaria = serializers.PrimaryKeyRelatedField(queryset=Maquinaria.objects.all(), required=False)


class FiltroSolicitudSerializer(FiltroPaginaSerializer):
    estado = serializers.ChoiceField(choices=["", "pendiente", "confirmada", "cancelada", "vencida"], required=False)


class SesionLecturaSerializer(serializers.ModelSerializer):
    segundos = serializers.SerializerMethodField()

    class Meta:
        model = SesionUso
        fields = ("id", "inicio", "fin", "iniciada_por", "cerrada_por", "motivo_cierre", "segundos")
        read_only_fields = fields

    def get_segundos(self, obj):
        duracion = (obj.fin or timezone.now()) - obj.inicio
        return duracion.total_seconds() if duracion.total_seconds() >= 0 else None
