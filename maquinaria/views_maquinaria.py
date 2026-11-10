from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms_maquinaria import (
    BodegaForm, CrearMaquinariaForm, EditarMaquinariaForm, FiltroCatalogoForm,
    ObraForm, OperacionMaquinariaForm, TrasladarMaquinariaForm, FiltroUbicacionesForm,
)
from .models import Bodega, Maquinaria, Obra, Usuario
from .servicios_maquinaria import crear_maquinaria, editar_maquinaria, exigir_permiso, operar_maquinaria
from .servicios_ubicaciones import bodegas_habilitadas, guardar_ubicacion


def errores_operacion(form, error):
    for mensaje in error.messages:
        form.add_error(None, mensaje)


@login_required
def catalogo(request):
    form = FiltroCatalogoForm(request.GET)
    consulta = Maquinaria.objects.select_related("bodega__obra").order_by("codigo")
    if form.is_valid():
        datos = form.cleaned_data
        if datos["q"]:
            consulta = consulta.filter(Q(codigo__icontains=datos["q"]) | Q(nombre__icontains=datos["q"]))
        if datos["estado"]:
            consulta = consulta.filter(estado=datos["estado"])
        if datos["bodega"]:
            consulta = consulta.filter(bodega=datos["bodega"])
    else:
        consulta = consulta.none()
    pagina = Paginator(consulta, 12).get_page(request.GET.get("page"))
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(request, "maquinaria/catalogo.html", {"form": form, "pagina": pagina, "filtros": parametros.urlencode()})


@login_required
def detalle_maquinaria(request, pk):
    maquina = get_object_or_404(Maquinaria.objects.select_related("bodega__obra", "registrado_por"), pk=pk)
    eventos = maquina.movimientos.select_related("origen__obra", "destino__obra", "registrado_por").order_by("-fecha", "-pk")
    return render(request, "maquinaria/detalle_maquinaria.html", {
        "maquina": maquina, "eventos": eventos,
        "puede_reactivar": request.user.has_perm("maquinaria.reactivar_maquinaria") and (request.user.is_superuser or request.user.rol == Usuario.Rol.ADMINISTRADOR) and maquina.bodega.activa and (not maquina.bodega.obra_id or maquina.bodega.obra.activa),
        "ubicacion_inactiva": not maquina.bodega.activa or (maquina.bodega.obra_id and not maquina.bodega.obra.activa),
    })


@login_required
@permission_required("maquinaria.add_maquinaria", raise_exception=True)
@require_http_methods(["GET", "POST"])
def nueva_maquinaria(request):
    form = CrearMaquinariaForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            maquina = crear_maquinaria(datos=form.cleaned_data, responsable=request.user)
        except ValidationError as error:
            errores_operacion(form, error)
        except IntegrityError:
            form.add_error(None, "No se pudo guardar. Revisa que el código no esté registrado.")
        else:
            messages.success(request, "Maquinaria registrada con su lectura e historial inicial.")
            return redirect("detalle_maquinaria", pk=maquina.pk)
    return render(request, "maquinaria/form_maquinaria.html", {"form": form, "titulo": "Registrar maquinaria", "es_alta": True})


@login_required
@permission_required("maquinaria.change_maquinaria", raise_exception=True)
@require_http_methods(["GET", "POST"])
def editar_maquinaria_view(request, pk):
    maquina = get_object_or_404(Maquinaria, pk=pk)
    form = EditarMaquinariaForm(request.POST if request.method == "POST" else None, instance=maquina)
    if request.method == "POST" and form.is_valid():
        try:
            editar_maquinaria(maquinaria_id=pk, datos=form.cleaned_data, responsable=request.user)
        except ValidationError as error:
            errores_operacion(form, error)
        else:
            messages.success(request, "Datos del equipo actualizados.")
            return redirect("detalle_maquinaria", pk=pk)
    return render(request, "maquinaria/form_maquinaria.html", {"form": form, "titulo": f"Editar {maquina.codigo}", "maquina": maquina})


@login_required
@require_http_methods(["GET", "POST"])
def operacion_maquinaria(request, pk, accion):
    opciones = {
        "trasladar": ("trasladar_maquinaria", "Trasladar maquinaria", TrasladarMaquinariaForm),
        "baja": ("dar_baja_maquinaria", "Dar de baja maquinaria", OperacionMaquinariaForm),
        "reactivar": ("reactivar_maquinaria", "Reactivar maquinaria para revisión", OperacionMaquinariaForm),
    }
    if accion not in opciones:
        raise Http404
    permiso, titulo, formulario = opciones[accion]
    exigir_permiso(request.user, permiso)
    if accion == "reactivar" and not (request.user.is_superuser or request.user.rol == Usuario.Rol.ADMINISTRADOR):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied
    maquina = get_object_or_404(Maquinaria.objects.select_related("bodega__obra"), pk=pk)
    form = formulario(request.POST if request.method == "POST" else None)
    if accion == "trasladar":
        form.fields["destino"].queryset = bodegas_habilitadas().exclude(pk=maquina.bodega_id)
    if request.method == "POST" and form.is_valid():
        try:
            operar_maquinaria(maquinaria_id=pk, accion=accion, motivo=form.cleaned_data["motivo"],
                              destino=form.cleaned_data.get("destino"), responsable=request.user)
        except ValidationError as error:
            errores_operacion(form, error)
        else:
            messages.success(request, "Operación registrada en el historial del equipo.")
            return redirect("detalle_maquinaria", pk=pk)
    return render(request, "maquinaria/operacion_maquinaria.html", {"form": form, "maquina": maquina, "titulo": titulo, "accion": accion})


@login_required
def ubicaciones(request):
    form = FiltroUbicacionesForm(request.GET or {"estado": "activas"})
    obras = Obra.objects.order_by("nombre")
    bodegas = Bodega.objects.select_related("obra").order_by("nombre")
    if form.is_valid():
        estado = form.cleaned_data["estado"]
        if estado != "todas":
            obras = obras.filter(activa=estado == "activas")
            bodegas = bodegas.filter(activa=estado == "activas")
    else:
        obras, bodegas = obras.none(), bodegas.none()
    return render(request, "maquinaria/ubicaciones.html", {
        "obras": obras, "bodegas": bodegas, "form": form,
        "es_administrador": request.user.is_superuser or request.user.rol == Usuario.Rol.ADMINISTRADOR,
    })


@login_required
@require_http_methods(["GET", "POST"])
def ubicacion_form(request, tipo, pk=None):
    opciones = {"obra": (Obra, ObraForm), "bodega": (Bodega, BodegaForm)}
    if tipo not in opciones:
        raise Http404
    modelo, formulario = opciones[tipo]
    exigir_permiso(request.user, f"{'change' if pk is not None else 'add'}_{tipo}")
    instancia = get_object_or_404(modelo, pk=pk) if pk is not None else None
    form = formulario(request.POST if request.method == "POST" else None, instance=instancia)
    if request.method == "POST" and form.is_valid():
        try:
            guardar_ubicacion(tipo=tipo, pk=pk, datos=form.cleaned_data, responsable=request.user)
        except ValidationError as error:
            errores_operacion(form, error)
        else:
            messages.success(request, "Ubicación guardada.")
            return redirect("ubicaciones")
    return render(request, "maquinaria/form_ubicacion.html", {
        "form": form, "titulo": f"{'Editar' if pk is not None else 'Registrar'} {tipo}",
        "bodega_existente": tipo == "bodega" and pk is not None,
    })



