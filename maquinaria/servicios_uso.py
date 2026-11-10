from datetime import timedelta

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Arriendo, SesionUso
from .revision_por_uso import asegurar_revision_por_uso
from .servicios_arriendos import bloquear_contexto
from .servicios_ubicaciones import exigir_bodega_habilitada


def bloquear_arriendo_para_uso(arriendo_id, usuario, solo_responsable=False):
    previa = Arriendo.objects.get(pk=arriendo_id)
    puede_gestionar = usuario.has_perm("maquinaria.gestionar_arriendos")
    if (not usuario.is_authenticated or not usuario.is_active
            or (previa.responsable_id != usuario.pk and (solo_responsable or not puede_gestionar))):
        raise PermissionDenied
    maquina, bodegas, obra = bloquear_contexto(previa.maquinaria_id, previa.obra_destino_id)
    arriendo = Arriendo.objects.select_for_update().get(pk=arriendo_id)
    return arriendo, maquina, bodegas[maquina.bodega_id], obra


def iniciar_trabajo(*, arriendo_id, usuario):
    impedimento = None
    with transaction.atomic():
        arriendo, maquina, bodega, obra = bloquear_arriendo_para_uso(arriendo_id, usuario, solo_responsable=True)
        if arriendo.devuelto_en is not None or arriendo.recibido_en is not None:
            raise ValidationError("La máquina ya fue recibida o el arriendo está cerrado.")
        if maquina.estado != "EN_USO":
            raise ValidationError("El estado del equipo no permite iniciar trabajo.")
        exigir_bodega_habilitada(bodega)
        if obra is not None and not obra.activa:
            raise ValidationError("La obra de destino está inactiva.")
        if SesionUso.objects.filter(arriendo=arriendo, fin__isnull=True).exists():
            raise ValidationError("Ya existe una sesión de trabajo en marcha.")
        asegurar_revision_por_uso(maquina=maquina, responsable=usuario)
        if maquina.bloqueada_por_mantencion:
            impedimento = "El equipo requiere una revisión antes de iniciar trabajo."
        else:
            sesion = SesionUso.objects.create(arriendo=arriendo, inicio=timezone.now(), iniciada_por=usuario)
    # La advertencia y la orden preventiva deben quedar guardadas aunque se
    # rechace el inicio: lanzar el error dentro de atomic las revertiría.
    if impedimento:
        raise ValidationError(impedimento)
    return sesion


@transaction.atomic
def pausar_trabajo(*, arriendo_id, usuario):
    arriendo, maquina, _, _ = bloquear_arriendo_para_uso(arriendo_id, usuario)
    sesion = SesionUso.objects.select_for_update().filter(arriendo=arriendo, fin__isnull=True).first()
    if sesion is None:
        raise ValidationError("No hay una sesión en marcha.")
    ahora = timezone.now()
    fin = min(ahora, arriendo.recibido_en) if arriendo.recibido_en else ahora
    if fin < sesion.inicio:
        raise ValidationError("La fecha de inicio de la sesión no es válida.")
    sesion.fin = fin
    sesion.cerrada_por = usuario
    sesion.motivo_cierre = "Pausa del responsable" if arriendo.responsable_id == usuario.pk else "Detención por personal autorizado"
    sesion.save(update_fields=["fin", "cerrada_por", "motivo_cierre"])
    maquina.tiempo_uso_acumulado += fin - sesion.inicio
    maquina.save(update_fields=["tiempo_uso_acumulado"])
    asegurar_revision_por_uso(maquina=maquina, responsable=usuario)
    return sesion


@transaction.atomic
def estado_uso(*, arriendo_id, usuario, sincronizar=False):
    arriendo, maquina, bodega, obra = bloquear_arriendo_para_uso(arriendo_id, usuario)
    ahora = timezone.now()
    if sincronizar and arriendo.recibido_en is None and arriendo.devuelto_en is None:
        asegurar_revision_por_uso(maquina=maquina, responsable=usuario)
    sesiones = list(SesionUso.objects.filter(arriendo=arriendo).order_by("inicio", "pk"))
    activa = next((s for s in sesiones if s.fin is None), None)
    limite = min(ahora, arriendo.recibido_en) if arriendo.recibido_en else ahora
    duracion = limite - activa.inicio if activa else timedelta()
    if duracion < timedelta():
        raise ValidationError("La fecha de inicio de la sesión no es válida.")
    total_arriendo = sum((s.fin - s.inicio for s in sesiones if s.fin is not None), timedelta()) + duracion
    operativo = arriendo.devuelto_en is None and arriendo.recibido_en is None and maquina.estado == "EN_USO"
    bloqueada = maquina.bloqueada_por_mantencion
    ubicacion_activa = bodega.activa and (not bodega.obra_id or bodega.obra.activa) and (obra is None or obra.activa)
    return {
        "sesion_activa": bool(activa and operativo),
        "segundos_sesion": duracion.total_seconds(),
        "segundos_totales": maquina.tiempo_uso_total.total_seconds(),
        "segundos_arriendo": total_arriendo.total_seconds(),
        "revision_pendiente": bloqueada,
        "recibido": arriendo.recibido_en is not None,
        "cerrado": arriendo.devuelto_en is not None,
        "puede_iniciar": usuario.pk == arriendo.responsable_id and operativo and not activa and not bloqueada and bool(ubicacion_activa),
        "puede_pausar": bool(activa) and (usuario.pk == arriendo.responsable_id or usuario.has_perm("maquinaria.gestionar_arriendos")),
    }
