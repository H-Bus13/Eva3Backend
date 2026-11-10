from collections.abc import Mapping
"""Entradas estrictas que reutilizan las validaciones de los formularios."""
from rest_framework import serializers
from maquinaria.models import Usuario, HistorialAdministracionUsuario, HistorialSolicitud, TerminosCondiciones, AceptacionTerminos
from .serializers import EntradaEstricta, FiltroPaginaSerializer


class UsuarioLectura(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ("id", "username", "first_name", "last_name", "email", "rut", "rol", "empresa",
                  "is_active", "suspendida", "is_superuser", "estado_aprobacion")
        read_only_fields = fields


class PerfilEntrada(EntradaEstricta):
    first_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    last_name = serializers.CharField(max_length=150, allow_blank=True, required=False)
    email = serializers.EmailField(required=False)


class HistorialUsuarioLectura(serializers.ModelSerializer):
    class Meta:
        model = HistorialAdministracionUsuario
        fields = ("id", "usuario", "responsable", "accion", "motivo", "fecha", "datos_anteriores", "datos_nuevos")
        read_only_fields = fields


class HistorialSolicitudLectura(serializers.ModelSerializer):
    class Meta:
        model = HistorialSolicitud
        fields = ("id", "usuario", "tipo", "motivo", "fecha", "registrado_por", "empresa")
        read_only_fields = fields


class SolicitudLectura(UsuarioLectura):
    class Meta(UsuarioLectura.Meta):
        fields = UsuarioLectura.Meta.fields + ("motivo_revision", "revisado_en", "revisado_por")
        read_only_fields = fields


class TerminosLectura(serializers.ModelSerializer):
    class Meta:
        model = TerminosCondiciones
        fields = ("id", "version", "contenido", "publicado_en", "publicado_por")
        read_only_fields = fields


class AceptacionLectura(serializers.ModelSerializer):
    condiciones = TerminosLectura(source="terminos", read_only=True)

    class Meta:
        model = AceptacionTerminos
        fields = ("id", "usuario", "terminos", "condiciones", "aceptado_en", "firmado_en")
        read_only_fields = fields


class AceptarEntrada(EntradaEstricta):
    version_id = serializers.IntegerField(min_value=1)
    acepto = serializers.BooleanField()

    def validate_acepto(self, valor):
        if not valor:
            raise serializers.ValidationError("Debes aceptar las condiciones.")
        return valor


class FiltroCuenta(FiltroPaginaSerializer):
    q = serializers.CharField(max_length=100, required=False, allow_blank=True)
    rol = serializers.ChoiceField(choices=Usuario.Rol.choices, required=False)
    estado = serializers.ChoiceField(choices=["habilitada", "suspendida", "pendiente", "rechazada"], required=False)
    empresa = serializers.IntegerField(min_value=1, required=False)


def validar_formulario(clase, datos, *, permitidos=None, **kwargs):
    # Los formularios HTML ignoran campos extra. La API los rechaza antes
    # de validar para no aceptar silenciosamente privilegios manipulados.
    if not isinstance(datos, Mapping):
        raise serializers.ValidationError("Se espera un objeto JSON.")
    formulario = clase(data=datos, **kwargs)
    extras = set(datos) - set(permitidos if permitidos is not None else formulario.fields)
    if extras:
        raise serializers.ValidationError({campo: ["Campo no permitido."] for campo in sorted(extras)})
    if not formulario.is_valid():
        raise serializers.ValidationError({campo: list(errores) for campo, errores in formulario.errors.items()})
    return formulario


class FiltroSolicitudCuenta(FiltroPaginaSerializer):
    q = serializers.CharField(max_length=100, required=False, allow_blank=True)
    estado = serializers.ChoiceField(choices=["pendiente", "rechazada", "aprobada"], required=False)
    empresa = serializers.IntegerField(min_value=1, required=False)


class RevisionEntrada(EntradaEstricta):
    motivo = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
