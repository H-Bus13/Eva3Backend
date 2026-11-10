from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError, transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from .forms import RegistroContratistaForm, RevisionCuentaForm
from .models import Usuario, AceptacionTerminos, HistorialSolicitud
from .servicios_bloqueos import contexto_bloqueo
from .condiciones import es_contratista_firmante, exigir_contratista_firmante


def registro(request):
    if request.user.is_authenticated:
        return redirect("inicio")
    form = RegistroContratistaForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                form.save()
        except IntegrityError:
            # Otra solicitud podría registrar el mismo RUT o nombre de usuario
            # entre la validación y el guardado; se revierte toda la operación.
            form.add_error(None, "No se pudo registrar. Revisa si la cuenta ya existe.")
        else:
            messages.success(request, "Solicitud enviada. Puedes ingresar para consultar su estado. Un administrador debe verificar tu vínculo con la empresa antes de habilitar el acceso al sistema.")
            return redirect("login")
    return render(request, "maquinaria/registro.html", {"form": form})


@login_required
def inicio(request):
    return render(request, "maquinaria/inicio.html", {**contexto_bloqueo(request.user),
        "perfil_contratista": es_contratista_firmante(request.user)})


@login_required
@permission_required("maquinaria.aprobar_contratista", raise_exception=True)
def pendientes(request):
    usuarios = Usuario.objects.filter(
        rol=Usuario.Rol.CONTRATISTA,
        estado_aprobacion=Usuario.EstadoAprobacion.PENDIENTE,
        is_superuser=False, is_staff=False,
    ).select_related("empresa").prefetch_related("historial_solicitud__registrado_por", "historial_solicitud__empresa").order_by("date_joined")
    return render(request, "maquinaria/pendientes.html", {"cuentas": usuarios})


@login_required
@permission_required("maquinaria.aprobar_contratista", raise_exception=True)
@require_POST
def revisar_cuenta(request, pk):
    form = RevisionCuentaForm(request.POST)
    if not form.is_valid():
        # Si JavaScript está desactivado, el servidor también bloquea el
        # rechazo y muestra el motivo dentro de la pantalla de solicitudes.
        for errores in form.errors.values():
            for error in errores:
                messages.error(request, error)
        return redirect("pendientes")
    # El bloqueo de fila evita que dos administradores revisen simultáneamente
    # la misma solicitud. Solo se puede resolver una cuenta aún pendiente.
    with transaction.atomic():
        usuario = get_object_or_404(
            Usuario.objects.select_for_update(), pk=pk,
            rol=Usuario.Rol.CONTRATISTA,
            estado_aprobacion=Usuario.EstadoAprobacion.PENDIENTE,
            is_superuser=False, is_staff=False,
        )
        if usuario.pk == request.user.pk or usuario.empresa_id is None:
            return HttpResponseBadRequest("La cuenta no puede aprobarse en estas condiciones.")
        aprobado = form.cleaned_data["accion"] == "aprobar"
        usuario.estado_aprobacion = (
            Usuario.EstadoAprobacion.APROBADO if aprobado
            else Usuario.EstadoAprobacion.RECHAZADO
        )
        usuario.is_active = aprobado and not usuario.suspendida
        usuario.revisado_por = request.user
        usuario.revisado_en = timezone.now()
        usuario.motivo_revision = form.cleaned_data["motivo"]
        usuario.save(update_fields=[
            "estado_aprobacion", "is_active", "revisado_por", "revisado_en", "motivo_revision",
        ])
        HistorialSolicitud.objects.create(
            usuario=usuario,
            tipo=(HistorialSolicitud.Tipo.APROBACION if aprobado else HistorialSolicitud.Tipo.RECHAZO),
            motivo=usuario.motivo_revision, fecha=usuario.revisado_en,
            registrado_por=request.user, empresa=usuario.empresa,
        )
        # La aprobación de una persona no elimina el bloqueo de su empresa.
    messages.success(request, "La solicitud fue revisada.")
    return redirect("pendientes")


@login_required
@never_cache
def perfil(request):
    if not es_contratista_firmante(request.user):
        return render(request, "maquinaria/perfil.html", {"perfil_contratista": False})
    from .condiciones import aceptacion_temporal, obtener_terminos_vigentes

    terminos = obtener_terminos_vigentes()
    historial = request.user.aceptaciones.select_related("terminos").order_by("-firmado_en", "-pk")
    comprobante = historial.filter(terminos=terminos).first() if terminos else None
    return render(request, "maquinaria/perfil.html", {
        "perfil_contratista": True, "terminos": terminos, "comprobante": comprobante, **contexto_bloqueo(request.user),
        "historial": historial,
        "puede_firmar": bool(aceptacion_temporal(request, terminos)) and not comprobante,
    })


