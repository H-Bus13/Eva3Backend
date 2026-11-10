# Registro de apoyo de IA

## 2026-11-09 — Diseño y creación de modelos

- Solicitud: proponer models.py para BuildCorp, explicar antes de implementar y comentar los bloques complejos del código.
- Contexto: arriendo de maquinaria, empresas contratistas, roles, firmas, condiciones, trazabilidad y mantención cada 250 horas de uso.
- Decisiones: usuario basado en AbstractUser; separación de empresas, obras, bodegas, arriendos y sesiones; historial de mantenciones y movimientos; restricciones de unicidad y fechas en la base de datos.
- Autorización: el estudiante aprobó incorporar la propuesta al proyecto.
- Alcance: estructura de datos y configuración inicial. Aún faltan templates, permisos, validación del RUT, servicios de entrega/devolución y uso, tareas automáticas y conexión PostgreSQL.
- Por indicación del estudiante se deshabilitó Django Admin. La pauta escrita pide utilizarlo; esta diferencia debe aclararse con el docente.
- La firma propuesta es un archivo con el trazo del usuario, sin integración con certificados.

## 2026-11-09 — Conexión PostgreSQL local

- El estudiante creó buildcorp, propietario postgres.
- Se configuró el backend PostgreSQL con credenciales leídas del entorno y se agregó psycopg a requirements.txt.
- configurar_postgresql.ps1 solicita la contraseña localmente y ejecuta migraciones; no guarda la contraseña en archivos.
- Se verificó que localhost:5432 acepta conexiones. La comprobación autenticada y las migraciones PostgreSQL quedan pendientes de ingresar la contraseña localmente.
- SQLite se conserva como archivo anterior; no se transfirieron sus datos a PostgreSQL.

## 2026-11-09 — Registro y aprobación de contratistas

- Solicitud aprobada: implementar cuentas pendientes de aprobación, validación del RUT y comentarios en bloques complejos.
- Implementación: formularios Django, templates propios de registro/login/inicio/revisión, backend que rechaza contratistas pendientes, campos de revisión y permiso específico para aprobar o rechazar.
- Seguridad: el registro fija rol y privilegios en el servidor; una transacción guarda empresa y cuenta; la revisión usa POST, CSRF y bloqueo de fila; aprobar no elimina el bloqueo de empresa.
- Se generó migración 0002 para aplicar localmente con configurar_postgresql.ps1. No se conoce ni se almacena la contraseña de PostgreSQL.
- Verificación: 20 pruebas aprobadas en SQLite temporal. No se aplicó la migración ni se ejecutaron pruebas contra PostgreSQL desde el agente.
- Pendientes del proyecto: creación de cuentas internas mediante pantalla protegida, firmas, condiciones, arriendos, timer, mantenciones y bloqueos automáticos.

## 2026-11-09 — Perfil, condiciones y firma

- El estudiante aprobó el código propuesto antes de solicitar su implementación.
- Se agregaron templates de perfil, publicación y comprobante; captura de firma mediante canvas y validación PNG con Pillow.
- Aceptación temporal en sesión, fecha del servidor y vencimiento de 30 minutos. Guardado transaccional con bloqueos de fila y comprobación de versión vigente. Reenvíos no duplican comprobantes de una misma versión y persona.
- Nueva migración 0003: autor de publicación y permisos específicos. Debe aplicarse localmente con la contraseña de PostgreSQL.
- Archivos privados por vistas autenticadas; sin publicación directa de MEDIA_ROOT. Los comprobantes anteriores se conservan.
- Verificación: 33 pruebas en base temporal, sintaxis JavaScript y revisión visual de aceptación, dibujo y guardado con datos de ensayo separados. No se aplicaron migraciones en PostgreSQL desde el agente.

## 2026-11-09 — Aviso al rechazar sin motivo

- Problema reportado: el formulario rechazaba la solicitud sin motivo mostrando texto sin diseño en otra página.
- Corrección aprobada: validación previa en el navegador con alerta y foco en el motivo; respaldo del servidor mediante mensajes y redirección al listado.
- La cuenta permanece pendiente e inactiva al intentar rechazar con motivo vacío o solo espacios. Aprobar sigue sin exigir motivo.

