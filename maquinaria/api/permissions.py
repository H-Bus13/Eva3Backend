from rest_framework.permissions import BasePermission

from maquinaria.models import Usuario


class CuentaHabilitada(BasePermission):
    message = "Necesitas una cuenta habilitada para usar la API."

    def has_permission(self, request, view):
        usuario = request.user
        if not usuario.is_authenticated or not usuario.is_active or usuario.suspendida:
            return False
        # La sesión limitada de solicitudes no es una sesión autenticada.
        # Este control también protege autenticaciones alternativas futuras.
        return usuario.is_superuser or usuario.rol != Usuario.Rol.CONTRATISTA or usuario.estado_aprobacion == "APROBADO"


class PermisosInventario(BasePermission):
    message = "No tienes permiso para realizar esta operación."

    def has_permission(self, request, view):
        accion = view.action
        if accion is None or accion in ("list", "retrieve", "historial", "metadata"):
            return True
        recurso = view.recurso
        codigos = {
            "create": f"add_{recurso}", "partial_update": f"change_{recurso}",
            "trasladar": "trasladar_maquinaria", "baja": "dar_baja_maquinaria",
            "desactivar": f"desactivar_{recurso}", "reactivar": f"reactivar_{recurso}",
        }
        permiso = codigos.get(accion)
        if not permiso or not request.user.has_perm(f"maquinaria.{permiso}"):
            return False
        if accion == "reactivar":
            return request.user.is_superuser or request.user.rol == Usuario.Rol.ADMINISTRADOR
        return True

