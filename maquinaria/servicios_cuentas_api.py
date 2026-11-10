from uuid import uuid4
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Usuario, HistorialSolicitud, AceptacionTerminos
from .condiciones import bloquear_publicacion, obtener_terminos_vigentes, aceptacion_temporal, CLAVE_ACEPTACION
from .permisos import exigir_permiso
from .condiciones import exigir_contratista_firmante


@transaction.atomic
def revisar_solicitud_api(*, pk, datos, actor):
    exigir_permiso(actor, "aprobar_contratista")
    usuario = Usuario.objects.select_for_update().get(pk=pk, rol="CONTRATISTA", is_superuser=False, is_staff=False)
    if usuario.estado_aprobacion != "PENDIENTE" or usuario.pk == actor.pk or not usuario.empresa_id:
        raise ValidationError("La solicitud no está pendiente o no puede revisarse.")
    aprobado = datos["accion"] == "aprobar"
    usuario.estado_aprobacion = "APROBADO" if aprobado else "RECHAZADO"
    usuario.is_active = aprobado and not usuario.suspendida
    usuario.revisado_por = actor
    usuario.revisado_en = timezone.now()
    usuario.motivo_revision = datos["motivo"]
    usuario.save(update_fields=["estado_aprobacion", "is_active", "revisado_por", "revisado_en", "motivo_revision"])
    HistorialSolicitud.objects.create(usuario=usuario, tipo="APROBACION" if aprobado else "RECHAZO",
        motivo=usuario.motivo_revision, fecha=usuario.revisado_en, registrado_por=actor, empresa=usuario.empresa)
    return usuario


@transaction.atomic
def reenviar_solicitud_api(*, solicitante, formulario):
    usuario = Usuario.objects.select_for_update().get(pk=solicitante.pk)
    if usuario.suspendida or usuario.is_staff or usuario.is_superuser or usuario.rol != "CONTRATISTA" or usuario.estado_aprobacion != "RECHAZADO":
        raise ValidationError("Solo puedes reenviar una solicitud rechazada y no suspendida.")
    usuario.empresa = formulario.obtener_empresa()
    usuario.estado_aprobacion = "PENDIENTE"
    usuario.is_active = False
    usuario.revisado_por = None
    usuario.revisado_en = None
    usuario.motivo_revision = ""
    usuario.save(update_fields=["empresa", "estado_aprobacion", "is_active", "revisado_por", "revisado_en", "motivo_revision"])
    HistorialSolicitud.objects.create(usuario=usuario, tipo="REENVIO", motivo=formulario.cleaned_data["comentario"],
        registrado_por=usuario, empresa=usuario.empresa)
    return usuario


def firmar_perfil_api(*, request, archivo):
    exigir_contratista_firmante(request.user)
    comprobante = None
    try:
        with transaction.atomic():
            # La misma persona y la publicación se bloquean igual que en
            # templates. Nunca se reutiliza una aceptación de otra versión.
            usuario = Usuario.objects.select_for_update().get(pk=request.user.pk)
            exigir_contratista_firmante(usuario)
            if not usuario.is_active or usuario.suspendida:
                raise ValidationError("La cuenta ya no está habilitada.")
            bloquear_publicacion()
            terminos = obtener_terminos_vigentes()
            aceptado = aceptacion_temporal(request, terminos)
            if aceptado is None:
                raise ValidationError("Acepta primero las condiciones vigentes; la aceptación vence a los 30 minutos.")
            existente = AceptacionTerminos.objects.filter(usuario=usuario, terminos=terminos).first()
            if existente:
                request.session.pop(CLAVE_ACEPTACION, None)
                return existente
            comprobante = AceptacionTerminos(usuario=usuario, terminos=terminos,
                aceptado_en=aceptado, firmado_en=timezone.now())
            comprobante.firma.save(f"{uuid4().hex}.png", archivo, save=False)
            comprobante.full_clean()
            comprobante.save()
    except Exception:
        # Los archivos no se revierten con SQL: se elimina solo el nuevo PNG.
        if comprobante is not None and comprobante.firma.name:
            comprobante.firma.delete(save=False)
        raise
    request.session.pop(CLAVE_ACEPTACION, None)
    return comprobante
