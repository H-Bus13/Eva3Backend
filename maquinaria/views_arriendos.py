from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms_arriendos import CancelarSolicitudForm, FiltroArriendoForm, FirmaArriendoForm, PrepararDevolucionForm, PrepararEntregaForm
from .models import Arriendo, SolicitudDevolucion, SolicitudEntrega
from .servicios_bloqueos import contexto_bloqueo, revisar_atrasos
from .servicios_arriendos import cancelar_solicitud, confirmar_devolucion, confirmar_entrega, preparar_devolucion, preparar_entrega


from .consultas_arriendos import consulta_arriendos, consulta_solicitudes


def errores(form, error):
    for mensaje in error.messages:
        form.add_error(None, mensaje)


@login_required
@never_cache
def arriendos(request):
    form = FiltroArriendoForm(request.GET)
    consulta = consulta_arriendos(request.user).order_by("-entregado_en", "-pk")
    if form.is_valid():
        estado = form.cleaned_data["estado"]
        if estado == "abierto":
            consulta = consulta.filter(devuelto_en__isnull=True)
        elif estado == "firma":
            consulta = consulta.filter(devuelto_en__isnull=True, recibido_en__isnull=False)
        elif estado == "cerrado":
            consulta = consulta.filter(devuelto_en__isnull=False)
    else:
        consulta = consulta.none()
    parametros = request.GET.copy()
    parametros.pop("page", None)
    return render(request, "maquinaria/arriendos.html", {
        **contexto_bloqueo(request.user), "form": form, "pagina": Paginator(consulta, 15).get_page(request.GET.get("page")), "filtros": parametros.urlencode(),
        "entregas": consulta_solicitudes(request.user, "entrega").order_by("-creada_en", "-pk")[:30],
        "recepciones": consulta_solicitudes(request.user, "devolucion").order_by("-creada_en", "-pk")[:30],
    })


@login_required
@never_cache
def detalle_arriendo(request, pk):
    arriendo = get_object_or_404(consulta_arriendos(request.user), pk=pk)
    from .servicios_uso import estado_uso
    try:
        uso = estado_uso(arriendo_id=pk, usuario=request.user)
        error_uso = ""
    except ValidationError as error:
        uso, error_uso = None, " ".join(error.messages)
    return render(request, "maquinaria/detalle_arriendo.html", {
        "arriendo": arriendo, "uso": uso, "error_uso": error_uso,
        "sesiones": arriendo.sesiones_uso.select_related("iniciada_por", "cerrada_por").order_by("-inicio", "-pk"),
        "recepciones": arriendo.recepciones.select_related("bodega", "preparada_por", "cancelada_por").order_by("-creada_en", "-pk"),
    })


@login_required
@permission_required("maquinaria.gestionar_arriendos", raise_exception=True)
@require_http_methods(["GET", "POST"])
def nueva_entrega(request):
    revisar_atrasos()
    form = PrepararEntregaForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            solicitud = preparar_entrega(datos=form.cleaned_data, responsable=request.user)
        except ValidationError as error:
            errores(form, error)
        else:
            messages.success(request, "Entrega preparada. No reserva el equipo: el responsable debe ingresar a su cuenta y firmar.")
            return redirect("solicitud_arriendo", tipo="entrega", pk=solicitud.pk)
    return render(request, "maquinaria/form_arriendo.html", {"form": form, "titulo": "Preparar entrega", "nota": "El responsable debe tener firmadas las condiciones vigentes. La disponibilidad se verifica de nuevo al confirmar. La solicitud vence en una hora."})


@login_required
@permission_required("maquinaria.gestionar_arriendos", raise_exception=True)
@require_http_methods(["GET", "POST"])
def nueva_devolucion(request, pk):
    arriendo = get_object_or_404(consulta_arriendos(request.user), pk=pk)
    form = PrepararDevolucionForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            solicitud = preparar_devolucion(arriendo_id=pk, datos=form.cleaned_data, responsable=request.user)
        except ValidationError as error:
            errores(form, error)
        except IntegrityError:
            form.add_error(None, "Ya hay una recepción pendiente para este arriendo.")
        else:
            messages.success(request, "Recepción física registrada y sesiones de trabajo cerradas. Falta la firma del responsable.")
            return redirect("solicitud_arriendo", tipo="devolucion", pk=solicitud.pk)
    return render(request, "maquinaria/form_arriendo.html", {"form": form, "arriendo": arriendo, "titulo": "Recibir devolución", "nota": "Confirma solo cuando el equipo esté físicamente en la bodega elegida. Se cerrarán sus sesiones. Cancelar esta solicitud después no deshace la recepción ni permite volver a trabajar con el equipo."})


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def solicitud_arriendo(request, tipo, pk):
    solicitud = get_object_or_404(consulta_solicitudes(request.user, tipo), pk=pk)
    responsable_id = solicitud.responsable_id if tipo == "entrega" else solicitud.arriendo.responsable_id
    puede_firmar = request.user.pk == responsable_id and solicitud.estado == "Pendiente de firma"
    form = FirmaArriendoForm(request.POST if request.method == "POST" else None, request.FILES if request.method == "POST" else None)
    if request.method == "POST":
        if request.user.pk != responsable_id:
            raise PermissionDenied
        if form.is_valid():
            try:
                servicio = confirmar_entrega if tipo == "entrega" else confirmar_devolucion
                arriendo = servicio(solicitud_id=pk, usuario=request.user, firma=form.cleaned_data["firma"])
            except ValidationError as error:
                errores(form, error)
            except IntegrityError:
                form.add_error(None, "La operación cambió mientras firmabas. Revisa el estado del arriendo.")
            else:
                messages.success(request, "Firma y operación registradas.")
                return redirect("detalle_arriendo", pk=arriendo.pk)
    return render(request, "maquinaria/solicitud_arriendo.html", {"solicitud": solicitud, "tipo": tipo, "form": form, "puede_firmar": puede_firmar})


@login_required
@permission_required("maquinaria.gestionar_arriendos", raise_exception=True)
@require_http_methods(["GET", "POST"])
def cancelar_solicitud_view(request, tipo, pk):
    solicitud = get_object_or_404(consulta_solicitudes(request.user, tipo), pk=pk)
    form = CancelarSolicitudForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            cancelar_solicitud(tipo=tipo, pk=pk, motivo=form.cleaned_data["motivo"], responsable=request.user)
        except ValidationError as error:
            errores(form, error)
        else:
            messages.success(request, "Solicitud cancelada. Sus antecedentes se conservaron.")
            return redirect("solicitud_arriendo", tipo=tipo, pk=pk)
    return render(request, "maquinaria/form_arriendo.html", {"form": form, "titulo": f"Cancelar solicitud de {tipo} #{solicitud.pk}", "nota": "Cancelar una recepción no elimina la recepción física ni reinicia el contador de trabajo. Si hay un error, prepara una nueva recepción con los antecedentes corregidos."})


@login_required
@never_cache
def firma_arriendo(request, pk, tipo):
    if tipo not in ("entrega", "devolucion"):
        raise Http404
    arriendo = get_object_or_404(consulta_arriendos(request.user), pk=pk)
    campo = arriendo.firma_entrega if tipo == "entrega" else arriendo.firma_devolucion
    try:
        archivo = campo.open("rb")
    except (OSError, ValueError):
        raise Http404("No se encontró la firma.")
    respuesta = FileResponse(archivo, content_type="image/png", filename="firma.png")
    respuesta["Cache-Control"] = "private, no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta



