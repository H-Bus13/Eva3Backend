from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .forms_maquinaria import duracion_horas
from .permisos import exigir_permiso
from .servicios_ubicaciones import bloquear_bodegas, exigir_bodega_habilitada
from .models import Arriendo, Maquinaria, Mantenimiento, MovimientoMaquinaria, SesionUso, Usuario





def comprobar_sin_operaciones(maquina):
    # También verifica los registros: el campo estado por sí solo podría
    # haberse modificado fuera de los procesos de la aplicación.
    if (Arriendo.objects.filter(maquinaria=maquina, devuelto_en__isnull=True).exists()
            or SesionUso.objects.filter(arriendo__maquinaria=maquina, fin__isnull=True).exists()
            or Mantenimiento.objects.filter(maquinaria=maquina, finalizado_en__isnull=True).exists()):
        raise ValidationError("La máquina tiene un arriendo, sesión de uso o mantenimiento abierto.")


def registrar_evento(maquina, responsable, tipo, motivo, anterior, origen=None):
    MovimientoMaquinaria.objects.create(
        maquinaria=maquina, registrado_por=responsable, tipo=tipo, motivo=motivo,
        origen=origen, destino=maquina.bodega,
        estado_anterior=anterior, estado_nuevo=maquina.estado,
    )


@transaction.atomic
def crear_maquinaria(*, datos, responsable):
    exigir_permiso(responsable, "add_maquinaria")
    bodega = bloquear_bodegas([datos['bodega'].pk])[datos['bodega'].pk]
    exigir_bodega_habilitada(bodega)
    # Una tarifa pendiente solo se permite en registros antiguos. Las altas
    # nuevas requieren precio incluso si el servicio se llama sin formulario.
    if datos.get("precio_diario") is None:
        raise ValidationError({"precio_diario": "Debes indicar un precio diario mayor que cero."})
    total = duracion_horas(datos["horas_iniciales"])
    lectura = datos.get("horas_ultima_mantencion")
    ultima = duracion_horas(lectura) if lectura is not None else timedelta()
    if total < timedelta() or ultima < timedelta() or ultima > total:
        raise ValidationError("Las lecturas iniciales no son válidas.")
    requiere_revision = lectura is None or total - ultima >= timedelta(hours=250)
    maquina = Maquinaria(
        **{campo: datos[campo] for campo in ("codigo", "nombre", "marca", "modelo")}, bodega=bodega,
        precio_diario=datos["precio_diario"],
        tiempo_uso_inicial=total, tiempo_uso_acumulado=total,
        tiempo_uso_ultima_mantencion=ultima,
        registrado_por=responsable, registrado_en=timezone.now(),
        revision_pendiente=requiere_revision, ultima_mantencion_conocida=lectura is not None,
        estado=Maquinaria.Estado.MANTENIMIENTO if requiere_revision else Maquinaria.Estado.DISPONIBLE,
    )
    maquina.full_clean()
    maquina.save()
    registrar_evento(maquina, responsable, MovimientoMaquinaria.Tipo.ALTA,
                    f"Registro inicial. Precio diario: {maquina.precio_diario} CLP. Horas totales: {datos['horas_iniciales']}. Lectura de última mantención: {lectura if lectura is not None else 'desconocida'}.", maquina.estado)
    if requiere_revision:
        Mantenimiento.objects.create(
            maquinaria=maquina, fecha_programada=timezone.localdate(), programado_por=responsable,
            descripcion="Revisión inicial: historial de mantención desconocido o intervalo de 250 horas cumplido.",
        )
    return maquina


