from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import ControlAdministracion, HistorialAdministracionUsuario, Usuario
from .permisos import exigir_permiso
from .validators import normalizar_rut
from .politica_usuarios import BODEGUERO, nombres_permisos, permisos_efectivos, permisos_operativos, permisos_otorgables


def exigir_administrador(actor):
    exigir_permiso(actor, "gestionar_usuarios")
    if actor.suspendida or not (actor.is_superuser or actor.rol == Usuario.Rol.ADMINISTRADOR):
        raise PermissionDenied


def bloquear_control(actor_id, destino_id=None):
    # Todas las operaciones administrativas se serializan mediante una fila
    # única. Se relee al actor después de esperar: un administrador suspendido
    # mientras esperaba no puede ejecutar un cambio con permisos antiguos.
    ControlAdministracion.objects.get_or_create(pk=1)
    ControlAdministracion.objects.select_for_update().get(pk=1)
    ids = {actor_id} | ({destino_id} if destino_id is not None else set())
    cuentas = {u.pk: u for u in Usuario.objects.select_for_update(no_key=True).filter(pk__in=ids).order_by("pk")}
    actor = cuentas[actor_id]
    exigir_administrador(actor)
    return actor, cuentas.get(destino_id)


def validar_destino(actor, destino):
    if actor.pk == destino.pk:
        raise ValidationError("No puedes modificar tu propia cuenta desde administración.")
    if not actor.is_superuser:
        if destino.is_superuser:
            raise PermissionDenied("Solo un superusuario puede modificar esta cuenta.")
        if not nombres_permisos(permisos_efectivos(destino)).issubset(actor.get_all_permissions()):
            raise PermissionDenied("Esta cuenta conserva permisos superiores a los tuyos.")


def proteger_ultimo_superusuario(destino, *, superusuario, activo, suspendida):
    habilitado_antes = destino.is_superuser and destino.is_active and not destino.suspendida
    habilitado_despues = superusuario and activo and not suspendida
    if habilitado_antes and not habilitado_despues:
        if not Usuario.objects.filter(is_superuser=True, is_active=True, suspendida=False).exclude(pk=destino.pk).exists():
            raise ValidationError("Debe quedar al menos un superusuario activo.")


def estado_cuenta(usuario):
    # Lista explícita: nunca se registran contraseñas, hashes o claves de sesión.
    return {
        "username": usuario.username, "nombre": usuario.first_name, "apellido": usuario.last_name,
        "email": usuario.email, "rol": usuario.rol, "activa": usuario.is_active,
        "suspendida": usuario.suspendida, "superusuario": usuario.is_superuser,
        "aprobacion": usuario.estado_aprobacion,
        "permisos": sorted(nombres_permisos(permisos_efectivos(usuario))),
        "grupos": list(usuario.groups.order_by("name").values_list("name", flat=True)),
    }


def guardar_evento(actor, destino, accion, motivo, anterior):
    motivo = motivo.strip()
    if not motivo:
        raise ValidationError("Debes indicar el motivo del cambio.")
    HistorialAdministracionUsuario.objects.create(usuario=destino, responsable=actor,
        accion=accion, motivo=motivo, datos_anteriores=anterior, datos_nuevos=estado_cuenta(destino))


@transaction.atomic
def crear_usuario_interno(*, datos, actor):
    actor, _ = bloquear_control(actor.pk)
    rol = datos["rol"]
    superusuario = datos.get("crear_superusuario", False)
    if rol not in (Usuario.Rol.BODEGUERO, Usuario.Rol.ADMINISTRADOR):
        raise ValidationError("Usa el registro público para crear contratistas.")
    if type(superusuario) is not bool or (superusuario and not actor.is_superuser):
        raise PermissionDenied
    if superusuario and rol != Usuario.Rol.ADMINISTRADOR:
        raise ValidationError("Un superusuario debe registrarse con rol Administrador.")
    destino = Usuario(**{campo: datos.get(campo, "") for campo in ("username", "first_name", "last_name", "email", "rut")},
        rol=rol, is_active=True, suspendida=False, estado_aprobacion="APROBADO",
        is_superuser=superusuario, is_staff=superusuario)
    destino.rut = normalizar_rut(destino.rut)
    validate_password(datos["password1"], destino)
    destino.set_password(datos["password1"])
    destino.full_clean()
    destino.save()
    perfil = permisos_otorgables(actor)
    if rol == Usuario.Rol.BODEGUERO:
        perfil = perfil.filter(codename__in=BODEGUERO)
    destino.user_permissions.set(perfil)
    guardar_evento(actor, destino, "CREACION", datos["motivo"], {})
    return destino


