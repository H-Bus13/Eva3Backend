from django.contrib.auth.backends import ModelBackend

from .models import Usuario


class BackendAprobacion(ModelBackend):
    def user_can_authenticate(self, user):
        # Se revisa también al recuperar una sesión existente. No basta con
        # esconder botones: una cuenta pendiente nunca debe autenticarse.
        habilitado = super().user_can_authenticate(user) and not user.suspendida
        if user.is_superuser or user.rol != Usuario.Rol.CONTRATISTA:
            return habilitado
        return habilitado and user.estado_aprobacion == Usuario.EstadoAprobacion.APROBADO