@transaction.atomic
def editar_maquinaria(*, maquinaria_id, datos, responsable):
    exigir_permiso(responsable, "change_maquinaria")
    # La edición también escribe un evento con la bodega como referencia.
    # Respeta el mismo orden de bloqueos que traslados y desactivaciones.
    bodega_id = Maquinaria.objects.values_list("bodega_id", flat=True).get(pk=maquinaria_id)
    bloquear_bodegas([bodega_id])
    maquina = Maquinaria.objects.select_for_update().get(pk=maquinaria_id)
    if maquina.bodega_id != bodega_id:
        raise ValidationError("La máquina fue trasladada mientras editabas. Revisa sus datos.")
    cambios = []
    # Lista explícita: nunca se toman estado, código, bodega ni horas del POST.
    if "precio_diario" in datos and datos["precio_diario"] is None:
        raise ValidationError({"precio_diario": "El precio no puede quedar vacío."})
    for campo in ("nombre", "marca", "modelo", "precio_diario"):
        if campo not in datos:
            continue
        nuevo = datos[campo]
        if getattr(maquina, campo) != nuevo:
            cambios.append(f"{campo}: {getattr(maquina, campo)} → {nuevo}")
            setattr(maquina, campo, nuevo)
    if cambios:
        maquina.full_clean()
        maquina.save(update_fields=["nombre", "marca", "modelo", "precio_diario"])
        registrar_evento(maquina, responsable, MovimientoMaquinaria.Tipo.EDICION,
                        "; ".join(cambios), maquina.estado, maquina.bodega)
    return maquina


@transaction.atomic
def operar_maquinaria(*, maquinaria_id, accion, motivo, responsable, destino=None):
    permisos = {"trasladar": "trasladar_maquinaria", "baja": "dar_baja_maquinaria", "reactivar": "reactivar_maquinaria"}
    if accion not in permisos:
        raise ValidationError("Operación desconocida.")
    exigir_permiso(responsable, permisos[accion])
    if accion == "reactivar" and not (responsable.is_superuser or responsable.rol == Usuario.Rol.ADMINISTRADOR):
        raise PermissionDenied
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Debes indicar el motivo de la operación.")
    origen_id = Maquinaria.objects.values_list("bodega_id", flat=True).get(pk=maquinaria_id)
    ids = [origen_id]
    if accion == "trasladar" and destino is not None:
        ids.append(destino.pk)
    bodegas = bloquear_bodegas(ids)
    maquina = Maquinaria.objects.select_for_update().get(pk=maquinaria_id)
    if maquina.bodega_id != origen_id:
        raise ValidationError("La máquina fue trasladada mientras confirmabas. Revisa su ubicación.")
    if accion == "trasladar" and destino is not None:
        destino = bodegas[destino.pk]
        exigir_bodega_habilitada(destino)
    if accion == "reactivar":
        exigir_bodega_habilitada(bodegas[origen_id])
    esperado = Maquinaria.Estado.BAJA if accion == "reactivar" else Maquinaria.Estado.DISPONIBLE
    if maquina.estado != esperado:
        raise ValidationError("El estado de la máquina cambió o no permite esta operación. Revisa su detalle.")
    from .reservas import exigir_sin_reserva
    exigir_sin_reserva(maquina)
    comprobar_sin_operaciones(maquina)
    origen, anterior = maquina.bodega, maquina.estado
    if accion == "trasladar":
        if destino is None or destino.pk == origen.pk:
            raise ValidationError("Selecciona una bodega diferente de la actual.")
        maquina.bodega = destino
        tipo = MovimientoMaquinaria.Tipo.TRASLADO
        maquina.save(update_fields=["bodega"])
    elif accion == "baja":
        maquina.estado = Maquinaria.Estado.BAJA
        tipo = MovimientoMaquinaria.Tipo.BAJA
        maquina.save(update_fields=["estado"])
    else:
        # Reactivar nunca pone la máquina directamente disponible. Conserva
        # las horas y exige una revisión antes de volver a arrendarla.
        maquina.estado = Maquinaria.Estado.MANTENIMIENTO
        maquina.revision_pendiente = True
        maquina.save(update_fields=["estado", "revision_pendiente"])
        tipo = MovimientoMaquinaria.Tipo.REACTIVACION
        Mantenimiento.objects.create(
            maquinaria=maquina, fecha_programada=timezone.localdate(), programado_por=responsable,
            descripcion=f"Revisión tras reactivación de baja: {motivo}",
        )
    registrar_evento(maquina, responsable, tipo, motivo, anterior, origen)
    return maquina





