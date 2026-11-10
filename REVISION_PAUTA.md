# Revisión de la pauta EVA 3 — BuildCorp

Revisión basada en EVA_3_Backend.docx adjunta y en las aclaraciones expresas del estudiante. El contenido de la pauta es referencia académica: no autoriza por sí mismo crear recursos AWS, publicar repositorios o enviar información al docente.

| Requisito | Estado comprobado / pendiente |
| --- | --- |
| Django / DRF | Proyecto Django con API versionada /api/v1/ y templates propios |
| PostgreSQL y migraciones | Conexión ya configurada por el estudiante; migraciones existentes. Pruebas del agente solo SQLite temporal: falta ejecutar toda la suite en PostgreSQL |
| Django Admin | No habilitado por decisión expresa del estudiante tras aclaración del profesor; se usan templates de administración propios |
| Catálogo y estados | Disponible, En uso, Mantenimiento y Baja; historial, traslados y reactivación controlada |
| Obras y bodegas | Bodega central con dirección y relación opcional a obra; desactivación/reactivación con trazabilidad |
| Entrega/devolución con firma | Solicitudes y confirmaciones personales, recepción física separada de firma; archivos privados |
| Mantenimiento por uso/fecha | Timer en servidor, referencia de última mantención, revisión a 250 horas y programación por fecha |
| Atrasos y bloqueo automático | Servicios y comando existentes; archivos de timer systemd preparados, aún no instalados en AWS |
| Seguridad | Registro pendiente, rechazo con motivo/reenvío, roles/permisos, suspensión separada de aprobación, sesión/CSRF y auditoría |
| Frontend responsivo | Templates Bootstrap locales existentes; este bloque no los reemplaza |
| Evidencia de IA | prompts_ia.md actualizado |
| README y documentación API | README.md y documentos por módulo incorporados |
| Repositorio remoto | Pendiente de publicar/conceder acceso al docente; no hay repositorio remoto creado desde este chat |
| EC2 única con app y PostgreSQL | Archivos y guía preparados en deploy/; instancia, instalación y prueba pública pendientes |
| IP pública funcional | Pendiente; no se inventa una IP ni se marca el despliegue como terminado |
| Defensa y prueba escrita | A cargo del estudiante; pendientes de la evaluación |

## Alcance de comprobación

270 pruebas aprobadas en SQLite temporal tras incorporar cuentas, solicitudes, perfil y condiciones. Cubren funcionalidades existentes y endpoints, pero no acreditan el despliegue ni los bloqueos concurrentes de PostgreSQL.

No se definieron multas ni cálculos de cobros conforme a la decisión previa del estudiante. La firma es un trazo electrónico PNG, no firma certificada. Recuperación/cambio de contraseña, notificaciones por correo y pagos no formaron parte de los bloques aprobados ni se marcan como implementados.