## 2026-11-09 — Consulta limitada y reenvío de solicitudes

- El estudiante aprobó la propuesta y solicitó implementarla.
- Se extendió el formulario de ingreso para identificar a contratistas pendientes o rechazados sin iniciar una sesión normal de Django. El backend de aprobación se conserva.
- Se agregaron pantalla de estado, cierre de consulta por POST, corrección de empresa y reenvío; historial de aprobación/rechazo/reenvío visible para solicitante y revisor.
- Seguridad: validación de contraseña y hash en la consulta, vencimiento de 30 minutos, CSRF, bloqueo de fila y transacciones, estados fijados en el servidor. El reenvío no levanta bloqueos de empresa ni concede permisos.
- Migración 0004: nuevo historial y copia de la última revisión conocida si tiene fecha, empresa y responsable. Debe aplicarse localmente con configurar_postgresql.ps1.
- Verificación: 47 pruebas aprobadas en SQLite temporal. No se ejecutó la migración contra PostgreSQL desde el agente.

## 2026-11-09 — Catálogo y gestión de maquinaria

- Alcance aprobado: catálogo y detalle; obras/bodegas; alta y edición; traslado y baja de equipos disponibles; reactivación de baja por administrador con motivo y paso obligatorio a Mantenimiento.
- Se incorporaron formularios y servicios separados, permisos específicos, transacciones y bloqueos de fila, lecturas iniciales y trazabilidad por tipo de evento.
- Si la mantención inicial es desconocida o se cumplieron 250 horas desde ella, se crea una revisión programada y el equipo no queda Disponible. Reactivar también programa revisión sin borrar su baja ni alterar las horas.
- Las ediciones no aceptan código, estado, horas ni bodega; el traslado y las operaciones se verifican en servidor. Las empresas contratistas solo consultan.
- Migración 0005 preparada para aplicar localmente con configurar_postgresql.ps1. No se conoce la contraseña de PostgreSQL ni se aplicó la migración desde el agente.
- Verificación: 66 pruebas aprobadas en SQLite temporal; configuración sin errores. La finalización de mantenciones y los arriendos quedan para próximos bloques.

## 2026-11-09 — Bodegas con dirección y obra opcional

- Ajuste aprobado: registrar maquinaria en bodegas de la empresa sin necesidad de asociarlas a una obra.
- Se agregó dirección propia y obra nullable/opcional a Bodega, junto con los cambios de formularios, etiquetas y pantallas. Las bodegas existentes conservan su obra; sus direcciones no se inventan.
- Migración 0006 preparada para aplicar localmente. La dirección vacía solo se usa al incorporar el campo a registros anteriores; los formularios requieren dirección para guardar bodegas nuevas o editadas.
- Verificación: 70 pruebas aprobadas en SQLite temporal, incluyendo creación sin obras, dirección obligatoria, maquinaria y traslado entre bodegas centrales y conservación de relaciones existentes. No se aplicó la migración en PostgreSQL desde el agente.

## 2026-11-09 — Desactivación reversible de obras y bodegas

- Solicitud aprobada: soft delete con activa, motivo, responsable, fechas e historial; filtros de activas/inactivas/todas y reactivación controlada.
- Reglas: no cerrar bodegas con equipos que no estén dados de baja ni obras con bodegas activas o arriendos abiertos. Reactivar una bodega requiere obra activa y administrador autorizado.
- Se excluyen ubicaciones desactivadas de nuevas operaciones; alta, traslado, edición e incorporación de bodegas coordinan bloqueos con las desactivaciones. Reactivar máquinas requiere ubicación habilitada.
- Migración 0007 preparada. Los registros actuales se mantienen activos y no se borran antecedentes.
- Verificación: 89 pruebas en SQLite temporal. No se aplicaron migraciones ni se probaron bloqueos concurrentes contra PostgreSQL desde el agente.

## 2026-11-09 — Programación, inicio y resultado de mantenciones

