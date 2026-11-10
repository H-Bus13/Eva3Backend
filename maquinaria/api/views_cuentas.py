from collections.abc import Mapping
from django.contrib.auth import login, logout
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import mixins, viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny, BasePermission
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError

from maquinaria.models import Usuario, TerminosCondiciones, AceptacionTerminos
from maquinaria.forms import (RegistroContratistaForm, AccesoConSolicitudForm, ReenviarSolicitudForm,
                              RevisionCuentaForm, PublicarTerminosForm)
from maquinaria.forms_usuarios import (CrearUsuarioInternoForm, EditarDatosUsuarioForm,
                                      PermisosUsuarioForm, EstadoUsuarioForm)
from maquinaria.servicios_usuarios import (exigir_administrador, crear_usuario_interno, editar_datos_usuario,
    cambiar_permisos_usuario, cambiar_estado_usuario)
from maquinaria.politica_usuarios import permisos_otorgables, permisos_efectivos
from maquinaria.solicitudes import obtener_solicitante, iniciar_consulta_solicitud, CLAVE_CONSULTA
from maquinaria.condiciones import obtener_terminos_vigentes, bloquear_publicacion, CLAVE_ACEPTACION
from maquinaria.condiciones import es_contratista_firmante, exigir_contratista_firmante
from maquinaria.servicios_cuentas_api import revisar_solicitud_api, reenviar_solicitud_api, firmar_perfil_api
from .permissions import CuentaHabilitada
from .renderers import PNGPrivadoRenderer
from .serializers import FiltroPaginaSerializer
from .serializers_arriendos import FirmaArriendoSerializer
from .serializers_cuentas import (UsuarioLectura, PerfilEntrada, HistorialUsuarioLectura,
    HistorialSolicitudLectura, SolicitudLectura, TerminosLectura, AceptacionLectura,
    AceptarEntrada, FiltroCuenta, FiltroSolicitudCuenta, RevisionEntrada, validar_formulario)


class AdministrarUsuarios(BasePermission):
    def has_permission(self, request, view):
        exigir_administrador(request.user)
        return True


class RevisarSolicitudes(BasePermission):
    def has_permission(self, request, view):
        return request.user.has_perm("maquinaria.aprobar_contratista")


