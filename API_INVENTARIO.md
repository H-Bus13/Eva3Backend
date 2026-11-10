# API REST de inventario

## Alcance implementado

Django REST Framework 3.18.3, instalado en el entorno y fijado en requirements.txt. Este primer bloque cubre maquinaria, obras y bodegas. Los endpoints REST de arriendos, firmas, contador, mantenciones, usuarios y empresas todavía deben incorporarse; sus flujos de templates permanecen disponibles.

La API reutiliza los servicios del proyecto y conserva sus permisos, transacciones, revisiones e historial. Django Admin sigue deshabilitado. No se agregaron modelos ni migraciones en este bloque.

## Acceso

Ingresar mediante el login propio y usar la API en el mismo navegador y dominio. Por ejemplo, después de ingresar en http://127.0.0.1:8000/ingresar/, abrir http://127.0.0.1:8000/api/v1/.

La autenticación usa la sesión de Django. Las escrituras requieren el cookie de sesión y un token CSRF válido enviado en X-CSRFToken. No se desactiva CSRF para Postman u otros clientes. Los formularios existentes permiten obtener el cookie CSRF; en un cliente HTTP debe completarse el inicio de sesión normal, conservando sus cookies y enviando el token.

Solo JSON: para escribir usar Content-Type: application/json. No hay autenticación por JWT o token en este bloque ni interfaz administrativa generada por DRF. Las cuentas pendientes, rechazadas, suspendidas o inactivas no tienen acceso normal; la identificación limitada para consultar solicitudes no autentica la API.

## Rutas

Prefijo: /api/v1/. Las rutas de detalle terminan en /.

| Método | Ruta | Función |
|---|---|---|
| GET | /api/v1/ | Índice de recursos |
| GET, POST | /api/v1/maquinaria/ | Listar o crear |
| GET, PATCH | /api/v1/maquinaria/ID/ | Consultar o editar nombre/marca/modelo |
| POST | /api/v1/maquinaria/ID/trasladar/ | Trasladar con motivo |
| POST | /api/v1/maquinaria/ID/baja/ | Dar de baja con motivo |
| POST | /api/v1/maquinaria/ID/reactivar/ | Reactivar para revisión |
| GET | /api/v1/maquinaria/ID/historial/ | Movimientos paginados |
| GET, POST | /api/v1/obras/ | Listar o crear obras |
| GET, PATCH | /api/v1/obras/ID/ | Consultar o editar nombre/dirección |
| GET, POST | /api/v1/bodegas/ | Listar o crear bodegas |
| GET, PATCH | /api/v1/bodegas/ID/ | Consultar o editar nombre/dirección |
| POST | /api/v1/obras/ID/desactivar/ | Desactivar con motivo |
| POST | /api/v1/obras/ID/reactivar/ | Reactivar con motivo |
| GET | /api/v1/obras/ID/historial/ | Historial paginado |
| POST | /api/v1/bodegas/ID/desactivar/ | Desactivar con motivo |
| POST | /api/v1/bodegas/ID/reactivar/ | Reactivar con motivo |
| GET | /api/v1/bodegas/ID/historial/ | Historial paginado |

No se implementan DELETE ni PUT: devuelven 405 para cuentas autenticadas habilitadas. Las desactivaciones y bajas conservan registros; los estados y horas no se editan libremente.

## Ejemplos de cuerpos JSON

Los IDs son ilustrativos; se deben usar los devueltos por los listados de tu base.

Crear una bodega de empresa, POST /api/v1/bodegas/:

```json
{"nombre": "Bodega Central", "direccion": "Avenida Central 100", "obra": null}
```

Crear maquinaria, POST /api/v1/maquinaria/:

```json
{
  "codigo": "GEN-002",
  "nombre": "Generador eléctrico",
  "marca": "Ejemplo",
  "modelo": "G5000",
  "bodega": 1,
  "horas_iniciales": "100.00",
  "horas_ultima_mantencion": "0.00"
}
```

Si la última mantención se omite o es null, se programa revisión inicial y el equipo queda en Mantenimiento. También se revisa si se cumplieron 250 horas desde esa lectura.

Editar solo nombre, PATCH /api/v1/maquinaria/ID/:

```json
{"nombre": "Generador de obra"}
```

Los demás campos se conservan desde el registro bloqueado en el servicio, sin combinar con una lectura anterior al bloqueo.

Trasladar, POST /api/v1/maquinaria/ID/trasladar/:

```json
{"destino": 2, "motivo": "Reubicación en bodega de obra"}
```

Baja, reactivación y desactivación de ubicaciones:

```json
{"motivo": "Motivo de la operación"}
```

La reactivación de maquinaria conserva las horas y deja el equipo en Mantenimiento con revisión. Reactivar equipos/ubicaciones requiere administrador o superusuario además del permiso correspondiente.

## Filtros y paginación

Maquinaria: q (código/nombre), estado (DISPONIBLE, EN_USO, MANTENIMIENTO, BAJA), bodega (ID).

Obras y bodegas: q (nombre/dirección), estado (activas, inactivas, todas). Por defecto se listan activas, pero las inactivas siguen siendo consultables por ID y mediante historial. Bodegas permite además obra (ID).

Paginación de 20 registros: page=1, page=2. Respuesta con count, next, previous y results. Parámetros desconocidos, IDs de filtro inválidos o números de página no válidos generan errores JSON. Las rutas admiten sufijo .json o format=json.

## Errores y permisos

- 200: consulta o modificación correcta.
- 201: recurso creado.
- 400: datos o reglas del caso inválidos; errores por campo o non_field_errors.
- 403: falta sesión válida, CSRF o permiso. Con SessionAuthentication no se redirige a una página de login desde la API.
- 404: recurso no encontrado.
- 405: método no disponible.
- 406: formato de respuesta no admitido, por ejemplo HTML.
- 409: conflicto de integridad, sin revelar SQL.
- 415: tipo de cuerpo no admitido.

Cada escritura exige el mismo permiso que la pantalla correspondiente. Consultar requiere cuenta habilitada. Campos desconocidos/protegidos en cuerpos de escritura se rechazan explícitamente: no se aceptan estado, horas acumuladas, privilegios o cambios de obra en una bodega ya registrada.

## Verificación

202 pruebas aprobadas en SQLite temporal: 175 anteriores y 27 de API. Se comprobaron JSON, sesiones, CSRF real, permisos, campos prohibidos, PATCH parcial, ubicaciones opcionales/inactivas, paginación, filtros, historial, bajas/reactivaciones, errores, formatos y conservación de templates.

Para ejecutar las pruebas de endpoints en PostgreSQL, desde la terminal donde ya esté configurada tu conexión:

```powershell
.\env\Scripts\python.exe manage.py test maquinaria.test_api
```

Django creará una base de pruebas separada (normalmente test_buildcorp); la cuenta de conexión necesita permiso para crear esa base. No se ejecutaron pruebas contra PostgreSQL desde el agente porque no dispone de tu contraseña local.

## Ampliación: arriendos

La API también incorpora arriendos, entregas, devoluciones, firmas privadas y control de horas. Consulta API_ARRIENDOS.md para las rutas, cuerpos y permisos. El total de verificación actualizado es de 222 pruebas; las 202 indicadas arriba corresponden al primer bloque.

## Precio diario de maquinaria

El alta por POST /api/v1/maquinaria/ requiere precio_diario como decimal estrictamente positivo, por ejemplo "25000.00". La lectura devuelve precio_diario y moneda="CLP". PATCH permite actualizar la tarifa; omitirla conserva el valor actual, enviarla vacía/null/cero/negativa es inválido. Equipos antiguos pendientes de completar pueden devolver precio_diario=null. No se modifican precios acordados de solicitudes o contratos existentes.
