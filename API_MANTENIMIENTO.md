# API de mantenimiento

Amplía `/api/v1/` con el recurso `mantenimientos`. Usa los servicios existentes de los templates; no cambia modelos ni requiere nuevas migraciones.

## Rutas y permisos

| Método | Ruta | Permiso maquinaria |
| --- | --- | --- |
| GET | /api/v1/mantenimientos/ | view_mantenimiento |
| GET | /api/v1/mantenimientos/{id}/ | view_mantenimiento |
| POST | /api/v1/mantenimientos/ | add_mantenimiento |
| POST | /api/v1/mantenimientos/{id}/iniciar/ | iniciar_mantenimiento |
| POST | /api/v1/mantenimientos/{id}/finalizar/ | finalizar_mantenimiento |

Se exige cuenta habilitada y sesión del login habitual. Todas las escrituras mantienen la protección CSRF: enviar cookie de sesión y encabezado `X-CSRFToken` obtenido de un formulario del sitio. Los permisos son independientes, igual que en los templates. Un contratista sin permisos de mantenimiento no accede a estas órdenes. No hay PUT, PATCH ni DELETE.

## Cuerpos JSON

Programar (201): sustituye el ID y la fecha por los que correspondan.

```json
{
  "maquinaria": 1,
  "fecha_programada": "2026-12-01",
  "descripcion": "Cambio de aceite y revisión de componentes"
}
```

Iniciar (200):

```json
{"confirmar": true}
```

Finalizar (200):

```json
{
  "resultado": "Cambio realizado y funcionamiento revisado",
  "apta_para_servicio": true,
  "confirmar": true
}
```

`false` en apta_para_servicio registra un resultado no satisfactorio. No usar los valores si/no de los formularios HTML: en JSON se envían booleanos. No se aceptan campos adicionales como horas, autores, estado o fechas de inicio/cierre. Descripción y resultado no pueden estar vacíos y aceptan hasta 3000 caracteres.

Las respuestas incluyen ID, máquina y nombre, fecha programada, descripción, estado, vencida, fechas de inicio/cierre, lectura_uso, resultado, aptitud y autores. lectura_uso conserva la representación de duración de DRF; es la lectura histórica del contador al cerrar la orden, no horas que pueda modificar el cliente.

## Consultas

Listados paginados de 20 registros con count, next, previous y results. Filtros opcionales:

- estado=pendiente|curso|finalizada
- maquinaria=ID
- page=1
- format=json (también se admite sufijo .json)

Ejemplo: `/api/v1/mantenimientos/?estado=curso&maquinaria=1`. Parámetros desconocidos o inválidos generan 400; una página fuera del listado devuelve 404.

## Reglas conservadas

- Programar para el futuro no detiene ni reserva la maquinaria, y puede hacerse durante un arriendo. Programar para hoy o antes requiere que no haya arriendos/sesiones abiertos y deja revisión pendiente.
- Iniciar exige un equipo sin arriendos ni sesiones abiertos, ubicación habilitada y sin otra intervención en curso. La maquinaria dada de baja debe reactivarse antes.
- Solo se finaliza una orden iniciada, una vez. No se reescribe su resultado.
- Un resultado apto actualiza la referencia del último mantenimiento sin reiniciar las horas totales. Otras órdenes exigibles mantienen el equipo en mantenimiento.
- Un resultado no apto conserva la referencia anterior, deja revisión pendiente y crea seguimiento si no existe otra orden exigible.
- Cada operación registra autor e historial de maquinaria mediante los servicios existentes.

Errores JSON comunes: 400 datos/reglas inválidos; 403 sesión, cuenta, CSRF o permisos; 404 registro no encontrado; 405 método no disponible; 409 conflicto de integridad; 415 cuerpo no admitido.

## Pruebas

Ejecutar desde una terminal con la conexión configurada:

```powershell
.\env\Scripts\python.exe manage.py test maquinaria
```

Django crea una base separada de pruebas; la cuenta necesita permiso para crearla. La comprobación del agente utiliza SQLite temporal, sin modificar buildcorp ni probar los bloqueos de filas de PostgreSQL.

Verificación del bloque: 237 pruebas aprobadas en SQLite temporal, incluidas 15 nuevas de endpoints de mantenimiento. Se cubren flujo satisfactorio/no apto, seguimiento, otras revisiones exigibles, permisos independientes, acceso bloqueado, validación estricta, arriendos abiertos, duplicados, filtros, formatos, errores y CSRF real.

Actualización: empresas/bloqueos REST implementados; ver API_EMPRESAS.md. Pendientes REST: usuarios/permisos, solicitudes de contratistas y perfil/condiciones.
