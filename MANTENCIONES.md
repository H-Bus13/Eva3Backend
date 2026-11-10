# Gestión de mantenciones

## Activar

Ejecutar desde la terminal del proyecto:

```powershell
.\configurar_postgresql.ps1
```

Aplica la migración 0008: aptitud del resultado, autor de programación y finalización, permisos, tipos de evento y restricciones de fechas/intervención única en curso. Los registros previos conservan sus fechas; no se inventa la autoría ni el resultado de aptitud.

## Recorrido

Con el superusuario, abrir Mantenciones desde el menú. También se puede entrar desde el detalle de una máquina mediante Ver mantenciones.

1. El listado muestra pendientes, en curso y finalizadas, con filtros por equipo y paginación.
2. Programar registra equipo, fecha y trabajo previsto. Para una fecha futura conserva la disponibilidad actual; para hoy o una fecha anterior exige ausencia de uso/arriendo y deja el equipo en Mantenimiento.
3. Las órdenes creadas previamente al registrar maquinaria o reactivarla también aparecen y se pueden iniciar.
4. Iniciar requiere confirmación, ubicación habilitada, equipo no dado de baja ni en uso, ausencia de arriendos/sesiones abiertas y de otra mantención en curso. Registra fecha y responsable.
5. Finalizar requiere trabajo realizado, resultado de aptitud y confirmación. Registra fecha, autor y lectura del contador.
6. Si fue satisfactoria, actualiza la referencia de última mantención sin reiniciar el uso total. Retorna a Disponible solo si la ubicación está activa y no hay otras revisiones exigibles pendientes.
7. Si no fue satisfactoria, conserva la referencia anterior y mantiene Mantenimiento. Si no hay otra revisión exigible pendiente, crea una orden de seguimiento para continuar sin sobrescribir el trabajo finalizado.

Ejemplo: 900 horas totales y última revisión a las 650. Al finalizar satisfactoriamente, conserva 900 horas y el siguiente ciclo de 250 horas se cumple a las 1150.

Una revisión satisfactoria puede quedar finalizada manteniendo el equipo en Mantenimiento cuando hay otra revisión exigible. Esa otra orden debe resolverse para liberar el equipo. Una revisión futura no impide liberarlo después de una intervención satisfactoria.

## Fechas y disponibilidad

Los requisitos de mantención se calculan también por las fechas de las órdenes abiertas. Al llegar la fecha programada, la propiedad bloqueada_por_mantencion y las advertencias del catálogo/detalle lo detectan, aunque nadie haya cambiado el campo estado. Una programación futura no cambia ese campo por anticipado.

El futuro servicio de arriendos deberá exigir estado Disponible y bloqueada_por_mantencion=False, además de ubicación habilitada. Este bloque no agrega todavía arriendos, timer ni tareas periódicas.

## Seguridad y trazabilidad

Permisos: view_mantenimiento para consultar listado/detalle, add_mantenimiento para programar, iniciar_mantenimiento y finalizar_mantenimiento para sus acciones. El superusuario dispone de ellos tras la migración.

Se conservan programación, inicio y resultado en el historial de maquinaria. Las operaciones usan transacciones, releen estados y bloquean en el orden ubicación, equipo y orden; se impiden dobles inicios y finalizaciones. La BD impide dos intervenciones en curso de una misma máquina y fechas finales anteriores al inicio.

## Verificación

104 pruebas aprobadas en una base SQLite temporal: flujo satisfactorio, no apto y seguimiento, conservación de horas, doble envío, intervenciones simultáneas, fechas futuras/exigibles, ubicación inactiva, arriendo abierto, permisos, CSRF, filtros, formularios y rollback cuando falla el historial, junto con los bloques anteriores.

No se aplicó la migración ni se probaron los bloqueos concurrentes en PostgreSQL desde el agente; el usuario debe aplicar la migración con su contraseña local.
