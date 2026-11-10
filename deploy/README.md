# Preparar EC2 (sin ejecutar desde el agente)

Archivos para una única instancia Linux con PostgreSQL y aplicación. No se ha accedido a AWS ni creado recursos. Sustituir dominio/IP y credenciales de ejemplo antes de instalar.

## Preparación

1. Crear instancia EC2 de AWS Academy y permitir entrada al servidor web; limitar SSH a tu IP. PostgreSQL queda escuchando localmente, sin abrir 5432 a Internet.
2. Instalar Python compatible con requirements.txt, venv, PostgreSQL y Nginx. Crear usuario de sistema buildcorp con grupo www-data y directorio /srv/buildcorp. Copiar allí el proyecto sin env de Windows, credenciales ni bases locales.
3. Crear usuario PostgreSQL buildcorp y base buildcorp con ese propietario; usar una contraseña propia. La aplicación no necesita el superusuario postgres. Para pruebas, conceder temporalmente CREATEDB a una cuenta de pruebas o ejecutarlas con una cuenta aparte.
4. Como propietario del proyecto, crear el entorno Linux e instalar requirements-production.txt. El requisito gunicorn es adicional al entorno local y todavía no se instaló/verificó en EC2.

```bash
cd /srv/buildcorp
python3 -m venv env
env/bin/python -m pip install -r requirements-production.txt
```

## Variables y permisos

Copiar buildcorp.env.example a /etc/buildcorp.env; propietario root y permisos 600. Reemplazar todos los valores REEMPLAZAR. Generar una clave Django nueva, no reutilizar la clave local. Establecer DJANGO_ALLOWED_HOSTS con IP/DNS concretos separados por coma.

El ejemplo activa HTTPS por defecto. nginx.conf es una plantilla HTTP inicial: antes de usar credenciales reales, configurar TLS en Nginx y DJANGO_CSRF_TRUSTED_ORIGINS con el origen https correcto. Si la demostración inicial usa exclusivamente HTTP por IP, configurar explícitamente DJANGO_HTTPS=false y el origen http correspondiente; las cookies y credenciales no tendrán protección de transporte hasta habilitar TLS. No establecer HTTPS=true delante de un servidor exclusivamente HTTP, porque provocaría redirección a un puerto TLS inexistente.

El usuario buildcorp debe poder leer el proyecto y escribir media/. Nginx solo necesita leer staticfiles/ y llegar al socket por el grupo www-data. No dar acceso web a media/: contiene firmas privadas. Conservar la regla /media/ que responde 404.

## Migraciones y estáticos

Ejecutar con usuario buildcorp y las variables de /etc/buildcorp.env. Desde un shell de administración, systemd puede cargar ese archivo sin hacerlo público:

```bash
sudo systemd-run --wait --pipe --collect \
  -p User=buildcorp -p Group=www-data \
  -p WorkingDirectory=/srv/buildcorp \
  -p EnvironmentFile=/etc/buildcorp.env \
  /srv/buildcorp/env/bin/python manage.py migrate

sudo systemd-run --wait --pipe --collect \
  -p User=buildcorp -p Group=www-data \
  -p WorkingDirectory=/srv/buildcorp \
  -p EnvironmentFile=/etc/buildcorp.env \
  /srv/buildcorp/env/bin/python manage.py collectstatic --noinput
```

Crear el primer superusuario mediante createsuperuser en una terminal interactiva con las mismas variables; no guardar la contraseña en scripts. Respaldar la base antes de migrar un despliegue que ya tenga datos.

## Servicios y tarea periódica

Instalar los tres archivos buildcorp*.service/timer en /etc/systemd/system/. Instalar la configuración Nginx después de reemplazar el host y preparar TLS si corresponde. Revisar con nginx -t antes de recargar.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now buildcorp.service
sudo systemctl enable --now buildcorp-atrasos.timer
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl list-timers buildcorp-atrasos.timer
sudo journalctl -u buildcorp.service -n 50
sudo journalctl -u buildcorp-atrasos.service -n 50
```

El timer ejecuta revisar_atrasos cada cinco minutos después del arranque. No aplica cobros. systemd no inicia otra ejecución de la misma unidad mientras sigue activa; los servicios de negocio usan además transacciones por empresa.

## Comprobación final

- Ejecutar pruebas contra PostgreSQL de la instancia con base de pruebas separada.
- Ejecutar manage.py check --deploy con settings_production y resolver las advertencias según el HTTPS instalado. HSTS no está preactivado: configurarlo solo cuando TLS sea permanente y esté verificado.
- Verificar desde fuera: login, registro/aprobación, entrega, firma, uso, devolución, mantenimiento y bloqueos. Consultar también /api/v1/ con sesión habilitada.
- Confirmar que /media/ no expone firmas y que cuentas sin permisos no acceden a datos administrativos.
- Anotar IP pública/DNS real en README.md y subir el repositorio con acceso al docente.
- Respaldar PostgreSQL y media/; restaurar ambos juntos para conservar las firmas.

Estos pasos quedan pendientes hasta disponer de instancia y acceso. La presencia de archivos de despliegue no significa que el proyecto esté publicado.

## Reservas de solicitudes

La unidad buildcorp-atrasos.service ahora ejecuta también manage.py vencer_reservas. Al actualizar un despliegue, copiar la unidad actualizada, aplicar migraciones y ejecutar systemctl daemon-reload. Mantener el timer habilitado. No se activó remotamente desde el agente.
