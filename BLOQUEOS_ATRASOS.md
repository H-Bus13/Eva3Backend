# Alertas por atraso y bloqueos de empresa

## Activar

Desde la terminal del proyecto:

```powershell
.\configurar_postgresql.ps1
```

Aplica la migración 0011: bloqueo automático por atraso, permiso de bloqueo manual e historial. Los bloqueos existentes se conservan como manuales, con sus motivos actuales y sin inventar fecha ni responsable anteriores.

## Reglas

- Un arriendo está atrasado si venció la fecha prevista y no tiene recepción física ni cierre de devolución.
- La firma pendiente después de recibir físicamente la máquina no genera atraso de entrega.
- Un atraso bloquea nuevas entregas de toda la empresa, no solo al responsable del equipo.
- Se vuelve a comprobar antes de preparar y confirmar una entrega. No depende de que la tarea periódica se haya ejecutado.
- El bloqueo detectado se conserva aunque la entrega sea rechazada. La validación consulta también los atrasos actuales bajo el bloqueo de empresa.
- Al registrar la recepción física se revisa la empresa en la misma transacción. Se retira el bloqueo automático solo cuando no quedan equipos atrasados.
- Un bloqueo manual permanece hasta retirarlo con permiso, motivo y confirmación. Recibir equipos no elimina ese bloqueo.
- El bloqueo no impide iniciar sesión, consultar antecedentes, devolver equipos o utilizar un arriendo existente si la máquina no tiene restricciones de mantenimiento.
- No se calculan cobros ni multas.

## Pantallas y permisos

Alertas en el menú abre el panel. Personal con gestionar_arriendos consulta los arriendos atrasados y empresas. Usuarios comunes ven el aviso empresarial, pero solo sus propios arriendos: no los contratos de compañeros ni de otras empresas.

El detalle de empresa muestra bloqueo manual, automático, cantidad de atrasos e historial. Personal con gestionar_bloqueos_empresa puede aplicar o retirar bloqueos manuales. Ese permiso permite gestionar empresas, pero no concede acceso a contratos ajenos; para eso se requiere gestionar_arriendos.

Los integrantes de una empresa pueden consultar su propio estado e historial. Los motivos manuales son visibles a sus integrantes; el formulario lo informa al personal que los escribe.

Los avisos aparecen en Inicio, Mi perfil y Arriendos. Los cambios automáticos se atribuyen al Sistema; los manuales guardan usuario, fecha, acción y motivo. Se registran eventos solo cuando cambia el estado, sin repetir uno en cada consulta.

## Revisión periódica

Comando preparado para revisión local o futura programación en AWS:

```powershell
.\env\Scripts\python.exe manage.py revisar_atrasos
```

También admite `--empresa ID` para una empresa. Debe ejecutarse con la conexión PostgreSQL configurada en la misma terminal. Es idempotente y revisa cada empresa en su propia transacción.

No se creó todavía una tarea programada del sistema operativo. Se programará al preparar el despliegue en AWS. Mientras tanto, se actualizan bloqueos al abrir el panel, consultar el estado de empresa, preparar/confirmar entregas y registrar recepciones. Las pantallas del contratista sincronizan su propia empresa al entrar.

## Verificación

155 pruebas aprobadas en SQLite temporal. Incluyen persistencia del bloqueo cuando se rechaza una entrega, separación de bloqueos manuales/automáticos, múltiples equipos atrasados, recepción sin firma, casos no vencidos/cerrados, comando idempotente, permisos, privacidad, motivos, CSRF y rollback si falla el historial; se mantienen los módulos anteriores.

La migración y los bloqueos concurrentes no se probaron contra PostgreSQL desde el agente. Se aplica localmente con la contraseña del usuario.
