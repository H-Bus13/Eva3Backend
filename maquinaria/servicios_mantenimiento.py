from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Arriendo, Maquinaria, Mantenimiento, MovimientoMaquinaria, SesionUso
from .permisos import exigir_permiso
from .servicios_maquinaria import registrar_evento
from .servicios_ubicaciones import bloquear_bodegas, exigir_bodega_habilitada


def bloquear_equipo(maquinaria_id):
    # Mismo orden de bloqueo que traslados y cierres: ubicación, máquina
    # y después la orden. No se bloquean joins sobre relaciones opcionales.
    bodega_id = Maquinaria.objects.values_list("bodega_id", flat=True).get(pk=maquinaria_id)
    bodegas = bloquear_bodegas([bodega_id])
    maquina = Maquinaria.objects.select_for_update().get(pk=maquinaria_id)
    if maquina.bodega_id != bodega_id:
        raise ValidationError("El equipo cambió de ubicación. Revisa su detalle.")
    return maquina, bodegas[bodega_id]


def comprobar_sin_uso(maquina):
    if (Arriendo.objects.filter(maquinaria=maquina, devuelto_en__isnull=True).exists()
            or SesionUso.objects.filter(arriendo__maquinaria=maquina, fin__isnull=True).exists()):
        raise ValidationError("No se puede intervenir una máquina con arriendo o sesión de uso abierta.")
    if maquina.estado in (Maquinaria.Estado.BAJA, Maquinaria.Estado.EN_USO):
        raise ValidationError("El estado actual de la máquina no permite intervenirla.")


@transaction.atomic
def programar_mantenimiento(*, datos, responsable):
    exigir_permiso(responsable, "add_mantenimiento")
    maquina, bodega = bloquear_equipo(datos["maquinaria"].pk)
    exigir_bodega_habilitada(bodega)
    if maquina.estado == Maquinaria.Estado.BAJA:
        raise ValidationError("Primero debes reactivar la máquina dada de baja.")
    descripcion = datos["descripcion"].strip()
    if not descripcion:
        raise ValidationError("Indica el trabajo que se debe realizar.")
    fecha = datos["fecha_programada"]
    # Una programación futura no implica intervenir ni detener el equipo.
    # Si es exigible hoy, no se crea mientras el equipo siga arrendado.
    if fecha <= timezone.localdate():
        from .reservas import exigir_sin_reserva
        exigir_sin_reserva(maquina)
        comprobar_sin_uso(maquina)
    if maquina.mantenimientos.filter(finalizado_en__isnull=True, fecha_programada=fecha, descripcion=descripcion).exists():
        raise ValidationError("Ya hay una mantención pendiente con esos datos.")
    orden = Mantenimiento.objects.create(maquinaria=maquina, fecha_programada=fecha,
                                         descripcion=descripcion, programado_por=responsable)
    anterior = maquina.estado
    if fecha <= timezone.localdate():
        maquina.estado = Maquinaria.Estado.MANTENIMIENTO
        maquina.revision_pendiente = True
        maquina.save(update_fields=["estado", "revision_pendiente"])
    registrar_evento(maquina, responsable, MovimientoMaquinaria.Tipo.PROGRAMACION_MANTENCION,
                    f"Mantención #{orden.pk} programada para {fecha}: {descripcion}", anterior, maquina.bodega)
    return orden


