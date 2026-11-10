# Solicitudes de arriendo iniciadas por el contratista

## Usar desde las pantallas

1. Aplicar migraciones desde la terminal con conexión PostgreSQL: .\configurar_postgresql.ps1. Este bloque agrega la migración 0014; 0013 contiene los modelos y tarifas.
2. Registrar/asignar un precio diario positivo a la maquinaria; debe estar disponible, sin revisión pendiente y en ubicación activa.
3. El contratista aprobado, habilitado y asociado a empresa no bloqueada ingresa. Desde Mi perfil acepta y firma las condiciones vigentes si todavía no lo hizo.
4. En Maquinaria elige Solicitar arriendo. Indica dirección de uso y comuna, fecha/hora futura de devolución y observaciones; revisa tarifa y condiciones, acepta y firma esta solicitud concreta.
5. En Mis solicitudes consulta estado, historial y firma privada. Mientras esté pendiente o aprobada vigente, puede cancelar con motivo.
6. El personal con gestionar_arriendos usa Revisar arriendos para aprobar o rechazar con motivo. Aprobar reserva una hora, limitada además por la fecha de devolución. No cambia la máquina a En uso ni inicia horas.
7. Desde la solicitud aprobada, el personal prepara la entrega física. El responsable ingresa a Arriendos, abre la entrega pendiente y firma nuevamente. Solo entonces se crea Arriendo, la solicitud pasa a Entregada y el equipo a En uso.
8. Iniciar/pausar trabajo y recibir/devolver mantienen los mecanismos existentes. Entregar no inicia automáticamente el timer.

La firma de solicitud y la de entrega corresponden a momentos distintos. No se implementa un calendario de reservas para intervalos futuros: las solicitudes son para entrega próxima. No se calculan cobros finales ni multas.

## Reglas y privacidad

- Identidad/empresa se toman de la sesión. El precio se copia del catálogo; precio_visto sirve solo para detectar que cambió mientras se firmaba, nunca para fijar la tarifa.
- Precio diario estrictamente positivo. Los arriendos históricos no se reescriben.
- La solicitud conserva su precio firmado aunque cambie el catálogo. Se conservan versión de condiciones, firma y fechas del servidor.
- Se revalidan bloqueos, aprobación/suspensión, disponibilidad y condiciones al aprobar, preparar y confirmar entrega. Si cambian las condiciones se requiere una nueva petición firmada.
- Pendiente no reserva. Solo una aprobación vigente por máquina. Una persona no duplica solicitudes activas para el mismo equipo.
- Traslados, baja, intervenciones de mantenimiento y entregas ajenas no pueden usar una máquina reservada. Programar un mantenimiento futuro sigue permitido; intervenir exige que no haya reserva.
- Cancelar libera la reserva e impide confirmar un comprobante de entrega preparado previamente.
- El comprobante de entrega no vence después de la reserva. Prepararlo repetidamente devuelve el mismo comprobante vigente. Un comprobante cancelado no se sobrescribe: cancelar la petición y crear otra.
- El contratista solo ve sus solicitudes, incluso dentro de la misma empresa. Gestionar_arriendos habilita revisión y consulta global; no habilita suplantar la firma del responsable.
- Las firmas no se exponen por /media/. Se entregan por vistas autenticadas con no-store.

## Vencimiento

Comando: python manage.py vencer_reservas. Marca reservas aprobadas vencidas y registra un evento automático, sin duplicarlo.

Los intentos de solicitar/aprobar/preparar/confirmar revisan vencimientos antes de su transacción principal; un intento fallido no deshace esa liberación. Las consultas GET muestran estado_actual=VENCIDA si expiró, aunque el comando no haya persistido aún el cambio. El campo estado conserva el valor guardado hasta la transición.

La plantilla deploy/buildcorp-atrasos.service ejecuta ahora revisar_atrasos y vencer_reservas. Su timer de cinco minutos todavía debe instalarse en EC2. No se instaló una tarea en el equipo local desde el agente. La disponibilidad usa el vencimiento real, sin esperar al timer.

## API

Recurso /api/v1/solicitudes-arriendo/. Sesión y CSRF igual que los otros módulos.

| Método | Ruta después del recurso | Función |
| --- | --- | --- |
| GET | (raíz) | Listado privado y paginado |
| GET | {id}/ | Detalle y condiciones firmadas |
| POST | enviar/ | Solicitar con PNG multipart |
| POST | {id}/aprobar/ | Aprobar con motivo JSON |
| POST | {id}/rechazar/ | Rechazar con motivo JSON |
| POST | {id}/cancelar/ | Cancelar con motivo JSON |
| POST | {id}/entregar/ | Preparar comprobante de entrega |
| GET | {id}/historial/ | Historial paginado |
| GET | {id}/firma/ | PNG privado |

Enviar: multipart con maquinaria, direccion_uso, comuna_uso, indicaciones_acceso opcional, devolucion_prevista (ISO con zona horaria), observaciones opcionales, version_id, precio_visto, acepto=true, confirmar=true y archivo firma. Se valida el PNG y se regenera sin metadatos. La firma es un trazo electrónico, no una firma certificada.

Aprobar/rechazar/cancelar: {"motivo": "Razón de la operación"}. Entregar: {"confirmar": true}. Devuelve el ID de SolicitudEntrega; el responsable la confirma por /api/v1/entregas/{id}/confirmar/ mediante multipart con firma nueva y confirmar=true.

Filtros: estado=PENDIENTE|APROBADA|RECHAZADA|CANCELADA|VENCIDA|ENTREGADA, maquinaria=ID, page. VENCIDA incluye expiradas todavía no sincronizadas; APROBADA solo reservas vigentes. Se rechazan campos desconocidos y no hay PUT/PATCH/DELETE.

Creación: 201; consulta/revisión/cancelación: 200; validación: 400; permisos/CSRF: 403; registros ajenos: 404; conflictos de integridad: 409; parser no admitido: 415. Firmas correctas devuelven image/png y errores JSON.

La entrada manual anterior de entrega se conserva por compatibilidad para personal autorizado y equipos sin reserva; ya no es el acceso principal de la pantalla Arriendos. No admite tarifa cero en altas nuevas y no puede invadir una reserva. Comprobantes y contratos anteriores siguen consultables.

## Pruebas

Suite SQLite temporal del agente y casos nuevos de flujo completo, privacidad, permisos, firma/condiciones/precio, reservas, cancelación, vencimiento, operaciones ajenas, HTML y CSRF. No verifica concurrencia/bloqueos de filas de PostgreSQL; ejecutar probar_postgresql.ps1 localmente para ese entorno. El agente no aplicó migraciones a buildcorp.

Verificación final: 306 pruebas aprobadas en SQLite temporal, incluidas 21 de este flujo. Sin migraciones adicionales pendientes de generar; 0014 debe aplicarse localmente a PostgreSQL.


Actualización: el destino nuevo es una dirección/comuna propia, sin catálogo de obras. La migración 0015 conserva los antecedentes existentes; consultar DESTINOS_ARRIENDO.md.
