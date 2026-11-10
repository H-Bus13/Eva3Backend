"""Reservas consultadas bajo el bloqueo de la máquina que se va a operar."""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from .models import SolicitudArriendo, HistorialSolicitudArriendo


def registrar_cambio(solicitud, anterior, responsable, motivo):
    HistorialSolicitudArriendo.objects.create(solicitud=solicitud, estado_anterior=anterior,
        estado_nuevo=solicitud.estado, responsable=responsable, motivo=motivo)


def exigir_sin_reserva(maquina, excluir=None):
    consulta = SolicitudArriendo.objects.filter(maquinaria=maquina, estado="APROBADA", reserva_hasta__gt=timezone.now())
    if excluir is not None:
        consulta = consulta.exclude(pk=excluir)
    if consulta.exists():
        raise ValidationError("La máquina está reservada para una solicitud aprobada.")


def vencer_reservas(maquinaria_id=None):
    from .servicios_arriendos import bloquear_contexto
    consulta = SolicitudArriendo.objects.filter(estado="APROBADA", reserva_hasta__lte=timezone.now())
    if maquinaria_id is not None:
        consulta = consulta.filter(maquinaria_id=maquinaria_id)
    cantidad = 0
    for pk, maquina_id, obra_id in consulta.order_by("pk").values_list("pk", "maquinaria_id", "obra_destino_id"):
        with transaction.atomic():
            # Mismo orden de bloqueo que aprobaciones y entregas. Un fallo
            # posterior del solicitante no revierte este vencimiento.
            bloquear_contexto(maquina_id, obra_id)
            solicitud = SolicitudArriendo.objects.select_for_update().get(pk=pk)
            if solicitud.estado == "APROBADA" and solicitud.reserva_hasta <= timezone.now():
                solicitud.estado = "VENCIDA"
                solicitud.save(update_fields=["estado"])
                registrar_cambio(solicitud, "APROBADA", None, "Venció la reserva sin entrega.")
                cantidad += 1
    return cantidad
