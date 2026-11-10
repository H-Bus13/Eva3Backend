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


# Etiquetas de presentación: no cambian códigos, IDs ni permisos otorgados.
ETIQUETAS_PERMISOS = {
    "gestionar_usuarios": "Administrar usuarios y permisos",
    "aprobar_contratista": "Aprobar o rechazar cuentas de contratistas",
    "publicar_terminos": "Publicar términos y condiciones",
    "consultar_firmas": "Consultar firmas y comprobantes de contratistas",
    "add_maquinaria": "Registrar maquinaria",
    "change_maquinaria": "Editar datos y tarifa de maquinaria",
    "trasladar_maquinaria": "Trasladar maquinaria entre bodegas",
    "dar_baja_maquinaria": "Dar de baja maquinaria",
    "reactivar_maquinaria": "Reactivar maquinaria para revisión",
    "add_obra": "Registrar obras",
    "change_obra": "Editar obras",
    "desactivar_obra": "Desactivar obras",
    "reactivar_obra": "Reactivar obras",
    "add_bodega": "Registrar bodegas",
    "change_bodega": "Editar bodegas",
    "desactivar_bodega": "Desactivar bodegas",
    "reactivar_bodega": "Reactivar bodegas",
    "view_mantenimiento": "Consultar mantenimientos",
    "add_mantenimiento": "Programar mantenimientos",
    "iniciar_mantenimiento": "Iniciar mantenimientos",
    "finalizar_mantenimiento": "Finalizar mantenimientos",
    "gestionar_arriendos": "Revisar solicitudes y gestionar entregas y devoluciones",
    "gestionar_bloqueos_empresa": "Aplicar y retirar bloqueos manuales de empresas",
    "revisar_solicitud_arriendo": "Aprobar o rechazar solicitudes de arriendo",
}


def etiqueta_permiso(permiso):
    if permiso.content_type.app_label == "maquinaria" and permiso.codename in ETIQUETAS_PERMISOS:
        return ETIQUETAS_PERMISOS[permiso.codename]
    # Los permisos externos conservados también pueden usar nombres CRUD
    # automáticos de Django; se presenta su acción en español.
    accion, _, modelo = permiso.codename.partition("_")
    verbos = {"add": "Agregar", "change": "Modificar", "view": "Consultar", "delete": "Eliminar"}
    clase = permiso.content_type.model_class()
    if accion in verbos and clase is not None:
        return f"{verbos[accion]} {clase._meta.verbose_name}"
    return permiso.name


def datos_permisos(permisos):
    return [{"id": p.pk, "codename": p.codename, "name": etiqueta_permiso(p)} for p in permisos]
