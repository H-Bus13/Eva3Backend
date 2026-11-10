# Administración de usuarios y diseño Bootstrap

## Activar

Desde la terminal del proyecto:

```powershell
.\configurar_postgresql.ps1
```

La migración 0012 incorpora la suspensión administrativa, el permiso gestionar_usuarios, el historial administrativo y el control de operaciones simultáneas. No crea usuarios ni contraseñas en PostgreSQL, ni cambia los roles o privilegios de las cuentas existentes.

Después de aplicar, ingresar con el superusuario y abrir Usuarios. Recargar con Ctrl+F5 para actualizar los estilos. Django Admin continúa deshabilitado.

## Pantallas

- /usuarios/: listado paginado con búsqueda por nombre, usuario, RUT o correo y filtros por rol, estado y empresa.
- /usuarios/nuevo/: creación de bodegueros y administradores. Solo un superusuario ve y puede usar la opción de crear otro superusuario.
- /usuarios/ID/: detalle, permisos e historial con comparación de antes/después.
- Edición de nombres/correo; rol y permisos de cuentas internas; activación y suspensión con motivo.

El RUT, el identificador de usuario y la empresa no se editan desde estas pantallas por su relación con firmas y antecedentes. El registro y la revisión de contratistas conservan sus flujos propios.

## Perfiles iniciales

Bodeguero: registro/edición/traslado/baja de maquinaria, registro/edición de ubicaciones, entregas/recepciones y consulta/programación de mantenciones. Los permisos pueden ajustarse posteriormente.

Administrador: funciones operativas de BuildCorp, incluyendo administración de usuarios. Un creador que no es superusuario solo asigna la intersección entre el perfil y sus propios permisos.

El rol no sustituye a los permisos. Para administrar cuentas se requiere gestionar_usuarios y ser administrador o superusuario. No se ofrece eliminación de registros ni permisos internos de otras aplicaciones.

## Protecciones

- Nadie modifica su propia cuenta desde administración.
- Un administrador común no modifica superusuarios ni cuentas que conservan permisos superiores a los suyos, incluso si están inactivas.
- Solo un superusuario concede o retira privilegios de superusuario.
- No puede quedar el sistema sin un superusuario activo. Las operaciones comparten una fila de control y releen al actor después de adquirir el bloqueo, evitando usar permisos revocados mientras esperaba.
- La creación usa validadores de contraseña y set_password. Las contraseñas no se muestran ni se guardan en el historial.
- Los cambios requieren motivo y se guardan junto con el historial en una transacción.
- Los permisos efectivos procedentes de grupos externos se convierten en asignaciones directas al editar permisos. Se conservan los accesos ajenos al panel y se registra el cambio de grupos. No se otorgan permisos externos nuevos.

## Suspensión y aprobación

La suspensión administrativa es independiente de la aprobación. Suspender invalida el acceso normal y también la consulta limitada de solicitudes. Reactivar un contratista no aprueba su solicitud: sigue limitado mientras esté pendiente o rechazado.

Aprobar una solicitud no elimina una suspensión administrativa. Primero debe retirarse desde Usuarios. Los usuarios anteriores reciben suspendida=False; el estado is_active que ya tenían se conserva.

## Bootstrap

Bootstrap 5.3.8 CSS y JS están guardados en maquinaria/static/vendor/bootstrap, junto con su licencia MIT. Se verificaron los hashes SHA-384 oficiales. No se necesita conexión a un CDN al navegar.

base.html contiene la navegación adaptable y los mensajes. buildcorp.css personaliza colores, tarjetas, filtros y tablas. Un renderer de formularios aplica las clases de Bootstrap a los formularios existentes sin cambiar sus rutas, nombres de campos ni los IDs usados por la firma y el contador.

## Verificación

175 pruebas aprobadas en SQLite temporal. Incluyen creación de cuentas/superusuarios, límites de permisos, privilegios en cuentas inactivas, suspensión de sesiones y consultas limitadas, aprobación independiente, historial sin contraseñas, rollback, último superusuario, filtros, CSRF y todos los módulos anteriores.

Se revisaron visualmente el listado y la creación de usuarios en escritorio, y el listado y menú adaptable en un ancho móvil de 390 px, con datos ficticios en una base aislada. El servidor de esa revisión fue detenido. No se crearon cuentas de demostración en tu base real ni se aplicó la migración a PostgreSQL desde el agente.
