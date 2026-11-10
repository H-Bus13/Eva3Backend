# Consulta y reenvío de solicitudes

## Activar

En la terminal del proyecto ejecutar:

```powershell
.\configurar_postgresql.ps1
```

Esto aplica la migración 0004 con tu contraseña local de PostgreSQL. Si el servidor está detenido, iniciarlo con `env\Scripts\python.exe manage.py runserver` desde esa misma terminal.

## Recorrido del solicitante

- Usar /ingresar/ con el usuario y contraseña registrados.
- Si la cuenta está pendiente o rechazada, se abre /solicitud/.
- La cuenta rechazada ve el motivo y puede corregir RUT y razón social de la empresa e indicar qué antecedentes corrigió.
- Reenviar vuelve a dejar la cuenta pendiente e inactiva. No concede privilegios ni quita bloqueos de empresas.
- Si la empresa ya existe, no se sobrescribe su razón social desde este formulario.
- Si fue aprobada mientras consultaba, la pantalla informa el resultado y pide volver a ingresar. Esa consulta no se convierte automáticamente en una sesión normal.
- Cerrar consulta elimina la identificación limitada. La consulta también vence a los 30 minutos o si cambia la contraseña.

## Seguridad e historial

El backend normal continúa rechazando contratistas pendientes o rechazados. El formulario de ingreso solo comprueba sus credenciales para guardar una identificación de consulta separada, sin iniciar sesión con login(). Por tanto, los controles login_required continúan protegiendo perfil, firmas y administración incluso si el solicitante escribe sus direcciones directamente.

El historial conserva cada aprobación, rechazo y reenvío con fecha, actor y empresa del evento. Se muestra al solicitante y también al administrador en la lista de pendientes. El reenvío y las revisiones se guardan junto con su evento en una transacción y bloquean la fila del usuario para evitar decisiones simultáneas incompatibles.

La migración copia la última revisión anterior únicamente cuando se conocen su fecha, responsable y empresa. No reconstruye eventos que no fueron registrados. El motivo actual del rechazo sigue mostrándose aunque no haya información suficiente para copiarlo al historial.

Las cuentas aprobadas desactivadas no obtienen acceso normal ni pueden usar el ingreso limitado como alternativa.

## Verificación

47 pruebas aprobadas en una base SQLite temporal, sin modificar PostgreSQL. Incluyen acceso limitado, credenciales incorrectas, aislamiento de funciones protegidas, historial, corrección de empresa, reenvío doble, RUT inválido, aprobación posterior, vencimiento, cambio de contraseña, cierre de consulta, CSRF y copia de revisiones existentes. Se generó la migración y Django no detectó cambios adicionales pendientes.
