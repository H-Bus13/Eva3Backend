from datetime import timedelta

from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.utils.dateparse import parse_datetime

from .models import Usuario


CLAVE_CONSULTA = "consulta_solicitud"


def iniciar_consulta_solicitud(request, usuario):
    # Solo se identifica al solicitante. No se llama a login() ni se crean
    # claves de autenticación de Django para acceder a las demás funciones.
    request.session.cycle_key()
    request.session[CLAVE_CONSULTA] = {
        "usuario_id": usuario.pk,
        "verificacion": usuario.get_session_auth_hash(),
        "iniciada_en": timezone.now().isoformat(),
    }


def obtener_solicitante(request):
    datos = request.session.get(CLAVE_CONSULTA)
    if not isinstance(datos, dict):
        return None
    try:
        fecha = parse_datetime(datos.get("iniciada_en", ""))
        identificador = datos.get("usuario_id")
        if not isinstance(identificador, int) or isinstance(identificador, bool):
            return None
    except (TypeError, ValueError):
        return None
    if (fecha is None or timezone.is_naive(fecha)
            or not timedelta() <= timezone.now() - fecha <= timedelta(minutes=30)):
        return None
    usuario = Usuario.objects.select_related("empresa").filter(
        pk=identificador, rol=Usuario.Rol.CONTRATISTA,
        is_staff=False, is_superuser=False, suspendida=False,
        estado_aprobacion__in=Usuario.EstadoAprobacion.values,
    ).first()
    verificacion = datos.get("verificacion")
    if (usuario is None or not isinstance(verificacion, str)
            or not constant_time_compare(verificacion, usuario.get_session_auth_hash())):
        return None
    # Se permite leer que fue aprobada, pero esto no habilita la sesión normal.
    # Debe ingresar nuevamente para que el backend compruebe su acceso actual.
    return usuario

