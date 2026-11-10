# BuildCorp

Sistema de arriendo y control de maquinaria desarrollado con Django, Django REST Framework, PostgreSQL y templates Bootstrap. El contratista solicita desde el catálogo; el personal revisa, reserva y entrega. Incluye firmas privadas, contador de trabajo, mantenimiento preventivo y bloqueos por atraso.

**Repositorio remoto:** pendiente de publicar.  
**IP pública/DNS de EC2:** pendiente de despliegue y verificación.

## Requisitos y ejecución local

Usar Python compatible con las versiones fijadas en `requirements.txt` (el entorno local utiliza Python 3.13), PostgreSQL y PowerShell. Crear una base vacía `buildcorp` con el propietario de conexión correspondiente.

```powershell
python -m venv env
.\env\Scripts\python.exe -m pip install -r requirements.txt
.\configurar_postgresql.ps1
.\env\Scripts\python.exe manage.py createsuperuser
.\env\Scripts\python.exe manage.py runserver
```

Si el entorno y el superusuario ya existen, omitir sus pasos de creación. No hay cuentas ni contraseñas de demostración incorporadas. Abrir `http://127.0.0.1:8000/`.

`configurar_postgresql.ps1` solicita la contraseña sin mostrarla y aplica las migraciones pendientes. Ejecutar el servidor en la misma terminal: `PGPASSWORD` no se conserva al abrir otra. El error `fe_sendauth: no password supplied` significa que falta cargar esa contraseña.

Variables de conexión: `PGDATABASE` (por defecto `buildcorp`), `PGUSER` (`postgres` en desarrollo), `PGHOST` (`localhost`), `PGPORT` (`5432`) y `PGPASSWORD`. No escribir contraseñas en el repositorio.

La administración se realiza mediante templates propios. Django Admin está deshabilitado según la aclaración del profesor comunicada por el estudiante.

## Roles y acceso

| Cuenta | Funciones |
| --- | --- |
| Contratista aprobado | Perfil/empresa, aceptar condiciones y firmar, solicitar maquinaria, consultar sus solicitudes/arriendos, confirmar entrega/devolución e iniciar/pausar trabajo |
| Bodeguero | Operaciones de inventario, solicitudes, entregas y mantenimiento según permisos asignados |
| Administrador | Administración interna y permisos funcionales dentro de sus atribuciones |
| Superusuario | Administración completa, incluidas cuentas superiores |

El registro público crea contratistas pendientes e inactivos. El personal autorizado aprueba o rechaza con motivo; una cuenta rechazada puede ingresar a una sesión limitada para consultar la razón y reenviar su solicitud. Esa sesión no habilita la aplicación y vence a los 30 minutos. Después de aprobar debe ingresar nuevamente.

Suspender/reactivar una cuenta es independiente de aprobarla. Los permisos impiden modificar la cuenta propia, gestionar cuentas superiores sin atribuciones o dejar el sistema sin superusuario activo.

Condiciones y firma personal son exclusivas de contratistas habilitados, también por URL/API. El personal autorizado conserva publicación de condiciones y consulta de comprobantes. Los correos se validan por formato; no se envía confirmación de existencia.

## Preparar inventario y arrendar

1. Crear una bodega con su dirección. Las bodegas de empresa no necesitan obra.
2. Registrar maquinaria con código único, precio diario positivo en CLP, ubicación y lecturas de uso. Si se desconoce la última mantención, queda pendiente de revisión. Completar tarifas pendientes de equipos antiguos antes de solicitar.
3. El contratista acepta y firma las condiciones vigentes en **Mi perfil**.
4. En el catálogo elige **Solicitar arriendo**, indica dirección de uso, comuna, devolución futura e indicaciones opcionales. Revisa precio/condiciones y firma la solicitud concreta.
5. El personal usa **Revisar arriendos** para aprobar o rechazar con motivo. Aprobar reserva hasta una hora, limitada por la devolución prevista. Todavía no crea el arriendo ni inicia horas.
6. Desde la petición aprobada prepara la entrega física. El responsable abre el comprobante pendiente en **Arriendos** y firma otra vez. Se crea el arriendo, la petición queda entregada y el equipo pasa a **En uso**.
7. El responsable inicia/pausa el trabajo desde el detalle. El servidor calcula las horas; entregar por sí solo no inicia el contador.
8. El personal registra recepción física en una bodega. Se cierran sesiones, se detiene el atraso y se prepara la firma de devolución. La firma del responsable cierra el arriendo y deja el equipo disponible o en mantenimiento según corresponda.

### Reglas del flujo