@method_decorator(never_cache, name="dispatch")
class BaseCuentas(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    http_method_names = ["get", "post", "patch", "head", "options"]

    def paginar(self, consulta, clase):
        entrada = FiltroPaginaSerializer(data=self.request.query_params)
        entrada.is_valid(raise_exception=True)
        pagina = self.paginate_queryset(consulta)
        return self.get_paginated_response(clase(pagina, many=True).data)


class UsuarioViewSet(BaseCuentas):
    permission_classes = [CuentaHabilitada, AdministrarUsuarios]
    serializer_class = UsuarioLectura

    def get_queryset(self):
        consulta = Usuario.objects.select_related("empresa").order_by("username", "pk")
        if self.action != "list":
            return consulta
        filtro = FiltroCuenta(data=self.request.query_params)
        filtro.is_valid(raise_exception=True)
        datos = filtro.validated_data
        if datos.get("q"):
            q = datos["q"]
            consulta = consulta.filter(Q(username__icontains=q) | Q(first_name__icontains=q) |
                Q(last_name__icontains=q) | Q(rut__icontains=q) | Q(email__icontains=q))
        rol = datos.get("rol")
        if rol == "ADMINISTRADOR":
            consulta = consulta.filter(Q(rol=rol) | Q(is_superuser=True))
        elif rol:
            consulta = consulta.filter(rol=rol, is_superuser=False)
        if datos.get("empresa"):
            consulta = consulta.filter(empresa_id=datos["empresa"])
        estado = datos.get("estado")
        if estado == "suspendida":
            consulta = consulta.filter(suspendida=True)
        elif estado in ("pendiente", "rechazada"):
            consulta = consulta.filter(rol="CONTRATISTA", is_superuser=False,
                estado_aprobacion="PENDIENTE" if estado == "pendiente" else "RECHAZADO")
        elif estado == "habilitada":
            consulta = consulta.filter(is_active=True, suspendida=False).filter(
                Q(is_superuser=True) | ~Q(rol="CONTRATISTA") | Q(estado_aprobacion="APROBADO"))
        return consulta

    def create(self, request, format=None):
        form = validar_formulario(CrearUsuarioInternoForm, request.data, actor=request.user)
        usuario = crear_usuario_interno(datos=form.cleaned_data, actor=request.user)
        return Response(UsuarioLectura(usuario).data, status=201)

    def partial_update(self, request, pk=None, format=None):
        destino = self.get_object()
        permitidos = {"first_name", "last_name", "email", "motivo"}
        # Se completan los campos omitidos para que PATCH no borre otros datos.
        datos = {campo: getattr(destino, campo) for campo in ("first_name", "last_name", "email")}
        if not isinstance(request.data, Mapping):
            raise ValidationError("Se espera un objeto JSON.")
        datos.update(request.data)
        form = validar_formulario(EditarDatosUsuarioForm, datos, permitidos=permitidos, instance=destino)
        usuario = editar_datos_usuario(usuario_id=destino.pk, datos={campo: form.cleaned_data[campo] for campo in request.data}, actor=request.user)
        return Response(UsuarioLectura(usuario).data)

    @action(detail=False, methods=["get"], url_path="permisos-disponibles")
    def permisos_disponibles(self, request, format=None):
        filtro = FiltroPaginaSerializer(data=request.query_params)
        filtro.is_valid(raise_exception=True)
        return Response(list(permisos_otorgables(request.user).values("id", "codename", "name")))

    @action(detail=True, methods=["get", "post"])
    def permisos(self, request, pk=None, format=None):
        destino = self.get_object()
        if request.method == "POST":
            form = validar_formulario(PermisosUsuarioForm, request.data, actor=request.user, destino=destino)
            cambiar_permisos_usuario(usuario_id=destino.pk, datos=form.cleaned_data, actor=request.user)
            destino = self.get_queryset().get(pk=destino.pk)
        return Response({"usuario": destino.pk, "rol": destino.rol, "superusuario": destino.is_superuser,
            "permisos": list(permisos_efectivos(destino).values("id", "codename", "name"))})

    def estado(self, request, activar):
        destino = self.get_object()
        form = validar_formulario(EstadoUsuarioForm, request.data)
        usuario = cambiar_estado_usuario(usuario_id=destino.pk, activar=activar,
            motivo=form.cleaned_data["motivo"], actor=request.user)
        return Response(UsuarioLectura(usuario).data)

    @action(detail=True, methods=["post"])
    def suspender(self, request, pk=None, format=None):
        return self.estado(request, False)

    @action(detail=True, methods=["post"])
    def reactivar(self, request, pk=None, format=None):
        return self.estado(request, True)

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None, format=None):
        return self.paginar(self.get_object().historial_administracion.order_by("-fecha", "-pk"), HistorialUsuarioLectura)


