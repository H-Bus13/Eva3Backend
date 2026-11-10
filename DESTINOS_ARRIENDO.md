# Dirección de uso en lugar de obra

## Nuevas solicitudes

El contratista indica direccion_uso (obligatoria, hasta 255 caracteres), comuna_uso (obligatoria, hasta 100) e indicaciones_acceso (opcional, hasta 3000). Se recortan espacios y se rechazan los campos obligatorios vacíos. Ya no selecciona una obra ni necesita permisos para crear ubicaciones.

Estos datos aparecen antes de firmar. Se guardan en SolicitudArriendo y se copian sin edición a SolicitudEntrega y Arriendo. La confirmación verifica que el comprobante coincida con la solicitud firmada. Las rutas no permiten editar el destino: cancelar y crear una nueva solicitud si cambia la dirección.

Los servicios de bloqueo, aprobación, reservas, entrega, timer, recepción y devolución funcionan sin obra_destino. Siguen comprobando las ubicaciones reales de almacenamiento de maquinaria y las relaciones antiguas cuando existan.

## API

En /api/v1/solicitudes-arriendo/enviar/ sustituir obra_destino por direccion_uso, comuna_uso e indicaciones_acceso opcional. Se mantiene el formato multipart para la firma.

La entrada manual de /api/v1/entregas/ también requiere esos datos. En ambos casos, obra_destino y destino_legacy son de solo lectura: enviarlos como entrada devuelve error por campo desconocido. Las lecturas incluyen los nuevos datos y la relación antigua si existe.

Ejemplo de destino:

```json
{
  "direccion_uso": "Avenida Principal 1234",
  "comuna_uso": "Santiago",
  "indicaciones_acceso": "Ingresar por portón lateral; avisar al responsable"
}
```

No se usa un catálogo de comunas ni geocodificación; son textos validados. No es la dirección de la bodega ni la dirección fiscal de la empresa.

## Antecedentes y migración

0015 agrega los campos a los tres documentos y vuelve opcional obra_destino. Copia la dirección de la obra asociada en los registros anteriores, conserva las relaciones y marca destino_legacy=true. No inventa comunas ni altera archivos de firma, precios o condiciones.

La dirección copiada es un antecedente recuperado del registro disponible al migrar; no se afirma que sea una nueva dirección aceptada por quien firmó anteriormente. La interfaz señala el origen histórico y la comuna sin registrar. Los registros nuevos usan destino_legacy=false.

Los campos de BD permiten vacíos para mantener antecedentes incompletos; formularios, serializers y servicios exigen dirección/comuna en operaciones nuevas. La referencia antigua no puede sustituir esos datos en una solicitud nueva.

Las bodegas mantienen dirección propia y relación opcional heredada; no necesitan obra. La página Bodegas presenta las obras anteriores en un apartado desplegable, retirando los accesos habituales para crear/editar obras. Los endpoints administrativos previos de obras siguen disponibles por compatibilidad, sin intervenir en los nuevos destinos de uso.

## Aplicar localmente

Detener runserver antes de migrar. Respaldar la base si contiene datos que se deban conservar. En la misma terminal:

```powershell
.\configurar_postgresql.ps1
python manage.py runserver
```

El script pide la contraseña local y aplica las migraciones pendientes. No se ejecutó contra PostgreSQL desde el agente.

## Verificación

312 pruebas aprobadas en SQLite temporal. Se comprobó el flujo completo sin ninguna obra registrada, incluyendo uso, recepción y firma de devolución; límites/obligatoriedad de dirección y comuna; visualización; rechazo de obra y marca histórica como entradas; destino no editable; comprobante alterado; y migración real desde 0014 con copia de dirección sin cambiar firmas ni inventar comuna.

Los bloqueos de filas y la ejecución contra PostgreSQL requieren verificación local con probar_postgresql.ps1. No se han desplegado cambios en EC2 desde el agente.
