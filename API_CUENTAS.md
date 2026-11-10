# API de cuentas, solicitudes, perfil y condiciones

Complementa API_INVENTARIO.md, API_ARRIENDOS.md, API_MANTENIMIENTO.md y API_EMPRESAS.md. Todos los cuerpos son JSON salvo las firmas PNG multipart. Los modelos existentes permanecen iguales.

## Acceso por API

1. GET /api/v1/acceso/csrf/ devuelve csrfToken y establece la cookie CSRF.
2. Conservar cookies y enviar X-CSRFToken en cada escritura, también las anónimas.
3. POST /api/v1/acceso/ingresar/ con username y password. La respuesta indica acceso=sistema o acceso=solicitud.
4. Después de entrar o salir, pedir otra vez /acceso/csrf/: el token puede rotar.
5. POST /api/v1/acceso/salir/ cierra ambas clases de sesión.

También se puede iniciar sesión mediante el template habitual. No se implementaron tokens JWT; se utiliza la sesión Django del mismo sitio.

## Registro y solicitudes

| Método | Ruta después de /api/v1/ | Función |
| --- | --- | --- |
| POST | acceso/registro/ | Registro público pendiente |
| GET | acceso/solicitud/ | Consultar solicitud propia con sesión limitada |
| POST | acceso/reenviar/ | Reenviar solicitud rechazada |
| GET | solicitudes/ | Listado administrativo |
| GET | solicitudes/{id}/ | Detalle administrativo |
| GET | solicitudes/{id}/historial/ | Revisiones y reenvíos |
| POST | solicitudes/{id}/aprobar/ | Aprobar pendiente |
| POST | solicitudes/{id}/rechazar/ | Rechazar con motivo |

Registro: username, first_name y last_name opcionales, email, rut, rut_empresa, razon_social, password1 y password2. Los RUT se validan y normalizan; las contraseñas pasan las validaciones Django. No se pueden enviar rol, aprobación, flags de staff o superusuario. Una empresa existente no se renombra desde el registro.

Aprobar/rechazar usa {"motivo": "Resultado de revisión"}. El rechazo exige motivo, máximo 1000 caracteres; aprobar puede omitirlo. El permiso es maquinaria.aprobar_contratista. No se revisan solicitudes ya resueltas y aprobar no elimina suspensión ni bloqueos de empresa.

Reenvío: rut_empresa, razon_social y comentario. Requiere sesión limitada vigente y estado rechazado; queda pendiente e inactivo otra vez. La sesión limitada vence a los 30 minutos, no permite consultar otros usuarios ni habilita inventario/perfil. Tras aprobar, se debe ingresar nuevamente.

Solicitudes filtra por q (username), estado=pendiente|rechazada|aprobada, empresa=ID y page. Solo incluye contratistas sin privilegios internos. Se rechazan filtros desconocidos.

## Administración de usuarios

Requiere rol Administrador o superusuario, más maquinaria.gestionar_usuarios. Los servicios releen al actor bajo bloqueo y protegen cuenta propia, cuentas superiores y último superusuario activo.

| Método | Ruta después de /api/v1/ | Función |
| --- | --- | --- |
| GET | usuarios/ | Listar/filtros |
| GET | usuarios/{id}/ | Datos administrativos |
| POST | usuarios/ | Crear cuenta interna |
| PATCH | usuarios/{id}/ | Editar nombre/apellido/correo con motivo |
| GET | usuarios/permisos-disponibles/ | IDs de permisos otorgables por el actor |
| GET, POST | usuarios/{id}/permisos/ | Consultar/asignar rol y permisos |
| POST | usuarios/{id}/suspender/ | Suspender con motivo y confirmación |
| POST | usuarios/{id}/reactivar/ | Reactivar con motivo y confirmación |
| GET | usuarios/{id}/historial/ | Auditoría paginada |

Alta interna: username, first_name, last_name, email, rut, rol=BODEGUERO|ADMINISTRADOR, password1, password2, motivo. Solo superusuarios pueden enviar crear_superusuario=true, con rol Administrador. Las contraseñas son de entrada: nunca salen ni se guardan en auditoría.

PATCH: first_name, last_name y/o email, más motivo obligatorio. Los campos omitidos se conservan después de bloquear el usuario. No cambia RUT, username, empresa o contraseña.

Asignar permisos: rol, permisos (lista completa de IDs otorgables), motivo; superusuario solo lo puede enviar un superusuario. Omitir permisos equivale a lista vacía, igual que en el formulario. No se convierten contratistas en cuentas internas. Suspender/reactivar: {"motivo": "Cambio autorizado", "confirmar": true}. Reactivar no aprueba solicitudes.

Filtros usuarios: q (usuario/nombres/RUT/email), rol, empresa, estado=habilitada|suspendida|pendiente|rechazada y page.

## Perfil, condiciones y firmas

| Método | Ruta después de /api/v1/ | Función |
| --- | --- | --- |
| GET | perfil/ | Perfil propio, términos vigentes y aceptaciones |
| PATCH | perfil/ | Actualizar nombre/apellido/correo propios |
| GET | condiciones/ | Versiones publicadas paginadas |
| GET | condiciones/{id}/ | Texto de una versión publicada |
| POST | condiciones/ | Publicar nueva versión, permiso publicar_terminos |
| POST | perfil/aceptar/ | Aceptación temporal de versión vigente |
| POST | perfil/firmar/ | Guardar PNG después de aceptar |
| GET | comprobantes/ | Comprobantes propios (o todos con consultar_firmas) |
| GET | comprobantes/{id}/ | Datos y condiciones aceptadas |
| GET | comprobantes/{id}/firma/ | Imagen privada |

Publicar: version y contenido; no permite editar/eliminar versiones anteriores. Aceptar: {"version_id": 1, "acepto": true}. Firmar dentro de 30 minutos: multipart con archivo firma y confirmar=true. La firma debe ser PNG válido con trazo; se regenera eliminando metadatos. Es una firma electrónica dibujada, no una firma certificada ni validación independiente de identidad.

Si cambia la versión o vence la aceptación, se debe volver a aceptar. La operación se serializa por usuario y publicación; repetir no duplica comprobantes. Las rutas privadas no exponen nombres de almacenamiento y devuelven PNG solo al dueño o a quien tenga consultar_firmas. GET lleva no-store. No hay ruta pública de medios.

## Errores y pruebas

Listados paginan 20 registros con page, count, next, previous, results. Los endpoints del router admiten format=json y sufijo .json. Los endpoints directos de acceso/perfil usan las rutas indicadas sin sufijo.

200 consulta/cambio correcto; 201 creación; 400 validación/regla; 403 sesión, permiso o CSRF; 404 registro/página ajena o inexistente; 405 método no disponible; 409 integridad; 415 formato no admitido. No hay eliminación física ni recuperación de contraseña/cambio de contraseña en este alcance.

Verificación: 270 pruebas aprobadas en SQLite temporal, incluidas 21 de este bloque. No se ejecutaron contra PostgreSQL desde el agente. Para hacerlo localmente, ver probar_postgresql.ps1.

Actualización de perfil por rol: GET perfil/ devuelve solo usuario y puede_firmar_condiciones=false para cuentas internas. Las rutas perfil/aceptar/ y perfil/firmar/ son exclusivas de contratistas habilitados; el personal recibe 403. Los permisos publicar_terminos y consultar_firmas mantienen su funcionamiento administrativo independiente.