- El precio nunca puede ser cero en altas nuevas. Se obtiene del servidor y queda conservado en la solicitud aunque cambie la tarifa del catálogo. No se calculan pagos, multas ni cobros finales.
- El destino nuevo es dirección/comuna propias; no se elige obra. Se conserva en solicitud, entrega y arriendo. Para cambiarlo después de firmar se cancela y presenta una nueva solicitud.
- Las obras antiguas permanecen como antecedentes. La migración 0015 copia su dirección sin inventar comunas ni modificar firmas; los documentos históricos se identifican como tales.
- Pendiente no reserva. Solo una petición aprobada vigente por máquina y una petición activa por persona/equipo. No hay calendario de reservas por intervalos futuros.
- El contratista puede cancelar una petición pendiente o aprobada vigente. El personal usa rechazar mientras está pendiente y cancelar después de aprobar. No se cancela una petición ya entregada: corresponde devolver.
- Reservas vigentes impiden traslados, bajas, intervenciones de mantenimiento y entregas ajenas. Cancelar libera la reserva e invalida la confirmación de una entrega ya preparada.
- Un comprobante de entrega no vence después de la reserva. No se sobrescriben comprobantes cancelados; se cancela la petición y se crea otra.
- La entrada manual de entrega anterior se conserva para personal autorizado y equipos sin reserva, pero no es el acceso principal del flujo nuevo.
- Solo el responsable firma la entrega/devolución. El personal puede detener trabajo, pero no iniciarlo por él. Cerrar el navegador no detiene una sesión activa.
- Las firmas PNG son trazos electrónicos, no firmas certificadas. Se validan y regeneran, y solo se sirven mediante vistas con permisos. El visor permite cerrar con X, fondo o Escape.

## Mantenimiento, estados y bloqueos

Estados de maquinaria: **Disponible**, **En uso**, **Mantenimiento** y **Dada de baja**. Baja y desactivaciones conservan registros e historial. Reactivar maquinaria exige revisión y no borra horas.

Se genera revisión al alcanzar 250 horas desde la referencia de última mantención. La alerta no corta automáticamente una sesión en marcha. El personal puede programar mantenciones por fecha; programar a futuro no equivale a intervenir. Iniciar una intervención exige que el equipo no tenga uso/arriendos ni reserva vigentes.

Finalizar satisfactoriamente actualiza la referencia de mantenimiento, conservando horas totales. Si quedan otras revisiones exigibles sigue en mantenimiento. Un resultado no apto mantiene revisión y genera seguimiento cuando corresponda.

El bloqueo manual de empresa y el automático por atraso son independientes. Retirar el manual no elimina atrasos. Una empresa bloqueada puede devolver equipos. La recepción física termina el atraso aunque falte la firma de devolución.

Comandos para tareas periódicas:

```powershell
python manage.py revisar_atrasos
python manage.py vencer_reservas
```

El primero también acepta `--empresa ID`. Ambos conservan historial sin duplicar cambios. Las plantillas de systemd los ejecutan cada cinco minutos, pero todavía deben instalarse en EC2. Las operaciones vuelven a comprobar atrasos y vencimientos sin depender exclusivamente del timer.

## API REST

Prefijo: `/api/v1/`. La raíz autenticada enlaza los recursos; devuelve JSON, no una pantalla administrativa. Las rutas terminan en `/` y los IDs de los ejemplos deben existir en la base.

### Autenticación y formatos

Puede utilizarse la sesión del login del sitio o el acceso por API:

1. `GET /api/v1/acceso/csrf/` devuelve `csrfToken` y establece su cookie.
2. `POST /api/v1/acceso/ingresar/` recibe `username` y `password`. Conservar cookies y enviar `X-CSRFToken` en toda escritura, incluidas las anónimas.
3. La respuesta indica `acceso=sistema` o `acceso=solicitud`. Tras entrar o salir, pedir un token CSRF nuevo porque puede rotar.
4. `POST /api/v1/acceso/salir/` cierra la sesión.

No se usa JWT. Los cuerpos son JSON excepto firmas, que requieren `multipart/form-data` con archivo PNG. No enviar base64. Campos de entrada desconocidos/protegidos se rechazan.

Listados paginan 20 registros con `page`, `count`, `next`, `previous` y `results`. Las rutas del router admiten `format=json` y sufijo `.json`; acceso/perfil usan las rutas directas documentadas. Las firmas privadas devuelven `image/png` y sus errores JSON.

### Recursos y acciones

En la tabla, `{id}` representa el ID del recurso indicado.

