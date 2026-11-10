from django.utils import timezone

from .models import Mantenimiento, MovimientoMaquinaria
from .servicios_maquinaria import registrar_evento


def asegurar_revision_por_uso(*, maquina, responsable):
    # Se llama con la máquina bloqueada dentro de una transacción. Incluye
    # la sesión en marcha al comprobar las horas desde la última revisión.
    if not maquina.requiere_mantencion_por_uso:
        return False
    ya_pendiente = maquina.revision_pendiente
    if not ya_pendiente:
        maquina.revision_pendiente = True
        maquina.save(update_fields=["revision_pendiente"])
    if not maquina.mantenimientos.filter(finalizado_en__isnull=True, fecha_programada__lte=timezone.localdate()).exists():
        Mantenimiento.objects.create(maquinaria=maquina, fecha_programada=timezone.localdate(),
            descripcion="Revisión preventiva: se cumplieron 250 horas de uso desde la última mantención.",
            programado_por=responsable)
    if not ya_pendiente:
        registrar_evento(maquina, responsable, MovimientoMaquinaria.Tipo.ALERTA_USO,
            "Intervalo de mantención cumplido. La sesión actual puede detenerse; no se permiten nuevos inicios.",
            maquina.estado, maquina.bodega)
    return True
