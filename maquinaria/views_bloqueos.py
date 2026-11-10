from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms_bloqueos import BloqueoManualEmpresaForm
from .models import Empresa
from .servicios_bloqueos import actualizar_bloqueo_por_atraso, arriendos_atrasados, cambiar_bloqueo_manual, revisar_atrasos


def puede_ver_todas(usuario):
    return usuario.has_perm("maquinaria.gestionar_arriendos") or usuario.has_perm("maquinaria.gestionar_bloqueos_empresa")


def empresa_visible(usuario, pk):
    consulta = Empresa.objects.all() if puede_ver_todas(usuario) else Empresa.objects.filter(pk=usuario.empresa_id)
    return get_object_or_404(consulta, pk=pk)


@login_required
@never_cache
def alertas_atraso(request):
    globales = puede_ver_todas(request.user)
    if globales:
        revisar_atrasos()
        empresas = Empresa.objects.order_by("razon_social")
        atrasos = arriendos_atrasados()
        total_empresa = atrasos.count()
    else:
        empresas = Empresa.objects.filter(pk=request.user.empresa_id).order_by("razon_social")
        if request.user.empresa_id:
            actualizar_bloqueo_por_atraso(request.user.empresa_id)
            total_empresa = arriendos_atrasados(request.user.empresa_id).count()
        else:
            total_empresa = 0
        # El aviso es empresarial, pero el detalle de arriendos ajenos sigue
        # siendo privado, incluso entre usuarios de la misma empresa.
        atrasos = arriendos_atrasados().filter(responsable=request.user)
    if not request.user.has_perm("maquinaria.gestionar_arriendos"):
        atrasos = atrasos.filter(responsable=request.user)
    atrasos = atrasos.select_related("maquinaria", "empresa", "responsable").order_by("devolucion_prevista", "pk")
    return render(request, "maquinaria/alertas_atraso.html", {
        "globales": globales, "detalle_limitado": not request.user.has_perm("maquinaria.gestionar_arriendos"), "total_atrasos": total_empresa,
        "atrasos": Paginator(atrasos, 15).get_page(request.GET.get("atrasos_page")), "cantidad_visibles": atrasos.count(),
        "pagina_empresas": Paginator(empresas, 15).get_page(request.GET.get("page")),
    })


@login_required
@never_cache
def detalle_bloqueo_empresa(request, pk):
    empresa_visible(request.user, pk)
    empresa = actualizar_bloqueo_por_atraso(pk)
    return render(request, "maquinaria/detalle_bloqueo_empresa.html", {
        "empresa": empresa, "atrasos": arriendos_atrasados(pk).count(),
        "eventos": empresa.historial_bloqueos.select_related("responsable").all(),
    })


@login_required
@permission_required("maquinaria.gestionar_bloqueos_empresa", raise_exception=True)
@require_http_methods(["GET", "POST"])
def bloqueo_manual_empresa(request, pk, accion):
    if accion not in ("bloquear", "desbloquear"):
        raise Http404
    empresa = get_object_or_404(Empresa, pk=pk)
    form = BloqueoManualEmpresaForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            cambiar_bloqueo_manual(empresa_id=pk, bloquear=accion == "bloquear",
                motivo=form.cleaned_data["motivo"], responsable=request.user)
        except ValidationError as error:
            for mensaje in error.messages:
                form.add_error(None, mensaje)
        else:
            messages.success(request, "Cambio manual registrado. El bloqueo por atraso se evalúa por separado.")
            return redirect("detalle_bloqueo_empresa", pk=pk)
    return render(request, "maquinaria/form_bloqueo_empresa.html", {"form": form, "empresa": empresa, "accion": accion})