class SolicitudViewSet(BaseCuentas):
    permission_classes = [CuentaHabilitada, RevisarSolicitudes]
    serializer_class = SolicitudLectura

    def get_queryset(self):
        consulta = Usuario.objects.filter(rol="CONTRATISTA", is_staff=False, is_superuser=False).order_by("date_joined", "pk")
        if self.action == "list":
            filtro = FiltroSolicitudCuenta(data=self.request.query_params)
            filtro.is_valid(raise_exception=True)
            datos = filtro.validated_data
            if datos.get("estado"):
                estados = {"pendiente": "PENDIENTE", "rechazada": "RECHAZADO", "aprobada": "APROBADO"}
                consulta = consulta.filter(estado_aprobacion=estados[datos["estado"]])
            if datos.get("q"):
                consulta = consulta.filter(username__icontains=datos["q"])
            if datos.get("empresa"):
                consulta = consulta.filter(empresa_id=datos["empresa"])
        return consulta

    def revisar(self, request, accion):
        usuario = self.get_object()
        entrada = RevisionEntrada(data=request.data)
        entrada.is_valid(raise_exception=True)
        # Se valida la acción fijada por la ruta, nunca una enviada por el cliente.
        form = validar_formulario(RevisionCuentaForm, {"accion": accion, "motivo": entrada.validated_data["motivo"]})
        usuario = revisar_solicitud_api(pk=usuario.pk, datos=form.cleaned_data, actor=request.user)
        return Response(SolicitudLectura(usuario).data)

    @action(detail=True, methods=["post"])
    def aprobar(self, request, pk=None, format=None):
        return self.revisar(request, "aprobar")

    @action(detail=True, methods=["post"])
    def rechazar(self, request, pk=None, format=None):
        return self.revisar(request, "rechazar")

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None, format=None):
        return self.paginar(self.get_object().historial_solicitud.order_by("-fecha", "-pk"), HistorialSolicitudLectura)


# También se exige CSRF para POST anónimos y sesiones limitadas.
# Se usa el verificador de DRF para conservar los errores en JSON.
@method_decorator(never_cache, name="dispatch")
class AccesoAPI(APIView):
    permission_classes = [AllowAny]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            SessionAuthentication().enforce_csrf(request)

    def get(self, request, operacion):
        if operacion == "csrf":
            return Response({"csrfToken": get_token(request)})
        if operacion == "solicitud":
            usuario = obtener_solicitante(request)
            if usuario is None:
                raise PermissionDenied("Ingresa para consultar tu solicitud.")
            return Response({"solicitud": SolicitudLectura(usuario).data,
                "historial": HistorialSolicitudLectura(usuario.historial_solicitud.all(), many=True).data})
        raise Http404

    def post(self, request, operacion):
        if operacion == "salir":
            logout(request)
            return Response({"detalle": "Sesión cerrada."})
        if request.user.is_authenticated:
            raise ValidationError("Cierra tu sesión antes de usar este acceso.")
        if operacion == "registro":
            form = validar_formulario(RegistroContratistaForm, request.data)
            with transaction.atomic():
                form.save()
            return Response({"detalle": "Solicitud registrada y pendiente de aprobación."}, status=201)
        if operacion == "ingresar":
            form = validar_formulario(AccesoConSolicitudForm, request.data, request=request._request)
            usuario = form.get_user()
            logout(request)
            if form.acceso_limitado:
                iniciar_consulta_solicitud(request, usuario)
                return Response({"acceso": "solicitud", "estado": usuario.estado_aprobacion})
            login(request, usuario)
            request.session.pop(CLAVE_CONSULTA, None)
            return Response({"acceso": "sistema"})
        if operacion == "reenviar":
            solicitante = obtener_solicitante(request)
            if solicitante is None:
                raise PermissionDenied("Ingresa para consultar tu solicitud.")
            form = validar_formulario(ReenviarSolicitudForm, request.data)
            usuario = reenviar_solicitud_api(solicitante=solicitante, formulario=form)
            return Response(SolicitudLectura(usuario).data)
        raise Http404


@method_decorator(never_cache, name="dispatch")
class PerfilAPI(APIView):
    permission_classes = [CuentaHabilitada]

    def get(self, request):
        if not es_contratista_firmante(request.user):
            return Response({"usuario": UsuarioLectura(request.user).data, "puede_firmar_condiciones": False})
        vigente = obtener_terminos_vigentes()
        return Response({"usuario": UsuarioLectura(request.user).data,
            "condiciones_vigentes": TerminosLectura(vigente).data if vigente else None,
            "aceptaciones": AceptacionLectura(request.user.aceptaciones.select_related("terminos").order_by("-firmado_en", "-pk"), many=True).data})

    def patch(self, request):
        entrada = PerfilEntrada(data=request.data)
        entrada.is_valid(raise_exception=True)
        with transaction.atomic():
            usuario = Usuario.objects.select_for_update().get(pk=request.user.pk)
            if not usuario.is_active or usuario.suspendida:
                raise PermissionDenied()
            for campo, valor in entrada.validated_data.items():
                setattr(usuario, campo, valor)
            usuario.full_clean()
            usuario.save(update_fields=list(entrada.validated_data))
        return Response(UsuarioLectura(usuario).data)


