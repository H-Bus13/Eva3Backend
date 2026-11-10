from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms_maquinaria import ActividadUbicacionForm
from .models import Bodega, Obra, Usuario
from .permisos import exigir_permiso
from .servicios_ubicaciones import cambiar_actividad_ubicacion


def obtener_ubicacion(tipo, pk):
    modelos = {"obra": Obra, "bodega": Bodega}
    if tipo not in modelos:
        raise Http404
    return get_object_or_404(modelos[tipo], pk=pk)


@login_required
@require_http_methods(["GET", "POST"])
def actividad_ubicacion(request, tipo, pk, accion):
    if accion not in ("desactivar", "reactivar") or tipo not in ("obra", "bodega"):
        raise Http404
    exigir_permiso(request.user, f"{accion}_{tipo}")
    if accion == "reactivar" and not (request.user.is_superuser or request.user.rol == Usuario.Rol.ADMINISTRADOR):
        raise PermissionDenied
    ubicacion = obtener_ubicacion(tipo, pk)
    form = ActividadUbicacionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            cambiar_actividad_ubicacion(tipo=tipo, pk=pk, activar=accion == "reactivar",
                                       motivo=form.cleaned_data["motivo"], responsable=request.user)
        except ValidationError as error:
            for mensaje in error.messages:
                form.add_error(None, mensaje)
        else:
            messages.success(request, "Cambio registrado. Se conservaron los equipos y el historial de la ubicación.")
            return redirect("historial_ubicacion", tipo=tipo, pk=pk)
    return render(request, "maquinaria/actividad_ubicacion.html", {
        "form": form, "ubicacion": ubicacion, "tipo": tipo, "accion": accion,
        "titulo": f"{'Reactivar' if accion == 'reactivar' else 'Desactivar'} {tipo}",
    })


@login_required
def historial_ubicacion(request, tipo, pk):
    ubicacion = obtener_ubicacion(tipo, pk)
    return render(request, "maquinaria/historial_ubicacion.html", {
        "ubicacion": ubicacion, "tipo": tipo,
        "eventos": ubicacion.historial_actividad.select_related("responsable").all(),
    })
