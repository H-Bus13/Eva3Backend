from rest_framework.permissions import BasePermission


class PermisosArriendos(BasePermission):
    message = "No tienes permiso para realizar esta operación de arriendo."

    def has_permission(self, request, view):
        if view.action in ("create", "cancelar", "recibir"):
            return request.user.has_perm("maquinaria.gestionar_arriendos")
        return True

    def has_object_permission(self, request, view, obj):
        if view.action == "confirmar":
            responsable_id = obj.responsable_id if hasattr(obj, "responsable_id") else obj.arriendo.responsable_id
            return responsable_id == request.user.pk
        if view.action == "iniciar_uso":
            return obj.responsable_id == request.user.pk
        return True
