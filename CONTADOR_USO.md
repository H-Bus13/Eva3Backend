# Contador de uso de maquinaria

## Activar

Desde la terminal del proyecto:

```powershell
.\configurar_postgresql.ps1
```

La migración 0010 agrega iniciada_por, cerrada_por y motivo_cierre a SesionUso y un evento de alerta por intervalo cumplido. Las sesiones anteriores conservan sus fechas y no se inventan autores ni motivos.

## Uso

Ingresar como responsable del arriendo, abrir Arriendos y seleccionar un arriendo abierto. Su detalle muestra Horas de trabajo, botones Iniciar trabajo y Pausar trabajo e historial de sesiones.

- Solo el responsable inicia el trabajo.
- El responsable o personal con gestionar_arriendos puede detenerlo.
- Cada pausa guarda la duración una sola vez; luego puede iniciarse otra sesión si no hay revisiones exigibles.
- Cerrar la página no detiene el trabajo. Las fechas y las horas se calculan en el servidor.
- El contador muestra sesión actual, trabajo total del arriendo y horas totales de la máquina. La visualización avanza cada segundo y se sincroniza con el servidor cada 15 segundos y al volver a la pestaña.
- Si se pierde conexión, se advierte que no se puede confirmar el tiempo y se conserva la última estimación visible. El trabajo no se detiene por esa pérdida. Se puede intentar la pausa mediante el formulario normal; la conexión debe recuperarse para que llegue al servidor.
- Los botones funcionan sin JavaScript, con actualización de las cifras al recargar.

Se mide el intervalo entre iniciar y pausar, no las horas del motor por telemetría. En uso significa que hay un arriendo abierto; no implica que siempre haya una sesión de trabajo activa.

## Intervalo de mantención

Se comparan las horas totales, incluyendo la sesión abierta, con la referencia de la última mantención satisfactoria.

Al cumplirse el intervalo, la sincronización, la pausa o la recepción aseguran una revisión exigible pendiente y muestran la alerta. No se detiene automáticamente una sesión en curso. La máquina conserva En uso mientras siga arrendada; una vez pausada, ya no permite iniciar otra sesión sin resolver la revisión. La devolución firmada la pasa a Mantenimiento cuando corresponde.

La consulta del contador usa POST con CSRF para que pueda registrar una revisión preventiva de forma segura. Sin ninguna petición al servidor, la detección persistida ocurre al siguiente acceso, sincronización, pausa o recepción; los cálculos de disponibilidad igualmente consideran las horas actuales.

Una empresa bloqueada para nuevos arriendos no pierde por ese solo motivo la posibilidad de usar un arriendo existente. Las revisiones exigibles de la máquina sí impiden nuevos inicios.

## Recepción física

La recepción existente ahora registra quién cerró las sesiones y el motivo Recepción física del equipo. Suma las duraciones abiertas una sola vez, impide reinicios y asegura la revisión por horas si se alcanzó el intervalo. La firma de devolución posterior no vuelve a sumar el tiempo.

Cancelar o reemplazar la solicitud de recepción no reabre sesiones ni deshace la recepción física. La fecha de recepción es independiente del cierre documental del arriendo.

## Seguridad y verificación

Los servicios usan el orden de bloqueo de ubicaciones, máquina, arriendo y sesión. La BD conserva su restricción de una sesión abierta por arriendo. El servidor controla permisos, estados, mantenciones y fechas; los valores enviados desde el navegador no determinan la duración guardada.

138 pruebas aprobadas en SQLite temporal, incluyendo inicio y pausa, dobles envíos, uso de un arriendo existente de empresa bloqueada, recepción, intervalo de 250 horas, conservación de revisiones al rechazar un inicio, privacidad, CSRF, fechas inválidas y rollback. JavaScript revisado sin errores de sintaxis. No se aplicó la migración ni se probaron bloqueos concurrentes contra PostgreSQL desde el agente.
