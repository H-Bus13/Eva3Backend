from decimal import Decimal
from django.utils import timezone
from rest_framework import serializers
from rest_framework.reverse import reverse
from maquinaria.models import SolicitudArriendo, Maquinaria, Obra, HistorialSolicitudArriendo
from .serializers import FiltroPaginaSerializer
from .serializers_arriendos import FirmaArriendoSerializer


class CrearPeticionSerializer(FirmaArriendoSerializer):
    maquinaria = serializers.PrimaryKeyRelatedField(queryset=Maquinaria.objects.all())
    direccion_uso = serializers.CharField(max_length=255)
    comuna_uso = serializers.CharField(max_length=100)
    indicaciones_acceso = serializers.CharField(max_length=3000, required=False, default="", allow_blank=True)
    devolucion_prevista = serializers.DateTimeField()
    observaciones = serializers.CharField(required=False, default="", allow_blank=True, max_length=3000)
    version_id = serializers.IntegerField(min_value=1)
    precio_visto = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    acepto = serializers.BooleanField()

    def validate_acepto(self, valor):
        if not valor:
            raise serializers.ValidationError("Debes aceptar las condiciones.")
        return valor

    def validate_devolucion_prevista(self, valor):
        if valor <= timezone.now():
            raise serializers.ValidationError("La devolución debe ser futura.")
        return valor


class PeticionLecturaSerializer(serializers.ModelSerializer):
    estado_actual = serializers.CharField(read_only=True)
    maquinaria_nombre = serializers.CharField(source="maquinaria.nombre", read_only=True)
    condiciones_version = serializers.CharField(source="terminos.version", read_only=True)
    condiciones_contenido = serializers.CharField(source="terminos.contenido", read_only=True)
    firma_url = serializers.SerializerMethodField()

    class Meta:
        model = SolicitudArriendo
        fields = ("id", "maquinaria", "maquinaria_nombre", "empresa", "solicitante", "obra_destino", "direccion_uso", "comuna_uso", "indicaciones_acceso", "destino_legacy", "creada_en",
            "devolucion_prevista", "observaciones", "precio_diario_acordado", "moneda", "terminos",
            "condiciones_version", "condiciones_contenido", "aceptado_en", "firmado_en", "estado", "estado_actual",
            "revisada_por", "revisada_en", "motivo_revision", "reserva_hasta", "cancelada_por", "cancelada_en",
            "motivo_cancelacion", "arriendo", "firma_url")
        read_only_fields = fields

    def get_firma_url(self, obj):
        return reverse("api-peticion-firma", kwargs={"pk": obj.pk}, request=self.context.get("request"))


class HistorialPeticionSerializer(serializers.ModelSerializer):
    class Meta:
        model = HistorialSolicitudArriendo
        fields = ("id", "solicitud", "estado_anterior", "estado_nuevo", "fecha", "responsable", "motivo")
        read_only_fields = fields


class FiltroPeticionSerializer(FiltroPaginaSerializer):
    estado = serializers.ChoiceField(choices=SolicitudArriendo.Estado.choices, required=False)
    maquinaria = serializers.IntegerField(min_value=1, required=False)