@login_required
@require_POST
def aceptar_terminos(request):
    exigir_contratista_firmante(request.user)
    from .condiciones import CLAVE_ACEPTACION, obtener_terminos_vigentes

    terminos = obtener_terminos_vigentes()
    if terminos is None:
        return HttpResponseBadRequest("Todavía no hay condiciones publicadas.")
    if request.POST.get("acepto") != "si":
        return HttpResponseBadRequest("Debes aceptar los términos y condiciones.")
    if request.POST.get("version_id") != str(terminos.pk):
        return HttpResponseBadRequest("Las condiciones cambiaron. Revisa la nueva versión.")
    # El navegador no decide la fecha ni la identidad de quien acepta.
    request.session[CLAVE_ACEPTACION] = {
        "usuario_id": request.user.pk, "terminos_id": terminos.pk,
        "aceptado_en": timezone.now().isoformat(),
    }
    return redirect("perfil")


@login_required
@require_POST
def guardar_firma(request):
    exigir_contratista_firmante(request.user)
    from uuid import uuid4
    from .condiciones import (
        CLAVE_ACEPTACION, aceptacion_temporal,
        bloquear_publicacion, obtener_terminos_vigentes,
    )
    from .forms import FirmaPerfilForm

    terminos = obtener_terminos_vigentes()
    if aceptacion_temporal(request, terminos) is None:
        return HttpResponseBadRequest("Primero acepta las condiciones vigentes. La aceptación vence a los 30 minutos.")
    form = FirmaPerfilForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, form.errors.as_text())
        return redirect("perfil")

    comprobante = None
    try:
        with transaction.atomic():
            # Serializa envíos dobles de la misma persona. Publicación y firma
            # comparten además el bloqueo de la última versión de condiciones.
            firmante = Usuario.objects.select_for_update().get(pk=request.user.pk)
            exigir_contratista_firmante(firmante)
            bloquear_publicacion()
            terminos = obtener_terminos_vigentes()
            aceptado_en = aceptacion_temporal(request, terminos)
            if aceptado_en is None:
                return HttpResponseBadRequest("Las condiciones cambiaron o la aceptación venció. Vuelve a aceptar.")
            if not AceptacionTerminos.objects.filter(usuario=request.user, terminos=terminos).exists():
                comprobante = AceptacionTerminos(
                    usuario=request.user, terminos=terminos,
                    aceptado_en=aceptado_en, firmado_en=timezone.now(),
                )
                comprobante.firma.save(f"{uuid4().hex}.png", form.cleaned_data["firma"], save=False)
                comprobante.full_clean()
                comprobante.save()
    except Exception:
        # El almacenamiento de archivos no participa en la transacción SQL.
        # Si falla incluso el commit, se elimina el archivo recién creado.
        if comprobante is not None and comprobante.firma.name:
            comprobante.firma.delete(save=False)
        raise
    request.session.pop(CLAVE_ACEPTACION, None)
    messages.success(request, "Tu aceptación y firma quedaron registradas.")
    return redirect("perfil")


@login_required
@permission_required("maquinaria.publicar_terminos", raise_exception=True)
def publicar_terminos(request):
    from .condiciones import bloquear_publicacion
    from .forms import PublicarTerminosForm
    from .models import TerminosCondiciones

    form = PublicarTerminosForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                bloquear_publicacion()
                # El formulario solo crea versiones; nunca edita las previas.
                terminos = form.save(commit=False)
                terminos.publicado_por = request.user
                terminos.publicado_en = timezone.now()
                terminos.save()
        except IntegrityError:
            form.add_error("version", "Esa versión ya fue publicada. Usa otro identificador.")
        else:
            messages.success(request, "Nueva versión publicada. Se conservaron las aceptaciones anteriores.")
            return redirect("publicar_terminos")
    return render(request, "maquinaria/publicar_terminos.html", {
        "form": form,
        "versiones": TerminosCondiciones.objects.select_related("publicado_por").order_by("-publicado_en", "-pk"),
    })


@login_required
@never_cache
def ver_comprobante(request, pk):
    from django.http import FileResponse, Http404
    from .models import AceptacionTerminos

    # Se restringe la consulta antes de buscar el ID, sin exponer comprobantes
    # ajenos. No hay ruta pública /media/ para acceder a estas imágenes.
    consulta = AceptacionTerminos.objects.select_related("terminos", "usuario")
    if not request.user.has_perm("maquinaria.consultar_firmas"):
        consulta = consulta.filter(usuario=request.user)
    comprobante = get_object_or_404(consulta, pk=pk)
    return render(request, "maquinaria/comprobante.html", {"comprobante": comprobante})


@login_required
@never_cache
def ver_firma(request, pk):
    from django.http import FileResponse, Http404
    from .models import AceptacionTerminos

    consulta = AceptacionTerminos.objects.all()
    if not request.user.has_perm("maquinaria.consultar_firmas"):
        consulta = consulta.filter(usuario=request.user)
    comprobante = get_object_or_404(consulta, pk=pk)
    try:
        archivo = comprobante.firma.open("rb")
    except (FileNotFoundError, OSError, ValueError):
        raise Http404("No se encontró el archivo de firma.")
    respuesta = FileResponse(archivo, content_type="image/png", filename="firma.png")
    # Evita conservar imágenes privadas en cachés compartidas o del navegador.
    respuesta["Cache-Control"] = "private, no-store"
    respuesta["X-Content-Type-Options"] = "nosniff"
    return respuesta