@transaction.atomic
def editar_datos_usuario(*, usuario_id, datos, actor):
    actor, destino = bloquear_control(actor.pk, usuario_id)
    validar_destino(actor, destino)
    anterior = estado_cuenta(destino)
    # RUT, username y empresa permanecen estables: están vinculados a firmas
    # e historial. No se convierten contratistas en cuentas internas.
    for campo in ("first_name", "last_name", "email"):
        if campo in datos:
            setattr(destino, campo, datos[campo])
    destino.full_clean()
    destino.save(update_fields=["first_name", "last_name", "email"])
    guardar_evento(actor, destino, "DATOS", datos["motivo"], anterior)
    return destino


@transaction.atomic
def cambiar_permisos_usuario(*, usuario_id, datos, actor):
    actor, destino = bloquear_control(actor.pk, usuario_id)
    validar_destino(actor, destino)
    if destino.rol == Usuario.Rol.CONTRATISTA and not destino.is_superuser:
        raise ValidationError("Los contratistas conservan el acceso de su aprobación; no reciben permisos internos.")
    rol = datos["rol"]
    if rol not in (Usuario.Rol.ADMINISTRADOR, Usuario.Rol.BODEGUERO):
        raise ValidationError("Selecciona un rol interno válido.")
    superusuario = datos.get("superusuario", destino.is_superuser)
    if type(superusuario) is not bool or (superusuario != destino.is_superuser and not actor.is_superuser):
        raise PermissionDenied
    if superusuario and rol != Usuario.Rol.ADMINISTRADOR:
        raise ValidationError("Un superusuario debe conservar el rol Administrador.")
    seleccionados = list(datos.get("permisos", []))
    permitidos = set(permisos_otorgables(actor).values_list("pk", flat=True))
    if any(p.pk not in permitidos for p in seleccionados):
        raise PermissionDenied("No puedes conceder esos permisos.")
    proteger_ultimo_superusuario(destino, superusuario=superusuario, activo=destino.is_active, suspendida=destino.suspendida)
    anterior = estado_cuenta(destino)
    # Si había grupos externos, se conservan sus permisos efectivos como
    # asignaciones directas. Los permisos ajenos al panel no se eliminan.
    externos = list(permisos_efectivos(destino).exclude(pk__in=permisos_operativos().values("pk")))
    destino.groups.clear()
    destino.user_permissions.set(seleccionados + externos)
    destino.rol = rol
    destino.is_superuser = superusuario
    destino.is_staff = superusuario
    destino.save(update_fields=["rol", "is_superuser", "is_staff"])
    guardar_evento(actor, destino, "PERMISOS", datos["motivo"], anterior)
    return destino


@transaction.atomic
def cambiar_estado_usuario(*, usuario_id, activar, motivo, actor):
    actor, destino = bloquear_control(actor.pk, usuario_id)
    validar_destino(actor, destino)
    if type(activar) is not bool:
        raise ValidationError("Acción inválida.")
    if destino.suspendida == (not activar) and destino.is_active == activar:
        raise ValidationError("La cuenta ya tiene ese estado administrativo.")
    proteger_ultimo_superusuario(destino, superusuario=destino.is_superuser, activo=activar, suspendida=not activar)
    anterior = estado_cuenta(destino)
    destino.suspendida = not activar
    destino.is_active = activar
    destino.save(update_fields=["suspendida", "is_active"])
    guardar_evento(actor, destino, "ACTIVACION" if activar else "SUSPENSION", motivo, anterior)
    return destino


