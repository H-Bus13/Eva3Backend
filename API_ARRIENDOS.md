# API de arriendos, entregas, devoluciones y uso

Este bloque amplía `/api/v1/`. Reutiliza los servicios de los templates; no crea tablas ni migraciones. La raíz ahora enlaza maquinaria, obras, bodegas, arriendos, entregas y devoluciones.

## Sesión y permisos

Inicia sesión desde el login habitual. Las escrituras requieren cookie de sesión y encabezado `X-CSRFToken` con el token obtenido de un formulario del sitio. No se deshabilita CSRF. Solo acceden cuentas habilitadas.

El personal con `maquinaria.gestionar_arriendos` prepara/cancela solicitudes y registra recepciones. El responsable contratista confirma personalmente con firma y puede iniciar su timer; personal autorizado también puede pausarlo. Cada contratista solo consulta sus propios arriendos y solicitudes, aunque comparta empresa con otro usuario. El personal autorizado consulta todos. Un recurso ajeno devuelve 404; el personal no puede firmar en nombre del responsable.

## Rutas

Todas terminan en `/`. Las escrituras usan POST; no hay PUT, PATCH ni DELETE para estos recursos.

| Método | Ruta después de /api/v1/ | Función |
| --- | --- | --- |
| GET | arriendos/ | Listar arriendos visibles |
| GET | arriendos/{id}/ | Consultar detalle y condiciones aceptadas |
| GET | entregas/ | Listar solicitudes de entrega |
| POST | entregas/ | Preparar entrega, sin reservar equipo |
| GET | entregas/{id}/ | Consultar solicitud y condiciones |
| POST | entregas/{id}/confirmar/ | Responsable firma y crea el arriendo |
| POST | entregas/{id}/cancelar/ | Cancelar solicitud con motivo |
| POST | arriendos/{id}/recibir/ | Registrar recepción física y preparar firma de devolución |
| GET | devoluciones/ | Listar solicitudes de devolución |
| GET | devoluciones/{id}/ | Consultar comprobante de recepción |
| POST | devoluciones/{id}/confirmar/ | Responsable firma y cierra arriendo |
| POST | devoluciones/{id}/cancelar/ | Cancelar solicitud sin revertir recepción física |
| GET | arriendos/{id}/sesiones/ | Historial paginado de uso |
| POST | arriendos/{id}/uso/iniciar/ | Iniciar trabajo |
| POST | arriendos/{id}/uso/pausar/ | Cerrar sesión y acumular duración una vez |
| POST | arriendos/{id}/uso/sincronizar/ | Consultar timer y detectar umbral de mantenimiento |
| GET | arriendos/{id}/firmas/entrega/ | Leer PNG privado de entrega |
| GET | arriendos/{id}/firmas/devolucion/ | Leer PNG privado de devolución |

## Cuerpos de ejemplo

Preparar entrega: JSON con IDs reales de tu base. La fecha debe ser futura; responsable aprobado, de esa empresa y con aceptación/firma de las condiciones vigentes en el perfil. No se definen multas ni cálculos de cobros.

```json
{
  "maquinaria": 1,
  "empresa": 1,
  "responsable": 2,
  "direccion_uso": "Calle Destino 123",
  "comuna_uso": "Santiago",
  "indicaciones_acceso": "Acceso por el portón principal",
  "devolucion_prevista": "2026-12-01T18:00:00-03:00",
  "tarifa_diaria": "0.00",
  "observaciones": "Equipo y accesorios revisados"
}
```

Confirmar entrega/devolución: `multipart/form-data`, campos `confirmar=true` y `firma` como archivo PNG dibujado. No enviar JSON ni base64. Se valida formato, dimensiones, tamaño y presencia de trazo, y se regenera el PNG sin metadatos. Esta firma electrónica dibujada no constituye una firma certificada ni verifica por sí sola la identidad.

Registrar recepción: JSON, `confirmar=true` indica que el equipo ya se recibió físicamente.

```json
{
  "bodega": 1,
  "observaciones": "Recibido y revisado",
  "requiere_revision": false,
  "confirmar": true
}
```

Cancelar: `{"motivo": "Corregir datos antes de volver a preparar"}`. Iniciar/pausar/sincronizar: `{}`; no se aceptan horas ni fechas del navegador.

## Respuestas, filtros y reglas

Preparación, confirmación de entrega y recepción correcta: 201. Consultas, cancelaciones, firma de devolución y timer: 200. Errores siguen el formato JSON del bloque de inventario (400, 403, 404, 405, 406, 409, 415). Las firmas correctas devuelven `image/png` incluso sin encabezado Accept; sus errores devuelven JSON y las respuestas no se almacenan en caché. Se admite `Accept: image/png` para descargar la firma. No se exponen rutas del almacenamiento.

Listados y sesiones paginan 20 registros con `page`. Arriendos filtra por `estado=abierto|firma|cerrado` y `maquinaria=ID`; abierto incluye recibido pendiente de firma. Solicitudes filtran por `estado=pendiente|confirmada|cancelada|vencida`. Se rechazan parámetros desconocidos.

Las solicitudes vencen después de una hora. Una entrega se vuelve a validar al firmar: disponibilidad, bloqueos, responsable y versión de condiciones. Repetir una firma confirmada se rechaza, sin crear otro arriendo.

La recepción física cierra las sesiones activas, detiene el atraso y traslada el equipo a la bodega; el arriendo permanece pendiente hasta la firma. Cancelar/vencer el comprobante no revierte la recepción. Una empresa bloqueada puede devolver. El equipo queda disponible o en mantenimiento según su revisión pendiente.

El servidor calcula las horas. Sincronizar al alcanzar 250 horas desde mantenimiento genera revisión sin cortar el trabajo activo. Pausar o recibir suma cada sesión una sola vez. Tras la recepción no se puede reiniciar el trabajo.

## Verificación

222 pruebas aprobadas en SQLite temporal, incluidas 20 de este bloque: flujo completo, privacidad entre contratistas, permisos, CSRF real, firmas válidas e inválidas, solicitudes repetidas/vencidas, condiciones cambiadas, empresa bloqueada, timers, umbral de 250 horas y recepción irreversible. No se verificó PostgreSQL desde el agente; no dispone de la contraseña local. Las pruebas SQLite no verifican bloqueos de filas de PostgreSQL.

Para probar localmente con la conexión ya configurada:

```powershell
.\env\Scripts\python.exe manage.py test maquinaria.test_api maquinaria.test_api_arriendos
```

Django crea una base de pruebas separada; la cuenta necesita permiso para crearla. No son necesarias nuevas migraciones para este bloque.

Pendientes REST: mantenimiento, administración de usuarios/permisos y empresas/bloqueos. Los templates existentes continúan disponibles.

Actualización: mantenimiento REST implementado; ver API_MANTENIMIENTO.md. Pendientes REST actuales: usuarios/permisos y empresas/bloqueos.


Actualización de destino (migración 0015): las entradas nuevas ya no aceptan obra_destino. Usan direccion_uso y comuna_uso obligatorias, e indicaciones_acceso opcional. La obra antigua se conserva solo en las respuestas de registros históricos. Ver DESTINOS_ARRIENDO.md.