- Alcance y bloques de código aprobados antes de implementar.
- Se agregaron listado, filtros, detalle, programación, confirmación de inicio y formulario de finalización con aptitud.
- Se conservan las horas acumuladas; una revisión satisfactoria actualiza la referencia del siguiente ciclo de 250 horas. Un resultado no apto deja el equipo bloqueado y una tarea pendiente de seguimiento cuando corresponde.
- Las revisiones futuras no cambian el estado inmediatamente; la exigibilidad por fecha se consulta mediante propiedades del equipo y se advierte en catálogo/detalle. El próximo flujo de arriendos deberá consultar también ese bloqueo.
- Nuevos permisos, autoría de programación/finalización, eventos e invariantes de fecha/intervención en curso. Migración 0008 preparada para aplicar localmente.
- Verificación: 104 pruebas aprobadas en SQLite temporal. No se aplicó la migración en PostgreSQL desde el agente.

## 2026-11-09 — Entrega y devolución con firmas propias

- El estudiante aprobó alcance y bloques antes de implementar. Confirmó que toda la administración debe ser mediante templates propios y que Django Admin debe permanecer deshabilitado.
- Se agregaron solicitudes inmutables de entrega/recepción, vencimiento de una hora, cancelación con motivo, firma desde la cuenta del responsable y listados/detalles privados.
- La entrega vuelve a validar aprobación, empresa, obra/bodega, condiciones vigentes y disponibilidad al firmar. La solicitud no reserva equipos. Se crean el arriendo y los movimientos en una transacción.
- La recepción física cierra sesiones y acumula duración una sola vez. La firma posterior cierra documentalmente el arriendo; equipos dañados o con revisiones pendientes pasan a Mantenimiento. Correcciones y vencimientos conservan los antecedentes y no deshacen la recepción física.
- Migración 0009 preparada para aplicar localmente. Firmas privadas con limpieza de PNG en fallos transaccionales.
- Verificación: 123 pruebas aprobadas en SQLite temporal. No se aplicó la migración a PostgreSQL desde el agente. Timer interactivo, cobros y bloqueos por atraso quedan pendientes.

## 2026-11-09 — Contador de uso y revisión por horas

- Alcance y código principal aprobados antes de incorporar.
- Se agregó contador al detalle del arriendo, con inicio exclusivo del responsable, pausa del responsable/personal autorizado e historial con autores y motivos.
- Tiempo del servidor, transacciones, bloqueo de registros y acumulación única. Sincronización por POST con CSRF cada 15 segundos; la visualización se actualiza cada segundo.
- La revisión por intervalo se asegura al sincronizar, pausar o recibir; no detiene automáticamente una sesión. Al pausarla se bloquean nuevos inicios. La recepción física cierra y atribuye sesiones sin contabilizar dos veces.
- Migración 0010 preparada. Se conservan sesiones históricas sin inventar sus autores.
- Verificación: 138 pruebas aprobadas en SQLite temporal; JavaScript sin errores de sintaxis y sin migraciones adicionales pendientes. No se aplicó la migración en PostgreSQL desde el agente.

## 2026-11-09 — Alertas y bloqueos por atraso, sin cobros ni multas

- El estudiante aprobó el alcance y código principal, excluyendo cobros y multas.
- Se conserva bloqueada como indicador manual y se agrega bloqueada_por_atraso. El historial distingue automatismos sin actor y acciones manuales con usuario y motivo.
- La detección usa plazo vencido sin recepción física ni cierre. La recepción sincroniza el desbloqueo; no toca el manual. Entregas y firmas verifican atrasos actuales y conservan el bloqueo aunque la operación se rechace.
- Panel privado de alertas/empresas, gestión manual por permiso y avisos en Inicio, Perfil y Arriendos. Los contratos ajenos no quedan expuestos por compartir empresa ni por tener solo el permiso de bloqueo.
- Se agregó revisar_atrasos con filtro opcional por empresa, preparado para programar en AWS; no se instaló todavía una tarea periódica del sistema.
- Migración 0011 preparada para aplicar localmente. Verificación: 155 pruebas aprobadas en SQLite temporal y ninguna migración adicional pendiente. No se aplicó la migración contra PostgreSQL desde el agente.

## 2026-11-09 — Usuarios, permisos y Bootstrap

