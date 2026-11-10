from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms_usuarios import CrearUsuarioInternoForm, EditarDatosUsuarioForm, EstadoUsuarioForm, FiltroUsuariosForm, PermisosUsuarioForm
from .models import Usuario
from .politica_usuarios import permisos_efectivos
from .servicios_usuarios import (cambiar_estado_usuario, cambiar_permisos_usuario, crear_usuario_interno,
                               editar_datos_usuario, exigir_administrador, validar_destino)


def errores(form, error):
    for mensaje in error.messages:
        form.add_error(None, mensaje)


@login_required
@never_cache
def usuarios(request):
    exigir_administrador(request.user)
    form = FiltroUsuariosForm(request.GET)
    consulta = Usuario.objects.select_related("empresa").order_by("username")
    if form.is_valid():
        datos = form.cleaned_data
        if datos["q"]:
            q = datos["q"]
            consulta = consulta.filter(Q(username__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(rut__icontains=q) | Q(email__icontains=q))
        if datos["rol"] == "ADMINISTRADOR":
            consulta = consulta.filter(Q(rol="ADMINISTRADOR") | Q(is_superuser=True))
        elif datos["rol"] == "CONTRATISTA":
            consulta = consulta.filter(rol="CONTRATISTA", is_superuser=False)
        elif datos["rol"]:
            consulta = consulta.filter(rol=datos["rol"], is_superuser=False)
        if datos["empresa"]:
            consulta = consulta.filter(empresa=datos["empresa"])
        if datos["estado"] == "suspendida":
            consulta = consulta.filter(suspendida=True)
        elif datos["estado"] == "habilitada":
            consulta = consulta.filter(is_active=True, suspendida=False).filter(Q(is_superuser=True) | ~Q(rol="CONTRATISTA") | Q(estado_aprobacion="APROBADO"))
        elif datos["estado"] in ("pendiente", "rechazada"):
            consulta = consulta.filter(rol="CONTRATISTA", is_superuser=False,
                estado_aprobacion="PENDIENTE" if datos["estado"] == "pendiente" else "RECHAZADO")
    else:
        consulta = consulta.none()
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "maquinaria/usuarios.html", {"form": form, "pagina": Paginator(consulta, 15).get_page(request.GET.get("page")), "filtros": params.urlencode()})


@login_required
@never_cache
def detalle_usuario(request, pk):
    exigir_administrador(request.user)
    destino = get_object_or_404(Usuario.objects.select_related("empresa"), pk=pk)
    editable = False
    try:
        validar_destino(request.user, destino)
        editable = True
    except (ValidationError, PermissionDenied):
        pass

    return render(request, "maquinaria/detalle_usuario.html", {
        "destino": destino, "editable": editable,
        "permisos_destino": permisos_efectivos(destino).order_by("content_type__app_label", "codename"),
        "eventos": destino.historial_administracion.select_related("responsable").all(),
        "es_interna": destino.rol != "CONTRATISTA" or destino.is_superuser,
    })


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def nuevo_usuario(request):
    exigir_administrador(request.user)
    form = CrearUsuarioInternoForm(request.POST if request.method == "POST" else None, actor=request.user)
    if request.method == "POST" and form.is_valid():
        try:
            destino = crear_usuario_interno(datos=form.cleaned_data, actor=request.user)
        except ValidationError as error:
            errores(form, error)
        except IntegrityError:
            form.add_error(None, "El usuario o RUT ya fue registrado mientras completabas el formulario.")
        else:
            messages.success(request, "Cuenta interna creada con su perfil inicial de permisos.")
            return redirect("detalle_usuario", pk=destino.pk)
    return render(request, "maquinaria/form_usuario.html", {"form": form, "titulo": "Crear cuenta interna", "creando": True})


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def editar_usuario(request, pk, accion):
    exigir_administrador(request.user)
    destino = get_object_or_404(Usuario, pk=pk)
    try:
        validar_destino(request.user, destino)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
        return redirect("detalle_usuario", pk=pk)
    if accion == "datos":
        form = EditarDatosUsuarioForm(request.POST if request.method == "POST" else None, instance=destino)
        titulo = "Editar datos de cuenta"
    elif accion == "permisos":
        if destino.rol == "CONTRATISTA" and not destino.is_superuser:
            messages.error(request, "Los contratistas no reciben permisos internos desde esta pantalla.")
            return redirect("detalle_usuario", pk=pk)
        form = PermisosUsuarioForm(request.POST if request.method == "POST" else None, actor=request.user, destino=destino)
        titulo = "Rol y permisos"
    elif accion in ("activar", "desactivar"):
        form = EstadoUsuarioForm(request.POST if request.method == "POST" else None)
        titulo = "Activar cuenta" if accion == "activar" else "Suspender cuenta"
    else:
        raise Http404
    if request.method == "POST" and form.is_valid():
        try:
            if accion == "datos":
                editar_datos_usuario(usuario_id=pk, datos=form.cleaned_data, actor=request.user)
            elif accion == "permisos":
                cambiar_permisos_usuario(usuario_id=pk, datos=form.cleaned_data, actor=request.user)
            else:
                cambiar_estado_usuario(usuario_id=pk, activar=accion == "activar", motivo=form.cleaned_data["motivo"], actor=request.user)
        except ValidationError as error:
            errores(form, error)
        else:
            messages.success(request, "Cambio de cuenta registrado en el historial.")
            return redirect("detalle_usuario", pk=pk)
    return render(request, "maquinaria/form_usuario.html", {"form": form, "titulo": titulo, "destino": destino, "accion": accion})


