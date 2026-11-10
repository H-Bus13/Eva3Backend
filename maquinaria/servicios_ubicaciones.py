from django.utils import timezone
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from .models import Arriendo, Bodega, HistorialUbicacion, Maquinaria, Obra, Usuario
from .permisos import exigir_permiso


def bodegas_habilitadas():
    return (Bodega.objects.filter(activa=True)
            .filter(Q(obra__isnull=True) | Q(obra__activa=True))
            .select_related("obra").order_by("nombre"))


def bloquear_bodegas(identificadores):
    ids = set(identificadores)
    relaciones = dict(Bodega.objects.filter(pk__in=ids).values_list("pk", "obra_id"))
    if set(relaciones) != ids:
        raise ValidationError("Alguna bodega ya no existe. Revisa las ubicaciones.")
    # Orden común para todos los servicios: primero obras, luego bodegas y
    # finalmente máquinas. Evita que un traslado y un cierre se crucen, y
    # evita bloqueos mutuos entre traslados a bodegas en sentido contrario.
    obras = {pk for pk in relaciones.values() if pk is not None}
    list(Obra.objects.select_for_update().filter(pk__in=obras).order_by("pk"))
    bodegas = {b.pk: b for b in Bodega.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    if any(b.obra_id != relaciones[b.pk] for b in bodegas.values()):
        raise ValidationError("Cambió la asociación de una bodega. Vuelve a intentarlo.")
    return bodegas


def exigir_bodega_habilitada(bodega):
    if not bodega.activa:
        raise ValidationError("La bodega está desactivada. Primero debes reactivarla.")
    if bodega.obra_id and not Obra.objects.filter(pk=bodega.obra_id, activa=True).exists():
        raise ValidationError("La obra asociada está desactivada. Primero debes reactivarla.")


@transaction.atomic
def guardar_ubicacion(*, tipo, datos, responsable, pk=None):
    if tipo not in ("obra", "bodega"):
        raise ValidationError("Tipo de ubicación desconocido.")
    exigir_permiso(responsable, f"{'change' if pk is not None else 'add'}_{tipo}")
    if tipo == "obra":
        ubicacion = Obra.objects.select_for_update().get(pk=pk) if pk is not None else Obra()
    elif pk is not None:
        ubicacion = bloquear_bodegas([pk])[pk]
    else:
        obra = datos.get("obra")
        if obra is not None:
            obra = Obra.objects.select_for_update().get(pk=obra.pk)
            if not obra.activa:
                raise ValidationError("No puedes crear una bodega en una obra desactivada.")
        ubicacion = Bodega(obra=obra)
    # El formulario no decide activa ni cambia la obra de una bodega existente.
    # PATCH combina con el registro ya bloqueado, para no sobrescribir otro
    # campo que se haya corregido mientras se abría la petición.
    for campo in ("nombre", "direccion"):
        if pk is None or campo in datos:
            setattr(ubicacion, campo, datos[campo])
    ubicacion.full_clean()
    if pk is None:
        ubicacion.save()
    else:
        ubicacion.save(update_fields=["nombre", "direccion"])
    return ubicacion


@transaction.atomic
def cambiar_actividad_ubicacion(*, tipo, pk, activar, motivo, responsable):
    if tipo not in ("obra", "bodega"):
        raise ValidationError("Tipo de ubicación desconocido.")
    exigir_permiso(responsable, f"{'reactivar' if activar else 'desactivar'}_{tipo}")
    if activar and not (responsable.is_superuser or responsable.rol == Usuario.Rol.ADMINISTRADOR):
        raise PermissionDenied
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Debes indicar el motivo de la operación.")
    ubicacion = (Obra.objects.select_for_update().get(pk=pk) if tipo == "obra"
                 else bloquear_bodegas([pk])[pk])
    if ubicacion.activa == activar:
        raise ValidationError("La ubicación ya tiene ese estado. Revisa su historial.")
    if activar:
        if tipo == "bodega" and ubicacion.obra_id and not Obra.objects.filter(pk=ubicacion.obra_id, activa=True).exists():
            raise ValidationError("Primero debes reactivar la obra asociada a esta bodega.")
    elif tipo == "obra":
        if ubicacion.bodegas.filter(activa=True).exists():
            raise ValidationError("La obra todavía tiene bodegas activas. Desactívalas primero.")
        from .models import SolicitudArriendo
        if SolicitudArriendo.objects.filter(obra_destino=ubicacion, estado="APROBADA", reserva_hasta__gt=timezone.now()).exists():
            raise ValidationError("La obra tiene una solicitud de arriendo reservada.")
        if Arriendo.objects.filter(obra_destino=ubicacion, devuelto_en__isnull=True).exists():
            raise ValidationError("La obra tiene arriendos pendientes de devolución.")
    else:
        if ubicacion.maquinarias.exclude(estado=Maquinaria.Estado.BAJA).exists():
            raise ValidationError("Primero debes trasladar la maquinaria de esta bodega. Solo pueden permanecer equipos dados de baja.")
        if Arriendo.objects.filter(maquinaria__bodega=ubicacion, devuelto_en__isnull=True).exists():
            raise ValidationError("La bodega está asociada a un arriendo pendiente de devolución.")
    ubicacion.activa = activar
    ubicacion.save(update_fields=["activa"])
    # Si falla registrar el evento, se revierte también el cambio de actividad.
    HistorialUbicacion.objects.create(
        **{tipo: ubicacion}, responsable=responsable, motivo=motivo,
        accion=HistorialUbicacion.Accion.REACTIVACION if activar else HistorialUbicacion.Accion.DESACTIVACION,
    )
    return ubicacion

