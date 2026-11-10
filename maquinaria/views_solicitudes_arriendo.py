from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .models import Maquinaria
from .condiciones import obtener_terminos_vigentes
from .forms_solicitudes_arriendo import SolicitarArriendoForm, MotivoPeticionForm
from .servicios_solicitudes_arriendo import consultar, solicitar, revisar, cancelar, preparar_desde_solicitud
from .reservas import vencer_reservas


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def nueva_peticion(request, maquinaria_id):
    if request.user.rol != "CONTRATISTA" or request.user.is_staff or request.user.is_superuser:
        raise PermissionDenied("Solo los contratistas pueden solicitar maquinaria.")
    maquina = get_object_or_404(Maquinaria, pk=maquinaria_id)
    terminos = obtener_terminos_vigentes()
    form = SolicitarArriendoForm(request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None,
        initial={"version_id": terminos.pk if terminos else None, "precio_visto": maquina.precio_diario})
    if request.method == "POST" and form.is_valid():
        try:
            solicitud = solicitar(datos={**form.cleaned_data, "maquinaria": maquina},
                firma=form.cleaned_data["firma"], usuario=request.user)
        except ValidationError as error:
            form.add_error(None, " ".join(error.messages))
        except IntegrityError:
            form.add_error(None, "Ya hay una solicitud activa o cambió la disponibilidad. Revisa tus solicitudes.")
        else:
            messages.success(request, "Solicitud enviada para revisión. Todavía no reserva la máquina.")
            return redirect("detalle_peticion", pk=solicitud.pk)
    return render(request, "maquinaria/nueva_peticion.html", {"form": form, "maquina": maquina, "terminos": terminos})


@login_required
@never_cache
def peticiones(request):
    consulta = consultar(request.user).order_by("-creada_en", "-pk")
    # Las consultas muestran vencimientos sin escribir datos ajenos. La
    # transición persistida se realiza por comando o al intentar operar.
    estado = request.GET.get("estado", "")
    from .models import SolicitudArriendo
    from django.db.models import Q
    from django.utils import timezone
    if estado == "VENCIDA":
        consulta = consulta.filter(Q(estado="VENCIDA") | Q(estado="APROBADA", reserva_hasta__lte=timezone.now()))
    elif estado == "APROBADA":
        consulta = consulta.filter(estado="APROBADA", reserva_hasta__gt=timezone.now())
    elif estado in SolicitudArriendo.Estado.values:
        consulta = consulta.filter(estado=estado)
    elif estado:
        consulta = consulta.none()
    return render(request, "maquinaria/peticiones.html", {"pagina": Paginator(consulta, 20).get_page(request.GET.get("page")),
        "estados": SolicitudArriendo.Estado.choices, "estado": estado})


@login_required
@never_cache
def detalle_peticion(request, pk):
    solicitud = get_object_or_404(consultar(request.user), pk=pk)
    from django.utils import timezone
    vencida = solicitud.estado == "APROBADA" and solicitud.reserva_hasta <= timezone.now()
    return render(request, "maquinaria/detalle_peticion.html", {"solicitud": solicitud, "vencida": vencida,
        "form": MotivoPeticionForm(), "eventos": solicitud.historial.select_related("responsable").all()})


@login_required
@require_POST
def operar_peticion(request, pk, accion):
    solicitud = get_object_or_404(consultar(request.user), pk=pk)
    if accion not in ("aprobar", "rechazar", "cancelar", "entregar"):
        raise Http404
    try:
        if accion == "entregar":
            if request.POST.get("confirmar") != "si":
                raise ValidationError("Confirma que prepararás la entrega física.")
            entrega = preparar_desde_solicitud(solicitud_id=pk, actor=request.user)
            return redirect("solicitud_arriendo", tipo="entrega", pk=entrega.pk)
        form = MotivoPeticionForm(request.POST)
        if not form.is_valid():
            raise ValidationError([str(error) for errores in form.errors.values() for error in errores])
        if accion == "cancelar":
            cancelar(solicitud_id=pk, motivo=form.cleaned_data["motivo"], usuario=request.user)
        else:
            revisar(solicitud_id=pk, aprobar=accion == "aprobar", motivo=form.cleaned_data["motivo"], actor=request.user)
    except ValidationError as error:
        messages.error(request, " ".join(error.messages))
    except IntegrityError:
        messages.error(request, "Otra operación cambió la solicitud o la reserva. Actualiza la pantalla.")
    else:
        messages.success(request, "Operación registrada.")
    return redirect("detalle_peticion", pk=pk)


@login_required
@never_cache
def firma_peticion(request, pk):
    solicitud = get_object_or_404(consultar(request.user), pk=pk)
    try:
        archivo = solicitud.firma_solicitud.open("rb")
    except (OSError, ValueError):
        raise Http404("No se encontró la firma.")
    respuesta = FileResponse(archivo, content_type="image/png", filename="firma-solicitud.png")
    respuesta["Cache-Control"] = "private, no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta
