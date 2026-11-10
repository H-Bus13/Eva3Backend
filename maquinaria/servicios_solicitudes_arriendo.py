from datetime import timedelta
from uuid import uuid4
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import SolicitudArriendo, SolicitudEntrega, Usuario
from .permisos import exigir_permiso
from .condiciones import obtener_terminos_vigentes
from .destinos import validar_destino, copiar_destino
from .reservas import exigir_sin_reserva, registrar_cambio, vencer_reservas
from .servicios_arriendos import (bloquear_contexto, bloquear_contratista, aceptacion_vigente,
                                 validar_equipo_entrega)


def exigir_cuenta(usuario):
    if not usuario.is_authenticated or not usuario.is_active or usuario.suspendida:
        raise PermissionDenied


def consultar(usuario):
    exigir_cuenta(usuario)
    consulta = SolicitudArriendo.objects.select_related("maquinaria", "empresa", "solicitante", "obra_destino", "terminos", "arriendo")
    return consulta if usuario.has_perm("maquinaria.gestionar_arriendos") else consulta.filter(solicitante=usuario)


def bloquear_solicitud(pk):
    previa = SolicitudArriendo.objects.get(pk=pk)
    maquina, bodegas, obra = bloquear_contexto(previa.maquinaria_id, previa.obra_destino_id)
    return SolicitudArriendo.objects.select_for_update().get(pk=pk), maquina, bodegas, obra


def validar_reserva(solicitud):
    if solicitud.estado != "APROBADA" or solicitud.reserva_hasta is None or solicitud.reserva_hasta <= timezone.now():
        raise ValidationError("La solicitud no está aprobada o su reserva venció.")
    if solicitud.devolucion_prevista <= timezone.now():
        raise ValidationError("La fecha de devolución ya pasó.")


def solicitar(*, datos, firma, usuario):
    exigir_cuenta(usuario)
    if usuario.empresa_id is None:
        raise ValidationError("La cuenta debe pertenecer a una empresa contratista.")
    vencer_reservas(datos["maquinaria"].pk)
    archivo = None
    try:
        with transaction.atomic():
            contratista, empresa = bloquear_contratista(usuario.pk, usuario.empresa_id)
            aceptacion = aceptacion_vigente(contratista)
            destino = validar_destino(datos)
            maquina, bodegas, obra = bloquear_contexto(datos["maquinaria"].pk)
            validar_equipo_entrega(maquina, bodegas[maquina.bodega_id], obra, datos["devolucion_prevista"])
            exigir_sin_reserva(maquina)
            if maquina.precio_diario is None or maquina.precio_diario <= 0:
                raise ValidationError("La máquina no tiene una tarifa válida.")
            if not datos["acepto"] or datos["version_id"] != aceptacion.terminos_id:
                raise ValidationError("Revisa y acepta las condiciones vigentes.")
            # Se rechaza un cambio de tarifa desde que se abrió el formulario.
            # El precio acordado se copia del servidor, nunca del navegador.
            if datos["precio_visto"] != maquina.precio_diario:
                raise ValidationError("El precio cambió. Revisa la tarifa actual antes de firmar.")
            ahora = timezone.now()
            solicitud = SolicitudArriendo(maquinaria=maquina, empresa=empresa, solicitante=contratista,
                obra_destino=None, **destino, devolucion_prevista=datos["devolucion_prevista"],
                observaciones=datos.get("observaciones", ""), precio_diario_acordado=maquina.precio_diario,
                moneda=maquina.moneda, terminos=aceptacion.terminos, aceptado_en=ahora, firmado_en=ahora)
            archivo = solicitud.firma_solicitud
            archivo.save(f"{uuid4().hex}.png", firma, save=False)
            solicitud.full_clean()
            solicitud.save()
            registrar_cambio(solicitud, "", contratista, "Solicitud firmada y enviada.")
            return solicitud
    except Exception:
        if archivo and archivo.name:
            archivo.delete(save=False)
        raise


def revisar(*, solicitud_id, aprobar, motivo, actor):
    exigir_cuenta(actor)
    exigir_permiso(actor, "gestionar_arriendos")
    previa = SolicitudArriendo.objects.get(pk=solicitud_id)
    vencer_reservas(previa.maquinaria_id)
    with transaction.atomic():
        if type(aprobar) is not bool or not motivo.strip():
            raise ValidationError("Indica el motivo de la revisión.")
        # Usuario y empresa antes de ubicaciones/máquina, como en entrega.
        if aprobar:
            contratista, empresa = bloquear_contratista(previa.solicitante_id, previa.empresa_id)
            aceptacion = aceptacion_vigente(contratista)
        solicitud, maquina, bodegas, obra = bloquear_solicitud(solicitud_id)
        if solicitud.estado != "PENDIENTE":
            raise ValidationError("La solicitud ya fue revisada.")
        ahora = timezone.now()
        if aprobar:
            if solicitud.terminos_id != aceptacion.terminos_id:
                raise ValidationError("Las condiciones cambiaron. Rechaza y solicita una nueva petición firmada.")
            validar_equipo_entrega(maquina, bodegas[maquina.bodega_id], obra, solicitud.devolucion_prevista)
            exigir_sin_reserva(maquina)
            solicitud.estado = "APROBADA"
            solicitud.reserva_hasta = min(ahora + timedelta(hours=1), solicitud.devolucion_prevista)
        else:
            solicitud.estado = "RECHAZADA"
        solicitud.revisada_por = actor
        solicitud.revisada_en = ahora
        solicitud.motivo_revision = motivo.strip()
        solicitud.full_clean()
        solicitud.save()
        registrar_cambio(solicitud, "PENDIENTE", actor, motivo.strip())
        return solicitud


def cancelar(*, solicitud_id, motivo, usuario):
    exigir_cuenta(usuario)
    previa = consultar(usuario).get(pk=solicitud_id)
    vencer_reservas(previa.maquinaria_id)
    with transaction.atomic():
        solicitud, maquina, bodegas, obra = bloquear_solicitud(solicitud_id)
        if solicitud.estado not in ("PENDIENTE", "APROBADA") or not motivo.strip():
            raise ValidationError("La solicitud no puede cancelarse o falta el motivo.")
        if solicitud.estado == "PENDIENTE" and solicitud.solicitante_id != usuario.pk:
            raise ValidationError("Para una solicitud pendiente utiliza rechazar e indica el motivo.")
        anterior = solicitud.estado
        solicitud.estado = "CANCELADA"
        solicitud.cancelada_por = usuario
        solicitud.cancelada_en = timezone.now()
        solicitud.motivo_cancelacion = motivo.strip()
        solicitud.full_clean()
        solicitud.save()
        registrar_cambio(solicitud, anterior, usuario, motivo.strip())
        return solicitud


def preparar_desde_solicitud(*, solicitud_id, actor):
    exigir_cuenta(actor)
    exigir_permiso(actor, "gestionar_arriendos")
    previa = SolicitudArriendo.objects.get(pk=solicitud_id)
    vencer_reservas(previa.maquinaria_id)
    with transaction.atomic():
        contratista, empresa = bloquear_contratista(previa.solicitante_id, previa.empresa_id)
        aceptacion = aceptacion_vigente(contratista)
        solicitud, maquina, bodegas, obra = bloquear_solicitud(solicitud_id)
        validar_reserva(solicitud)
        if solicitud.terminos_id != aceptacion.terminos_id:
            raise ValidationError("Las condiciones cambiaron. Cancela y solicita una nueva petición firmada.")
        validar_equipo_entrega(maquina, bodegas[maquina.bodega_id], obra, solicitud.devolucion_prevista)
        exigir_sin_reserva(maquina, excluir=solicitud.pk)
        # Una relación única impide dos comprobantes para la misma solicitud.
        entrega = SolicitudEntrega.objects.filter(solicitud_arriendo=solicitud).first()
        if entrega and entrega.arriendo_id:
            raise ValidationError("La entrega ya fue confirmada.")
        if entrega and not entrega.cancelada_en and entrega.vence_en > timezone.now():
            return entrega
        datos = dict(maquinaria=maquina, empresa=empresa, responsable=contratista, obra_destino=obra, **copiar_destino(solicitud),
            terminos=solicitud.terminos, devolucion_prevista=solicitud.devolucion_prevista,
            tarifa_diaria=solicitud.precio_diario_acordado, observaciones=solicitud.observaciones,
            preparada_por=actor, vence_en=min(timezone.now() + timedelta(hours=1), solicitud.reserva_hasta))
        if entrega:
            # No se reabre ni sobrescribe un comprobante cancelado: se debe
            # cancelar la solicitud completa y crear una nueva.
            raise ValidationError("El comprobante fue cancelado o venció. Cancela esta solicitud y crea otra.")
        return SolicitudEntrega.objects.create(solicitud_arriendo=solicitud, **datos)
