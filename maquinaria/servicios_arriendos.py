from datetime import timedelta
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .destinos import validar_destino, copiar_destino, CAMPOS_DESTINO
from .condiciones import bloquear_publicacion, obtener_terminos_vigentes
from .servicios_bloqueos import actualizar_bloqueo_por_atraso, arriendos_atrasados
from .models import (AceptacionTerminos, Arriendo, Bodega, Empresa, Maquinaria, Mantenimiento,
                     MovimientoMaquinaria, Obra, SesionUso, SolicitudDevolucion, SolicitudEntrega, Usuario)
from .permisos import exigir_permiso
from .servicios_maquinaria import registrar_evento
from .servicios_ubicaciones import exigir_bodega_habilitada


def bloquear_contexto(maquinaria_id, obra_id=None, destino_id=None):
    origen_id = Maquinaria.objects.values_list("bodega_id", flat=True).get(pk=maquinaria_id)
    ids = {origen_id}
    if destino_id is not None:
        ids.add(destino_id)
    relaciones = dict(Bodega.objects.filter(pk__in=ids).values_list("pk", "obra_id"))
    if set(relaciones) != ids:
        raise ValidationError("La bodega seleccionada ya no existe.")
    # Incluye la obra de destino del arriendo en el orden global de bloqueo:
    # obras por ID, bodegas por ID, máquina, arriendo y solicitud.
    obras_ids = {pk for pk in relaciones.values() if pk is not None} | ({obra_id} if obra_id is not None else set())
    obras = {o.pk: o for o in Obra.objects.select_for_update().filter(pk__in=obras_ids).order_by("pk")}
    bodegas = {b.pk: b for b in Bodega.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    if any(b.obra_id != relaciones[b.pk] for b in bodegas.values()):
        raise ValidationError("Cambió una ubicación. Vuelve a revisar la operación.")
    maquina = Maquinaria.objects.select_for_update().get(pk=maquinaria_id)
    if maquina.bodega_id != origen_id:
        raise ValidationError("La máquina fue trasladada. Revisa su ubicación.")
    return maquina, bodegas, obras[obra_id] if obra_id is not None else None


def bloquear_contratista(usuario_id, empresa_id):
    # NO KEY UPDATE mantiene protegidos los cambios de estos registros sin
    # bloquear las referencias de historial que otras operaciones insertan.
    usuario = Usuario.objects.select_for_update(no_key=True).get(pk=usuario_id)
    empresa = Empresa.objects.select_for_update(no_key=True).get(pk=empresa_id)
    if (not usuario.is_active or usuario.suspendida or usuario.estado_aprobacion != "APROBADO" or usuario.rol != "CONTRATISTA"
            or usuario.is_staff or usuario.is_superuser or usuario.empresa_id != empresa.pk):
        raise ValidationError("El responsable debe ser un contratista aprobado de la empresa indicada.")
    if empresa.tiene_bloqueo or arriendos_atrasados(empresa.pk).exists():
        raise ValidationError("La empresa está bloqueada para nuevos arriendos.")
    return usuario, empresa


def aceptacion_vigente(usuario):
    bloquear_publicacion()
    terminos = obtener_terminos_vigentes()
    aceptacion = AceptacionTerminos.objects.filter(usuario=usuario, terminos=terminos).exclude(firma="").order_by("-firmado_en", "-pk").first() if terminos else None
    if aceptacion is None:
        raise ValidationError("El responsable debe aceptar y firmar las condiciones vigentes desde su perfil.")
    return aceptacion


def validar_equipo_entrega(maquina, bodega, obra, fecha):
    exigir_bodega_habilitada(bodega)
    if obra is not None and not obra.activa:
        raise ValidationError("La obra de destino está desactivada.")
    if (maquina.estado != "DISPONIBLE" or maquina.bloqueada_por_mantencion
            or Arriendo.objects.filter(maquinaria=maquina, devuelto_en__isnull=True).exists()
            or SesionUso.objects.filter(arriendo__maquinaria=maquina, fin__isnull=True).exists()):
        raise ValidationError("La máquina no está disponible o tiene revisiones, uso o arriendos pendientes.")
    if fecha <= timezone.now():
        raise ValidationError("La fecha prevista de devolución debe ser futura.")


@transaction.atomic
def _preparar_entrega(*, datos, responsable):
    exigir_permiso(responsable, "gestionar_arriendos")
    usuario, empresa = bloquear_contratista(datos["responsable"].pk, datos["empresa"].pk)
    aceptacion = aceptacion_vigente(usuario)
    destino = validar_destino(datos)
    maquina, bodegas, obra = bloquear_contexto(datos["maquinaria"].pk)
    validar_equipo_entrega(maquina, bodegas[maquina.bodega_id], obra, datos["devolucion_prevista"])
    from .reservas import exigir_sin_reserva
    exigir_sin_reserva(maquina)
    if datos["tarifa_diaria"] <= 0:
        raise ValidationError("La tarifa debe ser mayor que cero.")
    if SolicitudEntrega.objects.filter(maquinaria=maquina, responsable=usuario, empresa=empresa,
        arriendo__isnull=True, cancelada_en__isnull=True, vence_en__gt=timezone.now()).exists():
        raise ValidationError("Ya existe una entrega pendiente de firma para este responsable y equipo.")
    return SolicitudEntrega.objects.create(maquinaria=maquina, empresa=empresa, responsable=usuario,
        obra_destino=None, **destino, terminos=aceptacion.terminos, devolucion_prevista=datos["devolucion_prevista"],
        tarifa_diaria=datos["tarifa_diaria"], observaciones=datos.get("observaciones", ""), preparada_por=responsable)


def _confirmar_entrega(*, solicitud_id, usuario, firma):
    archivo = None
    try:
        with transaction.atomic():
            previa = SolicitudEntrega.objects.get(pk=solicitud_id)
            if previa.responsable_id != usuario.pk:
                raise PermissionDenied
            contratista, empresa = bloquear_contratista(usuario.pk, previa.empresa_id)
            aceptacion = aceptacion_vigente(contratista)
            maquina, bodegas, obra = bloquear_contexto(previa.maquinaria_id, previa.obra_destino_id)
            from .reservas import exigir_sin_reserva, registrar_cambio
            from .servicios_solicitudes_arriendo import validar_reserva
            from .models import SolicitudArriendo
            origen = None
            if previa.solicitud_arriendo_id:
                origen = SolicitudArriendo.objects.select_for_update().get(pk=previa.solicitud_arriendo_id)
                validar_reserva(origen)
            exigir_sin_reserva(maquina, excluir=origen.pk if origen else None)
            solicitud = SolicitudEntrega.objects.select_for_update().get(pk=solicitud_id)
            if solicitud.arriendo_id or solicitud.cancelada_en or solicitud.vence_en <= timezone.now():
                raise ValidationError("Esta entrega ya fue confirmada, cancelada o venció.")
            if solicitud.terminos_id != aceptacion.terminos_id:
                raise ValidationError("Las condiciones cambiaron. El personal debe cancelar y preparar una nueva entrega.")
            validar_equipo_entrega(maquina, bodegas[maquina.bodega_id], obra, solicitud.devolucion_prevista)
            if origen and (origen.solicitante_id != contratista.pk or origen.empresa_id != empresa.pk
                    or origen.maquinaria_id != maquina.pk or origen.obra_destino_id != solicitud.obra_destino_id
                    or origen.terminos_id != solicitud.terminos_id
                    or origen.precio_diario_acordado != solicitud.tarifa_diaria
                    or origen.devolucion_prevista != solicitud.devolucion_prevista):
                raise ValidationError("El comprobante no coincide con la solicitud aprobada.")
            destino = copiar_destino(solicitud)
            if origen and any(getattr(origen, campo) != getattr(solicitud, campo)
                    for campo in (*CAMPOS_DESTINO, "destino_legacy")):
                raise ValidationError("El destino difiere de la solicitud firmada.")
            arriendo = Arriendo(maquinaria=maquina, empresa=empresa, responsable=contratista, obra_destino=obra, **destino,
                aceptacion=aceptacion, bodega_origen=maquina.bodega, entregado_en=timezone.now(),
                devolucion_prevista=solicitud.devolucion_prevista, tarifa_diaria=solicitud.tarifa_diaria,
                observaciones=solicitud.observaciones)
            archivo = arriendo.firma_entrega
            archivo.save(f"{uuid4().hex}.png", firma, save=False)
            arriendo.full_clean()
            arriendo.save()
            anterior = maquina.estado
            maquina.estado = "EN_USO"
            maquina.save(update_fields=["estado"])
            solicitud.arriendo = arriendo
            solicitud.save(update_fields=["arriendo"])
            if origen:
                origen.estado = "ENTREGADA"
                origen.arriendo = arriendo
                origen.save(update_fields=["estado", "arriendo"])
                registrar_cambio(origen, "APROBADA", usuario, "Entrega física confirmada con firma.")
            registrar_evento(maquina, usuario, MovimientoMaquinaria.Tipo.ENTREGA,
                f"Arriendo #{arriendo.pk}. Entrega firmada para {arriendo.direccion_uso or 'destino histórico'} · {arriendo.comuna_uso}.", anterior, maquina.bodega)
            return arriendo
    except Exception:
        # El archivo no participa en la transacción SQL: si falla incluso
        # el commit, se elimina solo el PNG nuevo de esta operación.
        if archivo and archivo.name:
            archivo.delete(save=False)
        raise


def cerrar_sesiones_recepcion(arriendo, maquina, instante, responsable=None):
    incremento = timedelta()
    for sesion in SesionUso.objects.select_for_update().filter(arriendo=arriendo, fin__isnull=True).order_by("pk"):
        if sesion.inicio > instante:
            raise ValidationError("Hay una sesión con inicio posterior a la recepción. Revisa sus fechas.")
        incremento += instante - sesion.inicio
        sesion.fin = instante
        sesion.cerrada_por = responsable
        sesion.motivo_cierre = "Recepción física del equipo"
        sesion.save(update_fields=["fin", "cerrada_por", "motivo_cierre"])
    # El bloqueo de la máquina y el filtro de sesiones abiertas hacen que
    # repetir una recepción nunca vuelva a sumar la misma duración.
    maquina.tiempo_uso_acumulado += incremento


@transaction.atomic
def preparar_devolucion(*, arriendo_id, datos, responsable):
    exigir_permiso(responsable, "gestionar_arriendos")
    previa = Arriendo.objects.get(pk=arriendo_id)
    Empresa.objects.select_for_update(no_key=True).get(pk=previa.empresa_id)
    maquina, bodegas, _ = bloquear_contexto(previa.maquinaria_id, previa.obra_destino_id, datos["bodega"].pk)
    arriendo = Arriendo.objects.select_for_update().get(pk=arriendo_id)
    if arriendo.devuelto_en is not None or maquina.estado != "EN_USO":
        raise ValidationError("Este arriendo ya fue devuelto o el equipo tiene un estado incompatible.")
    destino = bodegas[datos["bodega"].pk]
    exigir_bodega_habilitada(destino)
    ahora = timezone.now()
    # Una recepción vencida puede reemplazarse, conservando su comprobante
    # pendiente como antecedente. La recepción física nunca se deshace.
    arriendo.recepciones.filter(cancelada_en__isnull=True, confirmada_en__isnull=True, vence_en__lte=ahora).update(
        cancelada_en=ahora, motivo_cancelacion="Venció sin firma; reemplazada al preparar otra recepción.")
    if arriendo.recepciones.filter(cancelada_en__isnull=True, confirmada_en__isnull=True).exists():
        raise ValidationError("Ya hay una recepción pendiente. Debe confirmarse o cancelarse antes de preparar otra.")
    observaciones = datos["observaciones"].strip()
    if not observaciones:
        raise ValidationError("Describe el estado de recepción del equipo.")
    instante = arriendo.recibido_en or ahora
    cerrar_sesiones_recepcion(arriendo, maquina, instante, responsable=responsable)
    origen = maquina.bodega
    maquina.bodega = destino
    maquina.save(update_fields=["bodega", "tiempo_uso_acumulado"])
    # Importación local para compartir la revisión preventiva sin crear un
    # ciclo entre los servicios de recepción y los del contador.
    from .revision_por_uso import asegurar_revision_por_uso
    asegurar_revision_por_uso(maquina=maquina, responsable=responsable)
    arriendo.recibido_en = instante
    arriendo.bodega_recepcion = destino
    arriendo.save(update_fields=["recibido_en", "bodega_recepcion"])
    actualizar_bloqueo_por_atraso(arriendo.empresa_id)
    solicitud = SolicitudDevolucion.objects.create(arriendo=arriendo, bodega=destino,
        observaciones=observaciones, requiere_revision=datos["requiere_revision"], preparada_por=responsable)
    registrar_evento(maquina, responsable, MovimientoMaquinaria.Tipo.RECEPCION,
        f"Recepción #{solicitud.pk}, arriendo #{arriendo.pk}, pendiente de firma. {observaciones}", maquina.estado, origen)
    return solicitud


def confirmar_devolucion(*, solicitud_id, usuario, firma):
    archivo = None
    try:
        with transaction.atomic():
            previa = SolicitudDevolucion.objects.select_related("arriendo").get(pk=solicitud_id)
            if previa.arriendo.responsable_id != usuario.pk:
                raise PermissionDenied
            maquina, bodegas, _ = bloquear_contexto(previa.arriendo.maquinaria_id, previa.arriendo.obra_destino_id, previa.bodega_id)
            arriendo = Arriendo.objects.select_for_update().get(pk=previa.arriendo_id)
            solicitud = SolicitudDevolucion.objects.select_for_update().get(pk=solicitud_id)
            if arriendo.devuelto_en or solicitud.confirmada_en or solicitud.cancelada_en or solicitud.vence_en <= timezone.now():
                raise ValidationError("La recepción fue confirmada, cancelada o venció.")
            if maquina.estado != "EN_USO" or arriendo.recibido_en is None or maquina.bodega_id != solicitud.bodega_id:
                raise ValidationError("La recepción física o el estado del equipo cambió. Revisa la operación.")
            exigir_bodega_habilitada(bodegas[solicitud.bodega_id])
            if SesionUso.objects.filter(arriendo=arriendo, fin__isnull=True).exists():
                raise ValidationError("El equipo tiene una sesión abierta después de su recepción. Debe revisarse.")
            arriendo.devuelto_en = timezone.now()
            archivo = arriendo.firma_devolucion
            archivo.save(f"{uuid4().hex}.png", firma, save=False)
            arriendo.full_clean()
            arriendo.save(update_fields=["devuelto_en", "firma_devolucion"])
            anterior = maquina.estado
            revision = solicitud.requiere_revision or maquina.bloqueada_por_mantencion
            maquina.estado = "MANTENIMIENTO" if revision else "DISPONIBLE"
            maquina.revision_pendiente = bool(revision)
            maquina.save(update_fields=["estado", "revision_pendiente"])
            if revision and not maquina.mantenimientos.filter(finalizado_en__isnull=True, fecha_programada__lte=timezone.localdate()).exists():
                Mantenimiento.objects.create(maquinaria=maquina, fecha_programada=timezone.localdate(),
                    descripcion=f"Revisión tras devolución #{arriendo.pk}: {solicitud.observaciones}", programado_por=solicitud.preparada_por)
            solicitud.confirmada_en = arriendo.devuelto_en
            solicitud.save(update_fields=["confirmada_en"])
            registrar_evento(maquina, usuario, MovimientoMaquinaria.Tipo.DEVOLUCION,
                f"Devolución firmada de arriendo #{arriendo.pk}. {solicitud.observaciones}", anterior, maquina.bodega)
            return arriendo
    except Exception:
        if archivo and archivo.name:
            archivo.delete(save=False)
        raise


@transaction.atomic
def cancelar_solicitud(*, tipo, pk, motivo, responsable):
    exigir_permiso(responsable, "gestionar_arriendos")
    if tipo not in ("entrega", "devolucion"):
        raise ValidationError("Tipo de solicitud desconocido.")
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Indica el motivo de cancelación.")
    modelo = SolicitudEntrega if tipo == "entrega" else SolicitudDevolucion
    solicitud = modelo.objects.select_for_update().get(pk=pk)
    confirmada = solicitud.arriendo_id if tipo == "entrega" else solicitud.confirmada_en
    if confirmada or solicitud.cancelada_en:
        raise ValidationError("No se puede cancelar una solicitud confirmada o ya cancelada.")
    solicitud.cancelada_en = timezone.now()
    solicitud.cancelada_por = responsable
    solicitud.motivo_cancelacion = motivo
    solicitud.save(update_fields=["cancelada_en", "cancelada_por", "motivo_cancelacion"])
    return solicitud



def preparar_entrega(*, datos, responsable):
    exigir_permiso(responsable, "gestionar_arriendos")
    from .reservas import vencer_reservas
    vencer_reservas(datos["maquinaria"].pk)
    empresa_id = datos["empresa"].pk
    # Sincroniza fuera de la transacción de entrega: rechazarla no debe
    # deshacer un bloqueo que acabamos de detectar.
    actualizar_bloqueo_por_atraso(empresa_id)
    try:
        return _preparar_entrega(datos=datos, responsable=responsable)
    except ValidationError:
        actualizar_bloqueo_por_atraso(empresa_id)
        raise


def confirmar_entrega(*, solicitud_id, usuario, firma):
    previa = SolicitudEntrega.objects.get(pk=solicitud_id)
    if previa.responsable_id != usuario.pk:
        raise PermissionDenied
    from .reservas import vencer_reservas
    vencer_reservas(previa.maquinaria_id)
    actualizar_bloqueo_por_atraso(previa.empresa_id)
    try:
        return _confirmar_entrega(solicitud_id=solicitud_id, usuario=usuario, firma=firma)
    except ValidationError:
        actualizar_bloqueo_por_atraso(previa.empresa_id)
        raise
