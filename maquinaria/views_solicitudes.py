from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.views import LoginView
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .forms import AccesoConSolicitudForm, ReenviarSolicitudForm
from .models import HistorialSolicitud, Usuario
from .solicitudes import CLAVE_CONSULTA, iniciar_consulta_solicitud, obtener_solicitante


class IngresoConSolicitudView(LoginView):
    template_name = "maquinaria/login.html"
    authentication_form = AccesoConSolicitudForm

    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("inicio")
        if obtener_solicitante(request) is not None:
            return redirect("estado_solicitud")
        request.session.pop(CLAVE_CONSULTA, None)
        return super().get(request, *args, **kwargs)

    def form_valid(self, form):
        if form.acceso_limitado:
            # Elimina cualquier sesión anterior antes de guardar la identidad
            # limitada. Nunca se convierte en una sesión normal de Django.
            logout(self.request)
            iniciar_consulta_solicitud(self.request, form.get_user())
            return redirect("estado_solicitud")
        self.request.session.pop(CLAVE_CONSULTA, None)
        return super().form_valid(form)


def mostrar_estado(request, solicitante, form=None):
    if form is None:
        form = ReenviarSolicitudForm(initial={
            "rut_empresa": solicitante.empresa.rut if solicitante.empresa else "",
            "razon_social": solicitante.empresa.razon_social if solicitante.empresa else "",
        })
    # Una aprobación se informa, pero para acceder al sistema deberá ingresar
    # otra vez. Eliminar esta clave evita un bucle entre login y estado.
    if solicitante.estado_aprobacion == Usuario.EstadoAprobacion.APROBADO:
        request.session.pop(CLAVE_CONSULTA, None)
    return render(request, "maquinaria/estado_solicitud.html", {
        "solo_solicitud": True, "solicitante": solicitante, "form": form,
        "historial": solicitante.historial_solicitud.select_related("registrado_por", "empresa").all(),
    })


@never_cache
@require_GET
def estado_solicitud(request):
    if request.user.is_authenticated:
        return redirect("inicio")
    solicitante = obtener_solicitante(request)
    if solicitante is None:
        request.session.pop(CLAVE_CONSULTA, None)
        return redirect("login")
    return mostrar_estado(request, solicitante)


@never_cache
@require_POST
def reenviar_solicitud(request):
    if request.user.is_authenticated:
        return redirect("inicio")
    solicitante = obtener_solicitante(request)
    if solicitante is None:
        request.session.pop(CLAVE_CONSULTA, None)
        return redirect("login")
    form = ReenviarSolicitudForm(request.POST)
    if not form.is_valid():
        return mostrar_estado(request, solicitante, form)
    try:
        with transaction.atomic():
            # La fila se vuelve a consultar bajo bloqueo. Un reenvío no puede
            # anular una aprobación ni duplicarse mediante solicitudes paralelas.
            usuario = Usuario.objects.select_for_update().get(pk=solicitante.pk)
            if usuario.estado_aprobacion != Usuario.EstadoAprobacion.RECHAZADO:
                messages.error(request, "Solo puedes reenviar una solicitud rechazada.")
                return redirect("estado_solicitud")
            empresa = form.obtener_empresa()
            usuario.empresa = empresa
            usuario.estado_aprobacion = Usuario.EstadoAprobacion.PENDIENTE
            usuario.is_active = False
            usuario.revisado_por = None
            usuario.revisado_en = None
            usuario.motivo_revision = ""
            usuario.save(update_fields=[
                "empresa", "estado_aprobacion", "is_active", "revisado_por",
                "revisado_en", "motivo_revision",
            ])
            HistorialSolicitud.objects.create(
                usuario=usuario, tipo=HistorialSolicitud.Tipo.REENVIO,
                motivo=form.cleaned_data["comentario"],
                registrado_por=usuario, empresa=empresa,
            )
    except IntegrityError:
        form.add_error(None, "No se pudo reenviar la solicitud. Revisa los datos e inténtalo otra vez.")
        return mostrar_estado(request, solicitante, form)
    messages.success(request, "Solicitud reenviada. Queda pendiente de una nueva revisión.")
    return redirect("estado_solicitud")