- El estudiante aprobó el alcance y código principal antes de incorporar.
- Administración mediante templates propios: listado/filtros, alta de cuentas internas y superusuarios, edición de datos, roles/permisos, activación/suspensión e historial de cambios. Django Admin permanece deshabilitado.
- Seguridad: límites por actor, protección de cuentas superiores y propias, control serializado del último superusuario, relectura del actor, aprobación separada de suspensión y ausencia de contraseñas en el historial.
- Bootstrap 5.3.8 local, descargado desde los recursos oficiales indicados en https://getbootstrap.com/docs/5.3/getting-started/download/ y verificado con sus hashes SHA-384. Nueva base adaptable y renderer de formularios, sin cambiar IDs de firma/timer.
- Migración 0012 preparada para aplicar localmente. No crea cuentas en PostgreSQL.
- Verificación: 175 pruebas aprobadas en SQLite temporal. Revisión visual de listado, formulario y menú móvil de 390 px con datos de ensayo aislados. No se aplicó la migración a PostgreSQL desde el agente.

## 2026-11-09 — Endpoints REST de maquinaria, obras y bodegas

- El estudiante aprobó los bloques propuestos antes de incorporar. Se aclaró que el proyecto anterior tenía vistas/templates y un endpoint JSON, pero no una API REST completa.
- Se instaló djangorestframework 3.18.3 y se fijó en requirements.txt. Configuración de sesión, CSRF, JSON, paginación y errores comunes.
- Primer bloque /api/v1/: lectura, alta, PATCH y acciones de maquinaria, obras y bodegas, con historial y baja/desactivación reversible. No se expone DELETE ni PUT.
- Serializers de entrada estrictos y salida separados; permisos por acción y rechazo de cuentas no habilitadas. Las escrituras usan los servicios existentes. Los servicios de edición aceptan campos parciales y los combinan después de bloquear la fila para preservar otros cambios.
- Verificación: 202 pruebas aprobadas en SQLite temporal (175 anteriores y 27 de endpoints). Sin nuevas migraciones. PostgreSQL todavía requiere prueba local con la contraseña del usuario.
- Pendientes REST: arriendos/firmas/uso, mantenciones, usuarios y empresas; sus templates siguen funcionando.

## 2026-11-09 — Endpoints de arriendos, firmas y uso

- El estudiante aprobó el alcance y el código antes de implementar.
- Se incorporaron consultas privadas de arriendos/solicitudes, preparación y confirmación de entregas, recepción física, confirmación de devolución y cancelación con motivo.
- Confirmaciones multipart con PNG validado por el mismo formulario del perfil. Firmas servidas por rutas autenticadas con errores JSON y sin exponer rutas de almacenamiento.
- Timer mediante servicios existentes: inicio, pausa, sincronización e historial; no acepta horas del cliente. Revisión de 250 horas y recepción física conservan sus reglas.
- Consultas de visibilidad compartidas entre templates y API. Permisos por acción y dueño; CSRF permanece activo.
- Verificación: 222 pruebas en SQLite temporal, incluidas 20 nuevas; sin cambios de modelos. PostgreSQL requiere comprobación local, y sus bloqueos no fueron probados con SQLite.
- Documentación de uso en API_ARRIENDOS.md. Pendientes REST: mantenimiento, usuarios/permisos y empresas/bloqueos.

## 2026-11-09 — Endpoints REST de mantenimiento

- El estudiante aprobó alcance y código antes de su incorporación.
- Recurso /api/v1/mantenimientos/: listado/detalle, programación, inicio y finalización con confirmación explícita; sin edición ni eliminación.
- Validación de entrada estricta y permisos por acción equivalentes a templates. Sesión y CSRF existentes conservados.
- Se reutilizan servicios transaccionales: disponibilidad, historial, referencia de mantenimiento sin reiniciar horas y seguimiento de resultados no aptos. Programar a futuro permite arriendo; intervenir requiere equipo sin uso abierto.
- Verificación: 237 pruebas aprobadas en SQLite temporal (15 nuevas). No se modificó PostgreSQL ni se comprobaron sus bloqueos de filas.
- Documentación: API_MANTENIMIENTO.md. Pendientes REST: usuarios/permisos y empresas/bloqueos.

## 2026-11-10 — Endpoints REST de empresas y bloqueos