@transaction.atomic
def iniciar_mantenimiento(*, mantenimiento_id, responsable):
    exigir_permiso(responsable, "iniciar_mantenimiento")
    maquinaria_id = Mantenimiento.objects.values_list("maquinaria_id", flat=True).get(pk=mantenimiento_id)
    maquina, bodega = bloquear_equipo(maquinaria_id)
    orden = Mantenimiento.objects.select_for_update().get(pk=mantenimiento_id)
    exigir_bodega_habilitada(bodega)
    if orden.finalizado_en is not None or orden.iniciado_en is not None:
        raise ValidationError("Esta mantención ya fue iniciada o finalizada.")
    from .reservas import exigir_sin_reserva
    exigir_sin_reserva(maquina)
    comprobar_sin_uso(maquina)
    if maquina.mantenimientos.filter(iniciado_en__isnull=False, finalizado_en__isnull=True).exclude(pk=orden.pk).exists():
        raise ValidationError("La máquina ya tiene una mantención en curso.")
    anterior = maquina.estado
    orden.iniciado_en = timezone.now()
    orden.responsable = responsable
    orden.save(update_fields=["iniciado_en", "responsable"])
    maquina.estado = Maquinaria.Estado.MANTENIMIENTO
    maquina.revision_pendiente = True
    maquina.save(update_fields=["estado", "revision_pendiente"])
    registrar_evento(maquina, responsable, MovimientoMaquinaria.Tipo.INICIO_MANTENCION,
                    f"Inicio de mantención #{orden.pk}: {orden.descripcion}", anterior, maquina.bodega)
    return orden


@transaction.atomic
def finalizar_mantenimiento(*, mantenimiento_id, resultado, apta, responsable):
    exigir_permiso(responsable, "finalizar_mantenimiento")
    resultado = resultado.strip()
    if not resultado or type(apta) is not bool:
        raise ValidationError("Indica el resultado y si el equipo quedó apto.")
    maquinaria_id = Mantenimiento.objects.values_list("maquinaria_id", flat=True).get(pk=mantenimiento_id)
    maquina, bodega = bloquear_equipo(maquinaria_id)
    orden = Mantenimiento.objects.select_for_update().get(pk=mantenimiento_id)
    if orden.iniciado_en is None or orden.finalizado_en is not None:
        raise ValidationError("Solo se puede finalizar una mantención en curso, una única vez.")
    comprobar_sin_uso(maquina)
    if maquina.estado != Maquinaria.Estado.MANTENIMIENTO:
        raise ValidationError("La máquina no está en mantenimiento. Revisa su estado.")
    otras = maquina.mantenimientos.exclude(pk=orden.pk).filter(finalizado_en__isnull=True)
    if otras.filter(iniciado_en__isnull=False).exists():
        raise ValidationError("Hay otra intervención en curso que debe revisarse primero.")
    if apta:
        exigir_bodega_habilitada(bodega)
    anterior = maquina.estado
    orden.finalizado_en = timezone.now()
    orden.lectura_uso = maquina.tiempo_uso_acumulado
    orden.resultado = resultado
    orden.apta_para_servicio = apta
    orden.finalizado_por = responsable
    orden.save(update_fields=["finalizado_en", "lectura_uso", "resultado", "apta_para_servicio", "finalizado_por"])
    otras_exigibles = otras.filter(fecha_programada__lte=timezone.localdate()).exists()
    if apta:
        # Se actualiza la referencia, nunca se reinician las horas totales.
        maquina.tiempo_uso_ultima_mantencion = maquina.tiempo_uso_acumulado
        maquina.ultima_mantencion_conocida = True
        maquina.revision_pendiente = otras_exigibles
        maquina.estado = Maquinaria.Estado.MANTENIMIENTO if otras_exigibles else Maquinaria.Estado.DISPONIBLE
    else:
        maquina.revision_pendiente = True
        maquina.estado = Maquinaria.Estado.MANTENIMIENTO
        # Una reparación fallida conserva una tarea pendiente para que se
        # pueda continuar el trabajo sin reabrir ni sobrescribir su resultado.
        if not otras_exigibles:
            Mantenimiento.objects.create(maquinaria=maquina, fecha_programada=timezone.localdate(),
                descripcion=f"Seguimiento de mantención #{orden.pk}: {resultado}", programado_por=responsable)
    maquina.save(update_fields=["tiempo_uso_ultima_mantencion", "ultima_mantencion_conocida", "revision_pendiente", "estado"])
    registrar_evento(maquina, responsable, MovimientoMaquinaria.Tipo.FIN_MANTENCION,
                    f"Mantención #{orden.pk}. {'Apta' if apta else 'No apta'}: {resultado}", anterior, maquina.bodega)
    return orden
