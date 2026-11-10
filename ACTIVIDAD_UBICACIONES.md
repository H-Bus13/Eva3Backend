# Desactivación y reactivación de ubicaciones

## Activar

Ejecutar desde la terminal del proyecto:

```powershell
.\configurar_postgresql.ps1
```

La migración 0007 agrega activa a obras y bodegas, permisos específicos e historial de ubicaciones. Todos los registros existentes permanecen activos. No borra ni reasigna equipos y no inventa eventos históricos.

## Uso

En Obras y bodegas se muestran por defecto las ubicaciones activas. El filtro permite ver Inactivas o Todas. Cada ubicación dispone de historial y, según permisos, acciones separadas de editar, desactivar y reactivar.

- Desactivar exige motivo y confirmación.
- Una bodega no puede cerrarse con maquinaria que no esté dada de baja. Primero se traslada a otra bodega habilitada. Se comprueban también arriendos abiertos asociados a sus equipos.
- Una obra no puede cerrarse con bodegas activas o arriendos pendientes de devolución.
- Para reactivar se requiere ser administrador o superusuario y tener el permiso correspondiente. Antes de reactivar una bodega de obra hay que reactivar su obra.
- Desactivar y reactivar no cambia los estados ni las horas de las máquinas.
- No se permite reactivar una máquina dada de baja en una bodega inactiva o cuya obra esté inactiva. Primero hay que habilitar la ubicación.
- Los desplegables de alta y traslado de equipos solo ofrecen bodegas activas, centrales o con obra activa. Las bodegas inactivas siguen disponibles para consultas del inventario y antecedentes históricos.
- No se puede crear una bodega en una obra inactiva.
- Las ediciones de nombre y dirección no pueden cambiar el campo activa; se usa la acción específica con su motivo.

## Historial y seguridad

Cada cambio guarda ubicación, acción, fecha del servidor, responsable y motivo. El cambio y su evento son parte de una transacción: si falla el historial, se revierte la operación.

Los servicios comparten el orden de bloqueo obras, bodegas y máquinas, consultadas por ID en orden, para coordinar cierres, altas y traslados. Se releen los estados antes de guardar, aunque el formulario se haya abierto antes de una desactivación. Las consultas con bloqueo evitan joins sobre relaciones opcionales para ser compatibles con PostgreSQL.

El próximo servicio de arriendos deberá utilizar el mismo bloqueo de la obra de destino y la validación de ubicación activa antes de crear un arriendo. Todavía no existe ese flujo en la aplicación.

Permisos: desactivar_obra, reactivar_obra, desactivar_bodega, reactivar_bodega. El superusuario existente dispone de ellos al aplicar la migración. Las pantallas requieren sesión normal; el acceso limitado de solicitudes no habilita estas funciones.

## Verificación

89 pruebas aprobadas en SQLite temporal, incluyendo las reglas de cierre, reapertura por administrador, historial, rollback, filtrado, credenciales/permisos, confirmación, CSRF y rechazo de objetos leídos antes de desactivar una ubicación. La migración y el comportamiento concurrente de bloqueos en PostgreSQL no se probaron contra tu base desde el agente; requieren la conexión local con tu contraseña.
