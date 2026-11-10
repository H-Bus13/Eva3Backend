# Entrega y devolución de arriendos

## Activar

Desde la terminal del proyecto:

```powershell
.\configurar_postgresql.ps1
```

La migración 0009 incorpora solicitudes de entrega y recepción, bodega de origen/recepción, fecha de recepción física, permiso gestionar_arriendos y eventos del inventario. Los arriendos anteriores mantienen sus datos; las ubicaciones y fechas que no se conocían no se inventan.

## Preparar y firmar una entrega

1. El contratista debe tener cuenta aprobada, empresa asociada y condiciones vigentes aceptadas y firmadas desde Mi perfil.
2. El superusuario o personal con gestionar_arriendos abre Arriendos y Preparar entrega.
3. Selecciona máquina, empresa, responsable, obra activa, plazo, tarifa diaria y observaciones.
4. La solicitud no reserva el equipo y vence en una hora. La firma debe realizarla el responsable desde su propia cuenta, ingresando en Arriendos.
5. El responsable revisa equipo, empresa, dirección/comuna de uso, plazo, tarifa, observaciones y versión de condiciones. Marca la confirmación y dibuja una firma nueva.
6. Al confirmar se vuelven a comprobar todos los requisitos, se crea el arriendo, se conserva la firma y la máquina pasa a En uso. Se guarda el movimiento y la bodega de origen.

No se permite entregar con empresa bloqueada, usuario sin aprobación o ajeno a la empresa, ubicación inactiva, condiciones sin firmar, equipo ya arrendado/en uso o requisitos de mantención pendientes. Si cambian las condiciones después de preparar, el personal debe cancelar y crear otra solicitud con la nueva versión. Dos solicitudes para distintos responsables pueden coexistir, pero al confirmar gana la primera entrega válida de la máquina.

El personal puede ver los antecedentes, pero no puede sustituir la firma del responsable. La firma del perfil tampoco se copia como firma de entrega.

## Recepción física y firma de devolución

1. Desde el detalle del arriendo, el personal abre Registrar recepción física.
2. Elige una bodega habilitada, describe el estado recibido, indica daños/necesidad de revisión y confirma que el equipo ya está físicamente allí.
3. Se registra la recepción y ubicación, se cierran las sesiones de trabajo abiertas y se suma su duración una sola vez. El equipo permanece En uso e indisponible mientras falta la firma; no significa que el contador continúe trabajando.
4. El responsable ingresa en Arriendos, abre la recepción, revisa sus observaciones y firma.
5. Se cierra el arriendo con la fecha del servidor. La recepción física tiene su propia fecha, separada del cierre documental.
6. El equipo queda Disponible si no tiene daños ni requisitos pendientes. Si los tiene, pasa a Mantenimiento y se asegura una revisión exigible pendiente.

La devolución de un arriendo existente no exige aceptar condiciones posteriores a su entrega ni que la empresa siga habilitada para nuevos arriendos. Siempre debe poder devolverse el equipo.

Las observaciones preparadas no se editan. Para corregirlas, el personal cancela con motivo y prepara otra recepción. Una solicitud vencida se conserva y se marca como reemplazada al preparar una nueva. Cancelar o vencer una recepción nunca deshace la recepción física, reabre sesiones ni permite trabajar con la máquina. Se conserva el primer instante de recepción y los antecedentes cancelados.

## Acceso, archivos y trazabilidad

- Usuarios normales: solo sus arriendos y solicitudes como responsables, incluso si comparten empresa.
- Personal con gestionar_arriendos: consulta y preparación/cancelación de operaciones.
- Solo el responsable seleccionado puede confirmar mediante firma.
- Las firmas se sirven por vistas autenticadas y no se publican por /media/. Las respuestas privadas no se almacenan en caché.
- Los PNG nuevos se eliminan si falla la transacción de confirmación.
- Disponibilidad, arriendo, sesión, solicitud y movimientos se coordinan con bloqueos y transacciones. El orden incluye obras, bodegas, máquina, arriendo y solicitud; los registros del contratista/empresa y condiciones se bloquean antes de una entrega.
- La recepción devuelve el equipo a una bodega real habilitada y conserva la bodega de salida como referencia histórica.

## Qué sigue pendiente

El contador ya se incorporó al detalle del arriendo; ver CONTADOR_USO.md. Rechaza nuevas sesiones cuando recibido_en tiene valor, aun cuando el cierre firmado esté pendiente. Los cobros automáticos, alertas y bloqueos por atraso siguen pendientes. En uso identifica un arriendo abierto, no necesariamente una sesión de trabajo en marcha.

## Verificación

123 pruebas aprobadas en SQLite temporal: flujo firmado, privacidad, permisos, firma en blanco, condiciones reemplazadas, empresa bloqueada entre preparación y entrega, solicitudes vencidas/canceladas, competencia por disponibilidad, devolución sana/con revisión, cierre único de sesiones, corrección de recepción, archivos y rollback; se incluyen los módulos anteriores.

No se aplicó la migración ni se ejecutaron pruebas concurrentes contra PostgreSQL desde el agente. Se aplica localmente con la contraseña del usuario.

