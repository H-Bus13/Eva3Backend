from django.core.exceptions import PermissionDenied


def exigir_permiso(usuario, permiso):
    if not usuario.is_authenticated or not usuario.is_active or not usuario.has_perm(f"maquinaria.{permiso}"):
        raise PermissionDenied
