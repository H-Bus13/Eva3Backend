# Perfil y firma de condiciones

## Activar en PostgreSQL

Desde la terminal del proyecto:

```powershell
.\configurar_postgresql.ps1
.\env\Scripts\python.exe manage.py runserver
```

El primer comando pide la contraseña local y aplica la migración 0003, que agrega el autor de cada publicación y los permisos específicos. Pillow 13.0.0 ya está instalado en el entorno del proyecto y registrado en requirements.txt. En otra instalación ejecutar `python -m pip install -r requirements.txt`.

## Recorrido

1. Ingresar con una cuenta de superusuario existente.
2. Abrir /condiciones/publicar/ o el enlace Condiciones.
3. Escribir el identificador (por ejemplo 1.0) y revisar el texto completo antes de publicar. Hay un ejemplo académico desplegable que no se publica automáticamente.
4. El usuario aprobado ingresa en /perfil/ o Mi perfil.
5. Lee el texto vigente y marca la aceptación. El servidor registra el momento en su sesión.
6. Dibuja con mouse o pantalla táctil y guarda. La aceptación temporal vence a los 30 minutos.
7. Puede consultar su comprobante, el texto aceptado y la firma desde su historial.

Una versión nueva exige aceptar y firmar otra vez. Los comprobantes anteriores siguen disponibles con su versión original. La pantalla de publicación solo permite crear versiones: no ofrece editar ni eliminar las previas.

## Permisos y archivos

- publicar_terminos: permite publicar nuevas condiciones.
- consultar_firmas: permite consultar comprobantes y firmas ajenos por sus rutas protegidas.
- Un superusuario activo dispone de esos permisos. Los usuarios comunes solo acceden a sus propios comprobantes.
- Los PNG se almacenan bajo MEDIA_ROOT. No se publica una ruta /media/; en el despliegue tampoco debe exponerse esa carpeta como contenido público.
- Se valida tamaño, formato, dimensiones y presencia de trazos; se regenera el PNG sin sus metadatos originales.
- La firma es un trazo electrónico: no incorpora certificado ni verifica automáticamente la identidad del firmante.
- La integración de este requisito con la autorización de arriendos queda para el bloque de arriendos.

## Verificación

33 pruebas automatizadas aprobadas en SQLite temporal: incluyen condiciones, expiración, cambios de versión, archivos vacíos y corruptos, comprobantes privados, publicación protegida y limpieza de archivos cuando falla la base. JavaScript verificado sin errores de sintaxis. Recorrido visual de aceptación, dibujo y guardado comprobado en un servidor separado con datos de ensayo; no se alteró PostgreSQL.

## Perfil según tipo de cuenta

La aceptación y firma de condiciones de arriendo están disponibles solo para contratistas aprobados, activos, no suspendidos y sin privilegios de staff/superusuario. Bodegueros, administradores y superusuarios ven datos personales y rol, sin condiciones ni comprobantes personales en su perfil.

Las rutas HTML y API de aceptar/firmar rechazan cuentas internas con 403, incluso si se invocan directamente. El servicio de firma vuelve a comprobar la cuenta bajo bloqueo. No se eliminan aceptaciones históricas.

La publicación de condiciones y la consulta administrativa de comprobantes continúan disponibles con sus permisos habituales.