| Recurso después de `/api/v1/` | Métodos y acciones |
| --- | --- |
| `maquinaria/` | GET/POST; `{id}/` GET/PATCH; POST `{id}/trasladar/`, `baja/`, `reactivar/`; GET `{id}/historial/` |
| `bodegas/`, `obras/` | GET/POST; `{id}/` GET/PATCH; POST `{id}/desactivar/`, `reactivar/`; GET `{id}/historial/`. Obras queda por compatibilidad |
| `solicitudes-arriendo/` | GET listado/detalle; POST `enviar/` multipart; POST `{id}/aprobar/`, `rechazar/`, `cancelar/`, `entregar/`; GET `{id}/historial/`, `firma/` |
| `arriendos/` | GET listado/detalle; POST `{id}/recibir/`; GET `{id}/sesiones/`; POST `{id}/uso/iniciar/`, `uso/pausar/`, `uso/sincronizar/`; GET `{id}/firmas/entrega/`, `firmas/devolucion/` |
| `entregas/` | GET listado/detalle; POST creación manual; POST `{id}/confirmar/` multipart y `{id}/cancelar/` JSON |
| `devoluciones/` | GET listado/detalle; POST `{id}/confirmar/` multipart y `{id}/cancelar/` JSON. Se preparan mediante recibir, no POST de creación directa |
| `mantenimientos/` | GET/POST; GET `{id}/`; POST `{id}/iniciar/`, `finalizar/` |
| `empresas/` | GET listado/detalle; POST `{id}/bloquear/`, `desbloquear/`; GET `{id}/historial/`, `atrasos/` |
| `usuarios/` | GET/POST; GET/PATCH `{id}/`; GET `permisos-disponibles/`; GET/POST `{id}/permisos/`; POST `{id}/suspender/`, `reactivar/`; GET `{id}/historial/` |
| `solicitudes/` | Solicitudes de cuenta: GET listado/detalle; POST `{id}/aprobar/`, `rechazar/`; GET `{id}/historial/` |
| `condiciones/` | GET listado/detalle; POST publica una nueva versión con permiso correspondiente |
| `comprobantes/` | GET listado/detalle; GET `{id}/firma/`, privados por propietario o permiso administrativo |
| `perfil/` | GET/PATCH propios; POST `aceptar/` y `firmar/` solo para contratistas habilitados |
| `acceso/` | POST `registro/`, `ingresar/`, `salir/`, `reenviar/`; GET `csrf/` y `solicitud/` propia con sesión limitada |

No se expone eliminación física mediante DELETE ni reemplazo mediante PUT. Los permisos de escritura corresponden a los del template equivalente; ser usuario autenticado no concede acceso administrativo ni acceso a registros ajenos.

### Cuerpos principales

| Operación | Datos de entrada |
| --- | --- |
| Crear maquinaria | `codigo`, `nombre`, `marca`/`modelo` opcionales, `bodega`, `precio_diario`, `horas_iniciales`, `horas_ultima_mantencion` opcional/null |
| PATCH maquinaria | `nombre`, `marca`, `modelo` y/o `precio_diario`; omitir conserva el valor, no admite tarifa vacía/cero |
| Trasladar | `destino` (bodega ID) y `motivo`; baja/reactivar/desactivar/bloqueos/cancelaciones usan `motivo` |
| Enviar petición de arriendo | Multipart: `maquinaria`, `direccion_uso`, `comuna_uso`, `indicaciones_acceso` opcional, `devolucion_prevista`, `observaciones` opcional, `version_id`, `precio_visto`, `acepto=true`, `confirmar=true`, `firma` |
| Aprobar/rechazar petición | `motivo` obligatorio; preparar entrega desde petición usa `confirmar=true` |
| Confirmar entrega/devolución | Multipart: `confirmar=true` y archivo `firma` nuevo |
| Recibir físicamente | `bodega`, `observaciones`, `requiere_revision` booleano opcional y `confirmar=true` |
| Iniciar/pausar/sincronizar uso | `{}`; el cliente no envía horas ni fechas de trabajo |
| Programar mantenimiento | `maquinaria`, `fecha_programada` (AAAA-MM-DD), `descripcion` |
| Iniciar/finalizar mantenimiento | Inicio: `confirmar=true`. Fin: `resultado`, `apta_para_servicio` booleano y `confirmar=true` |
| Registro público | `username`, nombres opcionales, `email`, `rut`, `rut_empresa`, `razon_social`, `password1`, `password2` |
| Reenviar solicitud de cuenta | `rut_empresa`, `razon_social`, `comentario`; requiere sesión limitada de una cuenta rechazada |
| Revisar solicitud de cuenta | `motivo`; obligatorio para rechazar, opcional para aprobar |
| Crear usuario interno | `username`, nombres, `email`, `rut`, `rol=BODEGUERO|ADMINISTRADOR`, `password1`, `password2`, `motivo`; `crear_superusuario` solo para superusuarios |
| PATCH usuario | Nombre/apellido/correo y `motivo`; no altera RUT, username o empresa |
| Asignar permisos | `rol`, lista completa `permisos` (IDs otorgables), `motivo`; `superusuario` solo para superusuarios. Lista omitida equivale a vacía |
| Suspender/reactivar usuario | `motivo` y `confirmar=true`; no cambia su aprobación |
| Publicar condiciones | `version`, `contenido`; no modifica versiones anteriores |
| Aceptar condiciones | `version_id` vigente y `acepto=true`; luego firmar en 30 minutos con multipart `firma` y `confirmar=true` |
| PATCH perfil | `first_name`, `last_name` y/o `email` |

Las nuevas entradas no aceptan `obra_destino` ni `destino_legacy`; solo se devuelven como antecedentes. `precio_visto` detecta cambios desde que se abrió el formulario: el servidor decide el precio acordado. La identidad y empresa de quien solicita salen de la sesión.

Filtros principales (además de `page`):

- Maquinaria: `q`, `estado=DISPONIBLE|EN_USO|MANTENIMIENTO|BAJA`, `bodega`.
- Ubicaciones: `q`, `estado=activas|inactivas|todas`; bodegas admite `obra`.
- Peticiones de arriendo: `estado=PENDIENTE|APROBADA|RECHAZADA|CANCELADA|VENCIDA|ENTREGADA`, `maquinaria`.
- Arriendos: `estado=abierto|firma|cerrado`, `maquinaria`.
- Entregas/devoluciones: `estado=pendiente|confirmada|cancelada|vencida`.
- Mantenimientos: `estado=pendiente|curso|finalizada`, `maquinaria`.
- Empresas: `q`, `estado=todas|bloqueadas|habilitadas`.
- Usuarios: `q`, `rol`, `empresa`, `estado=habilitada|suspendida|pendiente|rechazada`.
- Solicitudes de cuenta: `q` (username), `empresa`, `estado=pendiente|rechazada|aprobada`.

Respuestas: 200 consulta/cambio, 201 creación, 400 validación/reglas, 403 sesión/CSRF/permisos, 404 registro ajeno/inexistente o página fuera de rango, 405 método no permitido, 406 formato no admitido, 409 conflicto de integridad y 415 cuerpo no admitido.

En empresas, `bloqueada_por_atraso` es el último estado guardado, mientras `bloqueo_por_atraso_actual` comprueba atrasos actuales. `tiene_bloqueo` combina el manual y el atraso actual. GET no crea eventos de historial.

## Pruebas y diagnóstico

```powershell
.\probar_postgresql.ps1
```

Pide la contraseña y usa una base de pruebas independiente, normalmente `test_buildcorp`; la cuenta necesita permiso para crearla. Si ya existe, Django solicita confirmación antes de eliminarla: no usar una base de pruebas que se necesite conservar. No elimina ni migra la base real `buildcorp`.

El script utiliza `verificar_postgresql.py` para capturar progreso y errores sin que Windows PowerShell interprete el stderr normal de Django como fallo. Guarda `pruebas-postgresql.log` en UTF-8, sin registrar la contraseña. `Creating test database...` y `Destroying test database...` son mensajes normales. El resultado esperado es `OK`.

**Verificación:** 320 pruebas aprobadas en PostgreSQL 18 temporal, y posteriormente el estudiante confirmó `OK` en su PostgreSQL local. Incluye funcionalidades, permisos, firmas, CSRF, historial y migración de destinos. Esta comprobación no sustituye verificar el servidor público después de desplegar.

## Despliegue y entrega académica

Seguir la [guía de EC2](deploy/README.md). La pauta exige aplicación y PostgreSQL en una única instancia de AWS Academy, accesible por IP/DNS. Los archivos Nginx/Gunicorn/systemd preparados son plantillas, no evidencia de despliegue completado.

Clonar el repositorio en EC2, crear un entorno virtual de Linux, instalar `requirements-production.txt`, configurar PostgreSQL y `/etc/buildcorp.env`, aplicar migraciones, ejecutar collectstatic, instalar/revisar Nginx y habilitar los servicios y el timer.

`drf.settings_production` exige una clave nueva y hosts concretos; usa `DEBUG=False`. Sus cookies/redirección HTTPS deben coincidir con el TLS realmente instalado. La guía explica el caso inicial por IP/HTTP.

Conservar la [evidencia de apoyo de IA](prompts_ia.md). Antes de entregar, completar el enlace real del repositorio y la IP/DNS al inicio de este README, verificar los flujos desde fuera de EC2 y preparar la defensa.

## Código, datos y respaldos

El `.gitignore` excluye entornos virtuales, cachés, logs, archivos de entorno, base SQLite, estáticos generados y `media/`. Revisar los archivos antes del primer envío. No subir contraseñas ni claves SSH `.pem`.

Git traslada código, no los datos de PostgreSQL ni las firmas. Si se trasladan datos locales a AWS, respaldar/restaurar la base y `media/` por separado y comprobar sus relaciones. Nginx no debe publicar `/media/`: las firmas solo se entregan mediante vistas autenticadas.

La recuperación/cambio de contraseñas por correo, pagos, multas y calendario de reservas futuras no forman parte del alcance implementado.