- Alcance y código aprobados por el estudiante antes de incorporar.
- Recurso empresas con listado/detalle, bloqueo/desbloqueo manual con motivo, historial y atrasos. No se permite crear, editar ni eliminar empresas en este bloque.
- Permisos separados: gestión de arriendos para detalles de atrasos; gestión de bloqueos para cambios manuales. Cuenta habilitada, sesión, CSRF y entradas estrictas.
- Consultas calculan atrasos actuales con EXISTS sin modificar flags ni historial. La respuesta distingue el estado automático guardado del atraso actual; desbloquear manualmente no elimina impedimentos por atraso.
- Verificación: 249 pruebas aprobadas en SQLite temporal, incluidas 12 nuevas. PostgreSQL no fue modificado y sus bloqueos de filas requieren prueba local.
- Documentación API_EMPRESAS.md. Pendientes REST: usuarios/permisos, solicitudes de contratistas y perfil/condiciones.

## 2026-11-10 — Cierre de endpoints y preparación de entrega

- El estudiante pidió implementar los bloques pendientes: usuarios/permisos, solicitudes de contratistas y perfil/condiciones.
- API de cuentas internas mediante servicios existentes; protección de cuenta propia, permisos superiores, último superusuario y actor releído bajo bloqueo. PATCH conserva campos omitidos bajo bloqueo.
- Registro y acceso JSON, incluida sesión limitada de solicitudes; CSRF explícito también en POST anónimos. Rechazo con motivo, aprobación y reenvío transaccionales sin cambiar las pantallas existentes.
- Perfil propio, publicación inmutable de términos, aceptación temporal y firma PNG privada. Comprobantes sin rutas de almacenamiento; bloqueo por usuario/publicación y limpieza de archivos si falla SQL.
- Verificación: 270 pruebas en SQLite temporal, incluidas 21 nuevas. Sin acceso a contraseña PostgreSQL ni instancia AWS para validar allí.
- README y documentación API_CUENTAS.md, revisión de pauta, script local de pruebas PostgreSQL y plantillas EC2 (settings_production, Gunicorn/Nginx, systemd y timer de atrasos). No se instalaron servicios, no se publicaron repositorios ni se crearon recursos AWS.
- Pendientes externos: ejecutar suite con PostgreSQL, desplegar/verificar EC2, activar timer allí y registrar IP/DNS y enlace de repositorio reales.

## 2026-11-10 — Modelos para solicitud iniciada por contratista

- El estudiante aprobó los modelos propuestos y precisó que no puede haber arriendos gratuitos.
- Precio de maquinaria nullable solo para datos pendientes de completar; precio asignado y precio acordado en solicitud estrictamente positivos, con validadores y restricciones SQL. Moneda CLP.
- SolicitudArriendo con condiciones/firma, precio conservado, revisión, reserva, cancelación y vínculo de entrega; HistorialSolicitudArriendo para transiciones.
- Migración 0013 creada; no aplicada por el agente a PostgreSQL. No se inventan precios ni se reescriben arriendos anteriores.
- Esta etapa no conecta todavía el nuevo flujo a templates/API ni automatiza reservas. Esos servicios/pantallas son el siguiente bloque; el flujo previo no se marca como reemplazado.

## 2026-11-10 — Precio en formularios, catálogo y API

- Código propuesto y aprobado antes de implementar.
- Precio diario requerido y positivo en alta/edición de templates; min/step de 0.01. Catálogo/detalle muestran CLP o aviso de tarifa pendiente.
- Servicios guardan tarifa, validan altas y registran cambios en historial sin modificar acuerdos anteriores. PATCH API conserva campos omitidos y rechaza null/cero/negativos.
- Nuevos casos de prueba de formularios, registro/edición HTML, API e historial. Los datos de las pruebas anteriores se completaron con tarifas positivas cuando creaban maquinaria desde formularios/API.
- No cambia modelos ni necesita migración adicional a 0013. La nueva solicitud de contratista sigue pendiente de conectar al flujo.

## 2026-11-10 — Solicitud, revisión, reserva y entrega por contratista

