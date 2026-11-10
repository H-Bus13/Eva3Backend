# Catálogo y gestión de maquinaria

## Activar

Desde la terminal del proyecto ejecutar:

```powershell
.\configurar_postgresql.ps1
```

Aplica las migraciones pendientes, incluida la 0005 de gestión de equipos y la 0006 que agrega dirección propia y obra opcional a las bodegas. Se necesita la contraseña local de PostgreSQL. No se aplicó esta migración a PostgreSQL desde el agente.

## Primeros pasos

1. Ingresar con el superusuario y abrir Maquinaria.
2. Entrar en Obras y bodegas. Crear una bodega con su dirección. La obra es opcional: dejarla vacía para una bodega de la empresa. Si la bodega está en una obra, registrar esa obra y seleccionarla.
3. Registrar maquinaria con código único, nombre, marca, modelo, bodega y lectura inicial.
4. Indicar la lectura del contador cuando se realizó la última mantención. Para una máquina nueva ingresar 0; dejar vacío si se desconoce.
5. Si la última mantención es conocida y no se cumplieron 250 horas desde ella, el equipo queda Disponible. Si se desconoce o ya se cumplió el intervalo, queda en Mantenimiento con revisión programada.

## Operaciones

- Catálogo: /maquinaria/, con búsqueda por código/nombre, filtros por estado/bodega y páginas de 12 equipos.
- Detalle: datos, horas, ubicación, responsable del registro e historial.
- Edición: solo nombre, marca y modelo. Código, horas, ubicación y estado no son editables desde ese formulario.
- Traslado: únicamente desde Disponible, a otra bodega, con motivo y confirmación. Guarda origen y destino.
- Baja: únicamente desde Disponible, con motivo y confirmación. No elimina el equipo.
- Reactivación: únicamente desde Dada de baja, por un superusuario o administrador con permiso específico. Exige motivo y confirmación, pasa a Mantenimiento y programa revisión. No altera las horas ni borra la baja anterior.
- No se permite operar si hay un arriendo, sesión de uso o mantenimiento abierto, aunque el campo estado se haya cambiado por otra vía.
- Obras y bodegas: crear y corregir datos con permisos. La obra de una bodega existente no se cambia, para no alterar su trazabilidad; se crea otra bodega.

Las transacciones y los bloqueos de fila hacen que ubicación/estado e historial se guarden juntos. No se ofrecen eliminación de maquinaria ni cambios libres de estado.

## Permisos

Consultar catálogo, detalle y ubicaciones requiere una sesión normal habilitada. Las consultas limitadas de solicitudes no acceden.

- add_maquinaria: registrar maquinaria.
- change_maquinaria: editar sus datos.
- trasladar_maquinaria: trasladar.
- dar_baja_maquinaria: dar de baja.
- reactivar_maquinaria: reactivar, además de ser administrador o superusuario.
- add_obra/change_obra y add_bodega/change_bodega: gestionar ubicaciones.

El superusuario existente puede realizar todas estas operaciones desde los templates propios.

## Límites del bloque

La programación inicial y la reactivación crean una revisión pendiente. La ejecución y finalización de esa revisión se implementarán con el módulo de mantenciones. Por ahora, un equipo reactivado no puede volver directamente a Disponible.

Las horas no aumentan desde el catálogo: eso corresponde al próximo flujo de uso/arriendos. Los equipos que existían antes de esta migración quedan marcados para revisión, sin inventar lecturas iniciales, autores ni fechas históricas. El futuro flujo de arriendo deberá comprobar tanto el estado como las revisiones pendientes.

## Verificación

70 pruebas aprobadas en SQLite temporal. Incluyen registro con lecturas conocidas/desconocidas, límite de 250 horas, códigos duplicados sin distinción de mayúsculas, edición restringida, traslado, baja, reactivación, historial transaccional, bloqueo de operaciones abiertas, permisos, confirmación, CSRF, filtros y paginación; también se conservaron las pruebas de usuarios y firmas.

## Bodegas centrales y de obra

Cada bodega tiene su propia dirección. La obra es opcional al crearla, de modo que la maquinaria puede permanecer en una bodega central sin crear una obra ficticia. La obra de destino del trabajo se seleccionará en el arriendo, independientemente de la bodega de origen.

La migración 0006 conserva las asociaciones actuales. Las direcciones de las bodegas anteriores quedan vacías y se muestran como Sin registrar; pueden completarse con Editar bodega. No se copia automáticamente la dirección de una obra, porque no necesariamente coincide con la entrada de la bodega.

Se mantiene la restricción de no cambiar la obra de una bodega ya registrada para conservar su trazabilidad.
