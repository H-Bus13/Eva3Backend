# BuildCorp

Sistema de arriendo y control de maquinaria con Django, Django REST Framework, PostgreSQL y templates Bootstrap. Incluye inventario, obras/bodegas, usuarios con aprobación, condiciones/firma, entrega/devolución, timer de trabajo, mantenimiento y bloqueos por atraso. No calcula cobros ni multas.

## Ejecutar localmente

Requiere una versión de Python compatible con requirements.txt y PostgreSQL. Crear base vacía buildcorp y configurar PGDATABASE, PGUSER, PGHOST y PGPORT si difieren de los valores locales por defecto.

```powershell
python -m venv env
.\env\Scripts\python.exe -m pip install -r requirements.txt
.\configurar_postgresql.ps1
.\env\Scripts\python.exe manage.py createsuperuser
.\env\Scripts\python.exe manage.py runserver
```

Si ya tienes un superusuario, omite createsuperuser. El script solicita la contraseña sin mostrarla y aplica migraciones; ejecutar en la misma terminal donde iniciarás el servidor. No hay cuentas ni contraseñas de demostración incorporadas.

Abrir http://127.0.0.1:8000/. Administración desde templates propios; Django Admin está deshabilitado conforme a la aclaración del profesor comunicada por el estudiante.

## API y documentación

Raíz autenticada: /api/v1/. Acceso y perfil tienen rutas directas documentadas en API_CUENTAS.md.

- API_INVENTARIO.md: maquinaria, obras y bodegas.
- API_ARRIENDOS.md: solicitudes, entrega/devolución, firmas y horas.
- API_MANTENIMIENTO.md: programación, intervención y resultados.
- API_EMPRESAS.md: empresas, bloqueos e historial.
- API_CUENTAS.md: registro, acceso, usuarios/permisos, solicitudes, perfil y condiciones.
- deploy/README.md: preparación EC2, servicios y revisión periódica de atrasos.
- REVISION_PAUTA.md: cobertura de requisitos y comprobaciones pendientes.
- prompts_ia.md: registro de apoyo de IA.

## Pruebas

```powershell
.\probar_postgresql.ps1
```

Se solicita contraseña y se usa una base de pruebas independiente (normalmente test_buildcorp); la cuenta necesita permiso para crearla. Si ya existe, Django pide confirmación antes de eliminarla. No usar una base de pruebas que necesites conservar. El script no aplica cambios de migraciones a buildcorp.

Última validación del agente: 270 pruebas aprobadas con SQLite temporal. PostgreSQL y los bloqueos concurrentes requieren comprobación en el entorno real. No se modifica ni elimina maquinaria, firmas o historiales para probar.

## Despliegue

Preparado con settings_production, Gunicorn, Nginx y systemd. Los archivos son plantillas: todavía no están instalados en una instancia.

**IP pública/DNS de EC2: pendiente de despliegue.** Completar aquí cuando esté publicado y verificado. No se ha creado ni publicado un repositorio remoto desde este chat.

No subir env/, media/, archivos con contraseñas ni la base SQLite local. Respaldar PostgreSQL y las firmas privadas de media/ por separado: no son archivos estáticos. Las firmas se entregan mediante vistas autenticadas, nunca mediante una ruta pública /media/.

## Flujo iniciado por el contratista

SOLICITUDES_ARRIENDO.md documenta solicitud firmada desde el catálogo, revisión del personal, reserva por una hora y entrega física vinculada (migración 0014). El menú Mis solicitudes/Revisar arriendos es el acceso principal. Se preparó la tarea vencer_reservas en el servicio periódico de despliegue; aún no está instalada en EC2. Las pruebas nuevas amplían la cifra de validación indicada en etapas anteriores.


Destino de uso: las nuevas solicitudes exigen dirección y comuna en vez de obra. La migración 0015 conserva los antecedentes anteriores y sus firmas. Ver DESTINOS_ARRIENDO.md. Verificación actual: 312 pruebas aprobadas en SQLite temporal; PostgreSQL requiere comprobación local.

## Verificación PostgreSQL

Después de corregir el cierre de respuestas streaming en dos pruebas, la suite completa de 320 pruebas pasó en una instancia temporal PostgreSQL 18 (base/usuario independientes). La base real buildcorp no fue modificada. Ejecutar probar_postgresql.ps1 permite confirmar el entorno local; la salida completa se guarda en pruebas-postgresql.log, excluido del repositorio por .gitignore.