- Alcance, servicios principales y ejecución aprobados por el estudiante.
- Templates: solicitar desde catálogo con precio/condiciones/firma, Mis solicitudes, revisión con motivo, cancelación, historial y firma privada. El acceso principal del personal ahora es revisar peticiones en vez de iniciar entrega manual.
- API solicitudes-arriendo con envío multipart, consultas privadas, revisión/cancelación JSON, preparación de entrega y firmas autenticadas. Identidad/empresa/precio se fijan en el servidor; precio_visto detecta cambios antes de firmar.
- Reserva aprobada por una hora limitada por devolución; liberación por cancelación/vencimiento y guardas en traslados, bajas, mantenimiento, ubicaciones y entregas ajenas. GET informa vencimiento sin escribir. Comando vencer_reservas preparado en servicio periódico de EC2 aún no instalado.
- Entrega vinculada con precio y condiciones conservados; fecha de vencimiento limitada por reserva. Firma del contratista crea arriendo y pasa solicitud a Entregada en una transacción; no arranca timer automáticamente.
- Migración 0014 preparada. No se aplicó a PostgreSQL desde el agente. No se cambian contratos anteriores ni se activan tareas del sistema local.
- 306 pruebas aprobadas en SQLite temporal, incluidas 21 nuevas (flujo, privacidad, permisos, CSRF, reserva, cancelación, vencimiento, tarifa, guardas y limpieza de archivos). PostgreSQL/concurrencia requieren comprobación local.
- Compatibilidad: las rutas manuales previas para personal autorizado permanecen en equipos sin reserva y con tarifa positiva; ya no son el acceso principal de los templates. No se añadieron pagos/cobros/multas.

## 2026-11-10 — Destino por dirección/comuna sin catálogo de obras

- El estudiante aprobó alcance/modelos y confirmó su incorporación.
- Nuevas solicitudes y entregas requieren dirección y comuna; indicaciones opcionales. Se retira el selector de obra. Solicitud, comprobante y arriendo conservan el destino; la firma de entrega rechaza discrepancias.
- Servicios adaptados a destino sin FK de obra, incluidos reservas, timer y devolución. Se conservan bloqueos de bodegas y antecedentes antiguos.
- Migración 0015: campos de destino y marca histórica, FK opcional, copia de dirección de obras sin inventar comuna ni modificar firmas/precios. La marca distingue documentos migrados de los nuevos.
- Obras anteriores fuera del flujo habitual, en apartado desplegable de Bodegas. Relaciones/endpoints administrativos anteriores conservados por compatibilidad.
- 312 pruebas aprobadas en SQLite temporal, incluidas seis comprobaciones nuevas de destino/migración. La migración se verificó desde 0014 con datos históricos. No se aplicó a PostgreSQL del usuario ni se desplegó en AWS.
- Documentación actualizada y explicación de compatibilidad en DESTINOS_ARRIENDO.md.

## 2026-11-10 — Visor de firmas y errores visibles de registro

- El estudiante reportó que el PNG privado no tenía cierre dentro de la página y que el registro enfocaba correo sin explicar el motivo.
- Visor Bootstrap compartido para firmas de solicitudes, comprobantes de perfil y entrega/devolución: X, botón Cerrar, fondo y Escape; conserva las rutas privadas, elimina src al cerrar y devuelve el foco.
- Registro con novalidate para mostrar validación de Django en vez de depender del aviso nativo: resumen accesible y errores por campo; mensajes explícitos de correo obligatorio/inválido. POST vacío también queda ligado al formulario y muestra sus errores.
- Ajuste de acciones aceptado en la conversación: personal revisa pendientes mediante aprobar/rechazar; cancelar se ofrece después de aprobar. El dueño conserva cancelación de sus pendientes. El servicio también impide cancelar pendientes ajenas.
- 316 pruebas aprobadas en SQLite temporal, incluidas cuatro nuevas de errores/registro válido y acciones del personal. Sintaxis de los dos JS comprobada con Node. Sin cambios de modelos ni migraciones.
- La comprobación visual en Brave fue detenida por la herramienta porque no pudo determinar con suficiente confianza la URL actual; no se modificaron datos del navegador. Interacción visual de X/fondo/Escape pendiente de prueba local.

## 2026-11-10 — Condiciones y firma exclusivas de contratistas

