from rest_framework.permissions import BasePermission


class PermisosMantenimiento(BasePermission):
    message = "No tienes permiso para esta operación."

    def has_permission(self, request, view):
        permisos = {
            "list": "view_mantenimiento", "retrieve": "view_mantenimiento",
            "metadata": "view_mantenimiento", "create": "add_mantenimiento",
            "iniciar": "iniciar_mantenimiento", "finalizar": "finalizar_mantenimiento",
        }
        # Un método no implementado debe responder 405, sin permitir cambios.
        if view.action is None:
            return True
        permiso = permisos.get(view.action)
        return bool(permiso and request.user.has_perm(f"maquinaria.{permiso}"))
