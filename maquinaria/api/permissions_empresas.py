from rest_framework.permissions import BasePermission


class PermisosEmpresa(BasePermission):
    message = "No tienes permiso para esta operación."

    def has_permission(self, request, view):
        usuario = request.user
        if view.action is None:
            return True
        if view.action in ("bloquear", "desbloquear"):
            return usuario.has_perm("maquinaria.gestionar_bloqueos_empresa")
        if view.action == "atrasos":
            return usuario.has_perm("maquinaria.gestionar_arriendos")
        return (usuario.has_perm("maquinaria.gestionar_arriendos")
                or usuario.has_perm("maquinaria.gestionar_bloqueos_empresa"))
