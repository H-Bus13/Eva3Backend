# Modelos de solicitud de arriendo iniciada por contratista

Migración 0013: precio_diario/moneda de maquinaria, SolicitudArriendo e HistorialSolicitudArriendo.

## Precio

Una tarifa asignada debe ser estrictamente positiva (mínimo decimal 0.01 CLP). Cero y negativos se rechazan mediante validador del modelo y restricción SQL. La tarifa antigua se conserva como NULL hasta que el personal la complete; NULL significa pendiente, nunca gratuito. Una nueva solicitud exige precio_diario_acordado positivo y la validación del modelo rechaza equipos sin tarifa.

La solicitud conserva el precio acordado y la versión de términos, con firma privada, obra, empresa y solicitante. Un cambio posterior en el catálogo no altera la fotografía de la solicitud. No se modifican tarifas de arriendos históricos.

## Reserva y estados

Estados: pendiente, aprobada, rechazada, cancelada, vencida y entregada. La BD permite una única reserva aprobada por máquina y una solicitud activa por persona/máquina. Aprobación exige autor, fecha y vencimiento de reserva; rechazo/cancelación exigen sus antecedentes; entregada exige arriendo vinculado. El historial admite eventos automáticos sin responsable humano.

Los modelos por sí solos no ejecutan transiciones ni tareas por el paso del tiempo. Los servicios deberán comprobar aprobación del contratista, bloqueos, disponibilidad, obra, condiciones vigentes, copiar el precio del servidor y bloquear las filas antes de cambiar estados. Las relaciones entre tablas se validan con full_clean, además de las restricciones SQL locales.

## Aplicar localmente

Desde la misma terminal con la contraseña PostgreSQL cargada:

```powershell
.\configurar_postgresql.ps1
```

El script aplica las migraciones pendientes. No se ejecutó contra PostgreSQL desde el agente.

## Alcance de esta etapa

Se incorporan los modelos aprobados y su migración. Todavía no se conectan al catálogo/formularios, endpoints ni revisión/entrega existentes. El flujo anterior sigue funcionando hasta implementar esos cambios; no debe presentarse esta migración como el flujo nuevo terminado. Las reservas nuevas tampoco son consideradas aún por las operaciones del flujo antiguo.

## Integración del precio en maquinaria

El catálogo y detalle muestran la tarifa diaria CLP; equipos sin tarifa muestran Precio pendiente de definir. Registrar y guardar una edición desde templates requiere precio positivo. La API requiere precio en altas y lo admite en PATCH, conservando omitidos. El servicio registra altas/cambios en el historial y valida la tarifa. Esta integración no activa todavía la solicitud/revisión iniciada por el contratista.

## Actualización: flujo conectado

La migración 0014 vincula SolicitudEntrega con SolicitudArriendo. El catálogo, Mis solicitudes/Revisar arriendos y la API están conectados a los servicios de solicitud, revisión, cancelación, reserva y entrega. Ver SOLICITUDES_ARRIENDO.md. Las notas previas de este documento describen la etapa inicial de modelos.
