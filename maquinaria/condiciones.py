from datetime import timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import TerminosCondiciones


CLAVE_ACEPTACION = "aceptacion_pendiente"


def obtener_terminos_vigentes():
    return (TerminosCondiciones.objects
            .filter(publicado_en__lte=timezone.now())
            .order_by("-publicado_en", "-pk").first())


def bloquear_publicacion():
    # Publicar y firmar bloquean la misma última versión dentro de una
    # transacción. Después deben volver a consultar la versión vigente.
    # Así una publicación concurrente no pasa inadvertida al firmar.
    return (TerminosCondiciones.objects.select_for_update()
            .order_by("-pk").first())


def aceptacion_temporal(request, terminos):
    pendiente = request.session.get(CLAVE_ACEPTACION)
    if not isinstance(pendiente, dict) or terminos is None:
        return None
    if (pendiente.get("usuario_id") != request.user.pk
            or pendiente.get("terminos_id") != terminos.pk):
        return None
    try:
        fecha = parse_datetime(pendiente.get("aceptado_en", ""))
    except (ValueError, TypeError):
        return None
    if fecha is None or timezone.is_naive(fecha):
        return None
    # Tampoco se aceptan fechas futuras o sesiones abandonadas por más de 30 min.
    if not timedelta() <= timezone.now() - fecha <= timedelta(minutes=30):
        return None
    return fecha


def es_contratista_firmante(usuario):
    # El rol por sí solo no basta: un superusuario antiguo puede conservar
    # el valor por defecto CONTRATISTA y sigue siendo una cuenta interna.
    return (usuario.is_authenticated and usuario.is_active and not usuario.suspendida
            and usuario.rol == "CONTRATISTA" and not usuario.is_staff
            and not usuario.is_superuser and usuario.estado_aprobacion == "APROBADO")


def exigir_contratista_firmante(usuario):
    from django.core.exceptions import PermissionDenied
    if not es_contratista_firmante(usuario):
        raise PermissionDenied("La aceptación y firma de condiciones corresponde solo a contratistas habilitados.")
