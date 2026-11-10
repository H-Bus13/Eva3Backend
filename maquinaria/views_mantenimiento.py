from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms_mantenimiento import FiltroMantenimientoForm, FinalizarMantenimientoForm, IniciarMantenimientoForm, ProgramarMantenimientoForm
from .models import Mantenimiento
from .servicios_mantenimiento import finalizar_mantenimiento, iniciar_mantenimiento, programar_mantenimiento


def errores_formulario(form, error):
    for mensaje in error.messages:
        form.add_error(None, mensaje)


@login_required
@permission_required("maquinaria.view_mantenimiento", raise_exception=True)
def mantenciones(request):
    form = FiltroMantenimientoForm(request.GET)
    consulta = Mantenimiento.objects.select_related("maquinaria", "responsable").order_by("fecha_programada", "pk")
    if form.is_valid():
        estado = form.cleaned_data["estado"]
        if estado == "pendiente":
            consulta = consulta.filter(iniciado_en__isnull=True, finalizado_en__isnull=True)
        elif estado == "curso":
            consulta = consulta.filter(iniciado_en__isnull=False, finalizado_en__isnull=True)
        elif estado == "finalizada":
            consulta = consulta.filter(finalizado_en__isnull=False)
        if form.cleaned_data["maquinaria"]:
            consulta = consulta.filter(maquinaria=form.cleaned_data["maquinaria"])
    else:
        consulta = consulta.none()
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(request, "maquinaria/mantenciones.html", {
        "form": form, "pagina": Paginator(consulta, 15).get_page(request.GET.get("page")),
        "filtros": parametros.urlencode(),
    })


@login_required
@permission_required("maquinaria.view_mantenimiento", raise_exception=True)
def detalle_mantenimiento(request, pk):
    orden = get_object_or_404(Mantenimiento.objects.select_related("maquinaria__bodega", "responsable", "programado_por", "finalizado_por"), pk=pk)
    return render(request, "maquinaria/detalle_mantenimiento.html", {"orden": orden})


@login_required
@permission_required("maquinaria.add_mantenimiento", raise_exception=True)
@require_http_methods(["GET", "POST"])
def nueva_mantencion(request):
    form = ProgramarMantenimientoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            orden = programar_mantenimiento(datos=form.cleaned_data, responsable=request.user)
        except ValidationError as error:
            errores_formulario(form, error)
        else:
            messages.success(request, "Mantención programada.")
            if request.user.has_perm("maquinaria.view_mantenimiento"):
                return redirect("detalle_mantenimiento", pk=orden.pk)
            return redirect("detalle_maquinaria", pk=orden.maquinaria_id)
    return render(request, "maquinaria/form_mantenimiento.html", {"form": form, "titulo": "Programar mantención", "programando": True})


@login_required
@require_http_methods(["GET", "POST"])
def operacion_mantenimiento(request, pk, accion):
    from django.http import Http404
    from .permisos import exigir_permiso
    opciones = {
        "iniciar": ("iniciar_mantenimiento", IniciarMantenimientoForm, "Iniciar mantención"),
        "finalizar": ("finalizar_mantenimiento", FinalizarMantenimientoForm, "Finalizar mantención"),
    }
    if accion not in opciones:
        raise Http404
    permiso, formulario, titulo = opciones[accion]
    exigir_permiso(request.user, permiso)
    orden = get_object_or_404(Mantenimiento.objects.select_related("maquinaria"), pk=pk)
    form = formulario(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            if accion == "iniciar":
                iniciar_mantenimiento(mantenimiento_id=pk, responsable=request.user)
            else:
                finalizar_mantenimiento(mantenimiento_id=pk, resultado=form.cleaned_data["resultado"],
                                         apta=form.cleaned_data["apta_para_servicio"], responsable=request.user)
        except ValidationError as error:
            errores_formulario(form, error)
        else:
            messages.success(request, "Operación registrada. Revisa el estado final del equipo en su detalle.")
            if request.user.has_perm("maquinaria.view_mantenimiento"):
                return redirect("detalle_mantenimiento", pk=pk)
            return redirect("detalle_maquinaria", pk=orden.maquinaria_id)
    return render(request, "maquinaria/form_mantenimiento.html", {"form": form, "titulo": titulo, "orden": orden})
