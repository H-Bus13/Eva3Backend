from django.contrib.auth.models import Permission
from django.db.models import Q


# Solo permisos usados por las pantallas de BuildCorp. Nunca se ofrecen
# eliminación de registros ni permisos internos de auth/contenttypes.
CODIGOS = {
    "gestionar_usuarios", "aprobar_contratista", "publicar_terminos", "consultar_firmas",
    "add_maquinaria", "change_maquinaria", "trasladar_maquinaria", "dar_baja_maquinaria", "reactivar_maquinaria",
    "add_obra", "change_obra", "desactivar_obra", "reactivar_obra",
    "add_bodega", "change_bodega", "desactivar_bodega", "reactivar_bodega",
    "view_mantenimiento", "add_mantenimiento", "iniciar_mantenimiento", "finalizar_mantenimiento",
    "gestionar_arriendos", "gestionar_bloqueos_empresa",
}
BODEGUERO = {
    "add_maquinaria", "change_maquinaria", "trasladar_maquinaria", "dar_baja_maquinaria",
    "add_obra", "change_obra", "add_bodega", "change_bodega",
    "gestionar_arriendos", "view_mantenimiento", "add_mantenimiento",
}


def permisos_operativos():
    return Permission.objects.filter(content_type__app_label="maquinaria", codename__in=CODIGOS).select_related("content_type").order_by("name")


def permisos_efectivos(usuario):
    # No usamos get_all_permissions para el destino: en cuentas inactivas
    # devuelve vacío y podría ocultar privilegios que conserva almacenados.
    return Permission.objects.filter(Q(user=usuario) | Q(group__user=usuario)).select_related("content_type").distinct()


def nombres_permisos(permisos):
    return {f"{p.content_type.app_label}.{p.codename}" for p in permisos}


def permisos_otorgables(actor):
    consulta = permisos_operativos()
    if not actor.is_superuser:
        consulta = consulta.filter(pk__in=permisos_efectivos(actor).values("pk"))
    return consulta
