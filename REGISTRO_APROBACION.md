# Registro y aprobación de contratistas

## Poner en marcha

En la terminal PowerShell del proyecto, ejecutar:

```powershell
.\configurar_postgresql.ps1
.\env\Scripts\python.exe manage.py runserver
```

El primer comando solicita la contraseña local de PostgreSQL y aplica también la migración de aprobación de cuentas. Mantener esa terminal abierta para iniciar el servidor con la misma conexión.

## Pantallas

- /registro/: solicitud pública de cuenta de contratista.
- /ingresar/: inicio de sesión.
- /: inicio protegido.
- /cuentas/pendientes/: revisión de solicitudes, solo con el permiso aprobar_contratista o con un superusuario activo.
- /salir/: cierre de sesión por POST desde el botón del sistema.

El registro público no crea administradores, bodegueros ni superusuarios. El rol escrito en una solicitud no permite obtener permisos. Los usuarios internos necesitan permisos asignados por una cuenta autorizada.

Si todavía no existe ninguna cuenta administrativa, el arranque inicial puede hacerse desde la terminal local con `env\Scripts\python.exe manage.py createsuperuser`, que solicitará el RUT y la contraseña. Esta cuenta ingresa por /ingresar/ y revisa mediante los templates propios: no hay Django Admin habilitado. La creación de cuentas internas desde una pantalla protegida queda para el siguiente bloque de trabajo.

## Reglas

- La cuenta nueva queda PENDIENTE e inactiva, y no puede iniciar sesión.
- El registro valida y normaliza RUT de persona y empresa mediante módulo 11.
- Si existe la empresa, no se modifica su razón social ni su bloqueo desde el registro público.
- Antes de aprobar se debe verificar externamente que la persona está autorizada por la empresa. El RUT no demuestra ese vínculo.
- Aprobar habilita la cuenta; rechazar exige un motivo y la mantiene inactiva.
- Ambas acciones conservan responsable, fecha y observaciones.
- Aprobar no elimina un bloqueo de empresa. La restricción de nuevos arriendos se incorporará al crear el proceso de arriendo.
- Las cuentas contratistas existentes reciben estado PENDIENTE al aplicar la migración; necesitan revisión. Las cuentas internas y superusuarios activos no dependen de ese estado para autenticarse.
- No se agregaron aún la firma, condiciones, arriendos ni tareas automáticas.

## Verificación realizada

20 pruebas automatizadas aprobadas en una base SQLite temporal, sin tocar datos de PostgreSQL. Se verificaron registro, normalización de RUT, duplicados, contraseñas cifradas, autenticación, privilegios, aprobación, rechazo, protección CSRF y reglas previas de los modelos. La migración en PostgreSQL requiere ejecutar el comando de inicio con la contraseña local.