class AceptarAPI(PerfilAPI):
    http_method_names = ["post", "options"]

    def check_permissions(self, request):
        super().check_permissions(request)
        exigir_contratista_firmante(request.user)
    def get(self, request):
        raise Http404

    def post(self, request):
        entrada = AceptarEntrada(data=request.data)
        entrada.is_valid(raise_exception=True)
        vigente = obtener_terminos_vigentes()
        if vigente is None or vigente.pk != entrada.validated_data["version_id"]:
            raise ValidationError("Revisa las condiciones vigentes.")
        request.session[CLAVE_ACEPTACION] = {"usuario_id": request.user.pk,
            "terminos_id": vigente.pk, "aceptado_en": timezone.now().isoformat()}
        return Response({"detalle": "Aceptación temporal registrada. Firma dentro de 30 minutos."})


class FirmarAPI(PerfilAPI):
    http_method_names = ["post", "options"]

    def check_permissions(self, request):
        super().check_permissions(request)
        exigir_contratista_firmante(request.user)
    parser_classes = [MultiPartParser]

    def get(self, request):
        raise Http404

    def post(self, request):
        entrada = FirmaArriendoSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        comprobante = firmar_perfil_api(request=request, archivo=entrada.validated_data["firma"])
        return Response(AceptacionLectura(comprobante).data)


class TerminosViewSet(BaseCuentas):
    permission_classes = [CuentaHabilitada]
    serializer_class = TerminosLectura

    def get_queryset(self):
        return TerminosCondiciones.objects.filter(publicado_en__lte=timezone.now()).order_by("-publicado_en", "-pk")

    def create(self, request, format=None):
        if not request.user.has_perm("maquinaria.publicar_terminos"):
            raise PermissionDenied()
        form = validar_formulario(PublicarTerminosForm, request.data)
        with transaction.atomic():
            bloquear_publicacion()
            terminos = form.save(commit=False)
            terminos.publicado_por = request.user
            terminos.publicado_en = timezone.now()
            terminos.save()
        return Response(TerminosLectura(terminos).data, status=201)

    def list(self, request, *args, **kwargs):
        filtro = FiltroPaginaSerializer(data=request.query_params)
        filtro.is_valid(raise_exception=True)
        return super().list(request, *args, **kwargs)


class ComprobanteViewSet(BaseCuentas):
    permission_classes = [CuentaHabilitada]
    serializer_class = AceptacionLectura

    def get_queryset(self):
        consulta = AceptacionTerminos.objects.select_related("terminos").order_by("-firmado_en", "-pk")
        return consulta if self.request.user.has_perm("maquinaria.consultar_firmas") else consulta.filter(usuario=self.request.user)

    def list(self, request, *args, **kwargs):
        filtro = FiltroPaginaSerializer(data=request.query_params)
        filtro.is_valid(raise_exception=True)
        return super().list(request, *args, **kwargs)

    @action(detail=True, methods=["get"], renderer_classes=[JSONRenderer, PNGPrivadoRenderer])
    def firma(self, request, pk=None, format=None):
        try:
            archivo = self.get_object().firma.open("rb")
        except (OSError, ValueError):
            raise Http404("No se encontró la firma.")
        respuesta = FileResponse(archivo, content_type="image/png", filename="firma-perfil.png")
        respuesta["Cache-Control"] = "private, no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta
