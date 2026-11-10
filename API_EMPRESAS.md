# API de empresas y bloqueos

Recurso `/api/v1/empresas/`. No crea ni edita empresas; administra sus bloqueos y consultas con los servicios existentes. No requiere nuevas migraciones.

## Rutas

| Método | Ruta | Función |
| --- | --- | --- |
| GET | /api/v1/empresas/ | Listado paginado |
| GET | /api/v1/empresas/{id}/ | Datos y bloqueos |
| POST | /api/v1/empresas/{id}/bloquear/ | Aplicar bloqueo manual |
| POST | /api/v1/empresas/{id}/desbloquear/ | Retirar bloqueo manual |
| GET | /api/v1/empresas/{id}/historial/ | Eventos guardados de bloqueo |
| GET | /api/v1/empresas/{id}/atrasos/ | Arriendos atrasados de esa empresa |

Las consultas requieren cuenta habilitada y al menos uno de los permisos maquinaria.gestionar_arriendos o maquinaria.gestionar_bloqueos_empresa. Los detalles de atrasos requieren gestionar_arriendos; bloquear/desbloquear requiere gestionar_bloqueos_empresa. Un contratista sin esos permisos no tiene acceso a este módulo de administración. Sus templates habituales siguen disponibles.

## Escrituras

Inicia sesión mediante el login habitual. Envía JSON, la cookie de sesión y X-CSRFToken obtenido de un formulario del sitio. Bloquear y desbloquear requieren motivo no vacío, hasta 1000 caracteres:

```json
{"motivo": "Cambio autorizado tras revisar los antecedentes"}
```

Respuesta correcta: 200 con empresa actualizada. Se rechazan campos adicionales, repetir el estado manual existente y modificar directamente flags, RUT o razón social. No se admite POST de creación, PUT, PATCH ni DELETE. El historial conserva motivo, fecha, origen y responsable; el desbloqueo limpia el motivo vigente, sin borrar los antecedentes.

## Bloqueo guardado y atraso actual

- bloqueada: bloqueo manual guardado.
- motivo_bloqueo: motivo del bloqueo manual vigente.
- bloqueada_por_atraso: último estado automático guardado por los servicios de revisión.
- bloqueo_por_atraso_actual: existencia de arriendos vencidos sin recepción física ni devolución, calculada al consultar.
- tiene_bloqueo: bloqueo manual o atraso actual, usado también para los filtros.

GET no actualiza flags ni crea eventos. Puede haber una diferencia entre el estado automático guardado y el atraso actual hasta que se ejecute la revisión existente. El historial incluye solo cambios ya registrados. Los servicios de arriendo continúan verificando bloqueos y atrasos al entregar; consultar la API no sustituye esa validación. La revisión periódica de atrasos sigue pendiente de programación en el despliegue.

Desbloquear manualmente no elimina los atrasos ni cambia su flag automático. Una empresa con atraso sigue impedida de iniciar nuevos arriendos. La recepción física termina el atraso aunque la firma de devolución esté pendiente. El bloqueo no impide devolver equipos.

## Filtros y respuestas

Listado: q busca RUT o razón social; estado=todas|bloqueadas|habilitadas; page para paginación de 20 registros. Historial y atrasos admiten page. Se admite format=json y sufijo .json. Respuestas paginadas: count, next, previous, results.

Ejemplo: `/api/v1/empresas/?estado=bloqueadas&q=Constructora`.

Errores JSON: 400 entrada/regla inválida; 403 cuenta, sesión, CSRF o permiso; 404 registro/página inexistente; 405 método no permitido; 409 conflicto de integridad; 415 cuerpo no admitido. Las respuestas llevan indicación de no almacenar en caché.

## Pruebas

```powershell
.\env\Scripts\python.exe manage.py test maquinaria
```

Django crea una base de pruebas separada; se necesita permiso para crearla. El agente verifica con SQLite temporal sin modificar buildcorp; esto no comprueba los bloqueos de filas de PostgreSQL.

Verificación: 249 pruebas aprobadas en SQLite temporal, incluidas 12 nuevas de empresas: cambios manuales e historial, entradas inválidas, repetición, separación de bloqueos, consultas sin escrituras, recepción física, permisos, aislamiento por empresa, filtros, métodos y CSRF real.