- El estudiante confirmó separar el perfil de personal del perfil de contratista.
- Perfil HTML y API de cuentas internas muestra datos/rol, sin aceptación ni firma personal de arriendo. Se comprueban rol, flags de staff/superusuario, aprobación, actividad y suspensión.
- Aceptar/firmar por URL directa o API rechaza cuentas internas con 403; la firma relee al usuario bajo bloqueo para detectar cambios de rol. Los superusuarios con rol antiguo CONTRATISTA también se consideran internos.
- Publicar condiciones y consultar comprobantes ajenos mantiene sus permisos administrativos; no se eliminan aceptaciones anteriores.
- 320 pruebas aprobadas en SQLite temporal, incluidas cuatro nuevas de perfiles, restricciones y conservación de funciones administrativas. Sin cambios de modelos ni nuevas migraciones.

## 2026-11-10 — Corrección de pruebas de firmas en PostgreSQL

- El estudiante adjuntó errores de conexión cerrada en dos clases de pruebas de firmas/entregas.
- Causa encontrada: dos respuestas FileResponse se cerraban mediante respuesta.close() dentro de TestCase. Ese cierre disparaba request_finished sin la protección del cliente de pruebas y podía cerrar la conexión con una transacción de prueba abierta. SQLite en memoria no evidenciaba el problema.
- Se consumen las respuestas mediante streaming_content y se comprueba la cabecera PNG. El wrapper del cliente realiza el cierre sin invalidar la conexión. No se alteró la gestión de conexiones de la aplicación ni se ocultaron excepciones.
- Verificación real: 320 pruebas aprobadas en PostgreSQL 18 temporal, en 127.0.0.1:55439, con base/usuario/contraseña de ensayo independientes. Se destruyó la base de pruebas y se detuvo el servidor temporal. No se conectó a buildcorp ni se utilizó la contraseña del usuario.
- probar_postgresql.ps1 conserva ahora stdout/stderr completos en pruebas-postgresql.log sin registrar la contraseña. Sintaxis PowerShell verificada.
- Repetir el script localmente confirma además la instalación y credenciales concretas del estudiante. No se requieren migraciones para esta corrección.

## 2026-11-10 — Captura compatible con Windows PowerShell

- El estudiante reportó NativeCommandError al mostrar Creating test database for alias default: era salida de progreso de Django en stderr, interpretada por Windows PowerShell al combinarla con Tee-Object.
- La captura se trasladó a verificar_postgresql.py: combina stdout/stderr antes de PowerShell, muestra el progreso y conserva el código real de salida y el registro UTF-8. El stdin permanece conectado para las confirmaciones de Django.
- probar_postgresql.ps1 sigue solicitando contraseña segura y restaurando PGPASSWORD; se guarda con BOM UTF-8 para que Windows PowerShell lea correctamente Contraseña.
- Verificación ejecutada con Windows PowerShell 5.1 y ErrorActionPreference=Stop: progreso por stderr sin NativeCommandError, caracteres UTF-8 conservados y códigos 0/7 mantenidos. Sintaxis del script validada. No se repitió la suite de Django, pues no cambió el proyecto ni las pruebas; la ejecución anterior completa en PostgreSQL 18 pasó 320 pruebas.

## 2026-11-10 — Consolidación de documentación para el repositorio

- El estudiante autorizó reunir las instrucciones útiles y retirar los Markdown auxiliares, conservando README.md, prompts_ia.md y deploy/README.md.
- README reescrito con instalación, roles, flujo vigente por dirección/comuna, firmas/reservas, mantenimiento, bloqueos, API, pruebas PostgreSQL y entrega/despliegue. Se retiraron referencias a documentos separados y cifras antiguas de verificación.
- Se conservaron los 19 documentos auxiliares en un respaldo fuera del proyecto y se trasladaron sus originales fuera de la carpeta del repositorio, evitando su eliminación permanente. No se modificaron archivos de dependencias, código de la aplicación ni datos.
- Verificación: quedan dos Markdown en la raíz más deploy/README.md; respaldo íntegro y enlaces relativos de las guías existentes. No se ejecutaron pruebas funcionales por tratarse solo de documentación.
