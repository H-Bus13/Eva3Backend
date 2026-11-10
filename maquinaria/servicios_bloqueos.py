from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import Arriendo, Empresa, HistorialBloqueoEmpresa
from .permisos import exigir_permiso


def arriendos_atrasados(empresa_id=None):
    consulta = Arriendo.objects.filter(devolucion_prevista__lt=timezone.now(),
        recibido_en__isnull=True, devuelto_en__isnull=True)
    return consulta.filter(empresa_id=empresa_id) if empresa_id is not None else consulta


@transaction.atomic
def actualizar_bloqueo_por_atraso(empresa_id):
    # Comparte el bloqueo de empresa con entregas y recepciones. NO KEY
    # UPDATE permite insertar referencias de historial mientras se consulta.
    empresa = Empresa.objects.select_for_update(no_key=True).get(pk=empresa_id)
    atrasos = arriendos_atrasados(empresa.pk).count()
    debe_bloquear = atrasos > 0
    empresa.cambio_automatico = empresa.bloqueada_por_atraso != debe_bloquear
    if empresa.cambio_automatico:
        empresa.bloqueada_por_atraso = debe_bloquear
        empresa.save(update_fields=["bloqueada_por_atraso"])
        HistorialBloqueoEmpresa.objects.create(empresa=empresa, origen="AUTOMATICO",
            accion="BLOQUEO" if debe_bloquear else "DESBLOQUEO",
            motivo=(f"Hay {atrasos} arriendo(s) vencido(s) sin recepción física."
                    if debe_bloquear else "No quedan arriendos vencidos sin recepción física."))
    return empresa


def revisar_atrasos(empresa_id=None):
    if empresa_id is None:
        ids = Empresa.objects.filter(Q(pk__in=arriendos_atrasados().values("empresa_id"))
                                     | Q(bloqueada_por_atraso=True)).order_by("pk").values_list("pk", flat=True)
    else:
        ids = [empresa_id]
    revisadas, cambios = 0, 0
    # Una transacción por empresa, sin retener bloqueos de todas a la vez.
    for pk in ids.iterator() if hasattr(ids, "iterator") else ids:
        empresa = actualizar_bloqueo_por_atraso(pk)
        revisadas += 1
        cambios += int(empresa.cambio_automatico)
    return revisadas, cambios


@transaction.atomic
def cambiar_bloqueo_manual(*, empresa_id, bloquear, motivo, responsable):
    exigir_permiso(responsable, "gestionar_bloqueos_empresa")
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Indica el motivo del cambio de bloqueo.")
    if type(bloquear) is not bool:
        raise ValidationError("Acción de bloqueo inválida.")
    empresa = Empresa.objects.select_for_update(no_key=True).get(pk=empresa_id)
    if empresa.bloqueada == bloquear:
        raise ValidationError("El bloqueo manual ya tiene ese estado.")
    empresa.bloqueada = bloquear
    empresa.motivo_bloqueo = motivo if bloquear else ""
    empresa.save(update_fields=["bloqueada", "motivo_bloqueo"])
    HistorialBloqueoEmpresa.objects.create(empresa=empresa, origen="MANUAL",
        accion="BLOQUEO" if bloquear else "DESBLOQUEO", motivo=motivo, responsable=responsable)
    return empresa


def contexto_bloqueo(usuario):
    if not usuario.empresa_id:
        return {"empresa_alerta": None, "atrasos_empresa": 0}
    empresa = actualizar_bloqueo_por_atraso(usuario.empresa_id)
    return {"empresa_alerta": empresa, "atrasos_empresa": arriendos_atrasados(empresa.pk).count()}
