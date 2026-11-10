from decimal import Decimal
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from datetime import timedelta


from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone


def vencimiento_solicitud():
    return timezone.now() + timedelta(hours=1)


class Empresa(models.Model):
    bloqueada_por_atraso = models.BooleanField(default=False)

    @property
    def tiene_bloqueo(self):
        return self.bloqueada or self.bloqueada_por_atraso

    class Meta:
        permissions = [("gestionar_bloqueos_empresa", "Puede aplicar y retirar bloqueos manuales de empresas")]
    rut = models.CharField(max_length=12, unique=True)
    razon_social = models.CharField(max_length=150)
    bloqueada = models.BooleanField(default=False)
    motivo_bloqueo = models.TextField(blank=True)

    def __str__(self):
        return f"{self.razon_social} ({self.rut})"


class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        ADMINISTRADOR = "ADMINISTRADOR", "Administrador"
        BODEGUERO = "BODEGUERO", "Bodeguero"
        CONTRATISTA = "CONTRATISTA", "Contratista"

    suspendida = models.BooleanField(default=False)
    rut = models.CharField(max_length=12, unique=True)
    rol = models.CharField(
        max_length=20, choices=Rol.choices, default=Rol.CONTRATISTA,
    )
    # Los usuarios internos pueden no pertenecer a una empresa contratista.
    empresa = models.ForeignKey(
        Empresa, on_delete=models.PROTECT, related_name="usuarios",
        null=True, blank=True,
    )

    class EstadoAprobacion(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    estado_aprobacion = models.CharField(
        max_length=12, choices=EstadoAprobacion.choices,
        default=EstadoAprobacion.PENDIENTE,
    )
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="cuentas_revisadas",
    )
    revisado_en = models.DateTimeField(null=True, blank=True)
    motivo_revision = models.TextField(blank=True)

    class Meta:
        permissions = [("aprobar_contratista", "Puede revisar cuentas de contratistas"), ("gestionar_usuarios", "Puede administrar cuentas y permisos desde el sistema")]

    # Permite que createsuperuser solicite el RUT además del correo.
    # El rol de negocio no concede por sí solo permisos de superusuario.
    REQUIRED_FIELDS = ["email", "rut"]

    def __str__(self):
        return self.get_full_name() or self.username


class Obra(models.Model):
    activa = models.BooleanField(default=True)

    class Meta:
        permissions = [
            ("desactivar_obra", "Puede desactivar obras"),
            ("reactivar_obra", "Puede reactivar obras"),
        ]
    nombre = models.CharField(max_length=120)
    direccion = models.CharField(max_length=250)

    def __str__(self):
        return self.nombre


class Bodega(models.Model):
    activa = models.BooleanField(default=True)

    class Meta:
        permissions = [
            ("desactivar_bodega", "Puede desactivar bodegas"),
            ("reactivar_bodega", "Puede reactivar bodegas"),
        ]
    nombre = models.CharField(max_length=100)
    direccion = models.CharField(max_length=250, verbose_name="Dirección")
    # Una bodega central tiene ubicación propia y no necesita una obra.
    obra = models.ForeignKey(
        Obra, on_delete=models.PROTECT, related_name="bodegas",
        null=True, blank=True,
    )

    def __str__(self):
        return self.nombre


class Maquinaria(models.Model):
    # NULL significa tarifa pendiente, nunca arriendo gratuito. No se
    # asignan precios ficticios a equipos registrados antes de la migración.
    precio_diario = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))], verbose_name="Precio diario de arriendo",
        help_text="En CLP, mayor que cero. Sin tarifa no podrá recibir nuevas solicitudes.")
    moneda = models.CharField(max_length=3, default="CLP", editable=False)

    class Estado(models.TextChoices):
        DISPONIBLE = "DISPONIBLE", "Disponible"
        EN_USO = "EN_USO", "En uso"
        MANTENIMIENTO = "MANTENIMIENTO", "Mantenimiento"
        BAJA = "BAJA", "Dada de baja"

    codigo = models.CharField(max_length=30, unique=True)
    nombre = models.CharField(max_length=120)
    marca = models.CharField(max_length=80, blank=True)
    modelo = models.CharField(max_length=80, blank=True)
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.DISPONIBLE,
    )
    bodega = models.ForeignKey(
        Bodega, on_delete=models.PROTECT, related_name="maquinarias",
    )
    # El acumulado incluye solo sesiones cerradas y nunca se reinicia.
    # La referencia de la última mantención permite contar ciclos de 250 h.
    tiempo_uso_acumulado = models.DurationField(default=timedelta)
    tiempo_uso_ultima_mantencion = models.DurationField(default=timedelta)
    intervalo_mantencion = models.DurationField(default=timedelta(hours=250))

    # Lectura y autor del alta: se conservan aunque aumenten las horas de uso.
    tiempo_uso_inicial = models.DurationField(null=True, blank=True)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="maquinarias_registradas",
    )
    registrado_en = models.DateTimeField(null=True, blank=True)
    revision_pendiente = models.BooleanField(default=True)
    ultima_mantencion_conocida = models.BooleanField(default=False)

    class Meta:
        permissions = [
            ("trasladar_maquinaria", "Puede trasladar maquinaria disponible"),
            ("dar_baja_maquinaria", "Puede dar de baja maquinaria disponible"),
            ("reactivar_maquinaria", "Puede reactivar maquinaria para revisión"),
        ]
        constraints = [
            models.UniqueConstraint(Lower("codigo"), name="codigo_maquinaria_sin_mayusculas"),
            models.CheckConstraint(condition=models.Q(precio_diario__isnull=True) | models.Q(precio_diario__gt=0), name="maquina_precio_positivo"),
            models.CheckConstraint(condition=models.Q(moneda="CLP"), name="maquina_moneda_clp"),
            models.CheckConstraint(condition=models.Q(tiempo_uso_acumulado__gte=timedelta()), name="uso_maquina_no_negativo"),
            models.CheckConstraint(condition=models.Q(tiempo_uso_ultima_mantencion__gte=timedelta()) & models.Q(tiempo_uso_ultima_mantencion__lte=models.F("tiempo_uso_acumulado")), name="lectura_mantencion_valida"),
            models.CheckConstraint(condition=models.Q(intervalo_mantencion__gt=timedelta()), name="intervalo_mantencion_positivo"),
            models.CheckConstraint(condition=models.Q(tiempo_uso_inicial__isnull=True) | (models.Q(tiempo_uso_inicial__gte=timedelta()) & models.Q(tiempo_uso_inicial__lte=models.F("tiempo_uso_acumulado"))), name="lectura_inicial_valida"),
        ]

    @property
    def reserva_vigente(self):
        return self.solicitudes_arriendo.filter(estado="APROBADA", reserva_hasta__gt=timezone.now()).exists()

    @property
    def tiempo_uso_total(self):
        # Se calcula desde la fecha del servidor: cerrar el navegador no
        # detiene el contador. Consultar esta propiedad no escribe en la BD.
        sesion = SesionUso.objects.filter(
            arriendo__maquinaria=self, fin__isnull=True,
        ).first()
        tiempo_actual = (
            timezone.now() - sesion.inicio if sesion else timedelta()
        )
        return self.tiempo_uso_acumulado + tiempo_actual

    @property
    def requiere_mantencion_por_uso(self):
        # Es un aviso calculado; no cambia el estado ni da por hecha la
        # mantención. Su programación se implementará en el flujo de trabajo.
        uso_desde_mantencion = (
            self.tiempo_uso_total - self.tiempo_uso_ultima_mantencion
        )
        return uso_desde_mantencion >= self.intervalo_mantencion

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


    @property
    def requiere_mantencion_por_fecha(self):
        return self.mantenimientos.filter(finalizado_en__isnull=True, fecha_programada__lte=timezone.localdate()).exists()

    @property
    def bloqueada_por_mantencion(self):
        # Se evalúa al consultar y operar. No depende de que un proceso
        # periódico cambie un estado cuando llega la fecha programada.
        return (self.revision_pendiente or self.requiere_mantencion_por_uso
                or self.requiere_mantencion_por_fecha
                or self.mantenimientos.filter(iniciado_en__isnull=False, finalizado_en__isnull=True).exists())


class TerminosCondiciones(models.Model):
    # Cada publicación debe crear una versión nueva para conservar lo aceptado.
    version = models.CharField(max_length=20, unique=True)
    contenido = models.TextField()
    publicado_en = models.DateTimeField(default=timezone.now)
    publicado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="condiciones_publicadas",
    )

    class Meta:
        permissions = [
            ("publicar_terminos", "Puede publicar versiones de condiciones"),
            ("consultar_firmas", "Puede consultar comprobantes de otros usuarios"),
        ]

    def __str__(self):
        return f"Términos versión {self.version}"


class AceptacionTerminos(models.Model):
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="aceptaciones",
    )
    terminos = models.ForeignKey(
        TerminosCondiciones, on_delete=models.PROTECT,
    )
    aceptado_en = models.DateTimeField(default=timezone.now)
    # La BD guarda la ruta; el archivo se guarda en el almacenamiento de medios.
    # Las vistas deberán validar el archivo y restringir quién puede leerlo.
    firma = models.FileField(upload_to="firmas/perfiles/")
    firmado_en = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(firmado_en__gte=models.F("aceptado_en")),
                name="firma_despues_de_aceptar",
            ),
        ]


class Arriendo(models.Model):
    # Se conserva el destino de cada documento. Los registros históricos
    # pueden estar incompletos; las altas se validan en formularios/servicios.
    direccion_uso = models.CharField(max_length=255, blank=True, default="", verbose_name="Dirección de uso de la maquinaria")
    comuna_uso = models.CharField(max_length=100, blank=True, default="", verbose_name="Comuna")
    indicaciones_acceso = models.TextField(blank=True, default="", verbose_name="Indicaciones de acceso")
    destino_legacy = models.BooleanField(default=False, editable=False)

    bodega_origen = models.ForeignKey(Bodega, on_delete=models.PROTECT, null=True, blank=True, related_name="arriendos_entregados")
    bodega_recepcion = models.ForeignKey(Bodega, on_delete=models.PROTECT, null=True, blank=True, related_name="arriendos_recibidos")
    recibido_en = models.DateTimeField(null=True, blank=True)
    maquinaria = models.ForeignKey(
        Maquinaria, on_delete=models.PROTECT, related_name="arriendos",
    )
    empresa = models.ForeignKey(
        Empresa, on_delete=models.PROTECT, related_name="arriendos",
    )
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="arriendos",
    )
    obra_destino = models.ForeignKey(Obra, on_delete=models.PROTECT, null=True, blank=True)
    aceptacion = models.ForeignKey(
        AceptacionTerminos, on_delete=models.PROTECT,
    )
    entregado_en = models.DateTimeField(default=timezone.now)
    devolucion_prevista = models.DateTimeField()
    devuelto_en = models.DateTimeField(null=True, blank=True)
    # Se conserva la tarifa acordada aunque el precio del catálogo cambie.
    tarifa_diaria = models.DecimalField(max_digits=12, decimal_places=2)
    firma_entrega = models.FileField(upload_to="firmas/entregas/")
    firma_devolucion = models.FileField(
        upload_to="firmas/devoluciones/", blank=True,
    )
    observaciones = models.TextField(blank=True)

    @property
    def esta_atrasado(self):
        # El tiempo por sí solo no dispara save(): el bloqueo automático
        # necesitará una tarea periódica y una comprobación al arrendar.
        return (
            self.devuelto_en is None and self.recibido_en is None
            and timezone.now() > self.devolucion_prevista
        )

    class Meta:
        permissions = [("gestionar_arriendos", "Puede preparar y cancelar entregas y recepciones"),]
        # Estas reglas se aplican en la propia BD, incluso si se omiten
        # los formularios. Las relaciones entre entidades se validarán
        # también en el proceso de entrega (empresa, firma y disponibilidad).
        constraints = [
            models.UniqueConstraint(
                fields=["maquinaria"],
                condition=models.Q(devuelto_en__isnull=True),
                name="un_arriendo_abierto_por_maquina",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    devolucion_prevista__gt=models.F("entregado_en"),
                ),
                name="plazo_posterior_a_entrega",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(devuelto_en__isnull=True)
                    | models.Q(devuelto_en__gte=models.F("entregado_en"))
                ),
                name="devolucion_posterior_a_entrega",
            ),
            models.CheckConstraint(
                condition=models.Q(tarifa_diaria__gte=0),
                name="tarifa_no_negativa",
            ),
        ]


class SesionUso(models.Model):
    iniciada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="sesiones_iniciadas")
    cerrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="sesiones_cerradas")
    motivo_cierre = models.CharField(max_length=200, blank=True)
    arriendo = models.ForeignKey(
        Arriendo, on_delete=models.PROTECT, related_name="sesiones_uso",
    )
    inicio = models.DateTimeField(default=timezone.now)
    fin = models.DateTimeField(null=True, blank=True)

    # Los servicios de uso y recepción suman la duración de cada sesión
    # al acumulado una sola vez, dentro de una transacción. Un save() aislado
    # de este modelo no actualiza el contador de la máquina.
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["arriendo"], condition=models.Q(fin__isnull=True),
                name="una_sesion_abierta_por_arriendo",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(fin__isnull=True)
                    | models.Q(fin__gte=models.F("inicio"))
                ),
                name="fin_uso_posterior_a_inicio",
            ),
        ]


class Mantenimiento(models.Model):
    apta_para_servicio = models.BooleanField(null=True, blank=True)
    programado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="mantenciones_programadas",
    )
    finalizado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="mantenciones_finalizadas",
    )

    class Meta:
        permissions = [
            ("iniciar_mantenimiento", "Puede iniciar mantenciones"),
            ("finalizar_mantenimiento", "Puede finalizar mantenciones"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["maquinaria"], condition=models.Q(iniciado_en__isnull=False, finalizado_en__isnull=True), name="una_mantencion_en_curso"),
            models.CheckConstraint(condition=models.Q(finalizado_en__isnull=True) | (models.Q(iniciado_en__isnull=False) & models.Q(finalizado_en__gte=models.F("iniciado_en"))), name="fechas_mantencion_validas"),
            models.CheckConstraint(condition=models.Q(lectura_uso__isnull=True) | models.Q(lectura_uso__gte=timedelta()), name="lectura_mantencion_no_negativa"),
        ]

    @property
    def estado(self):
        if self.finalizado_en is not None:
            return "Finalizada"
        return "En curso" if self.iniciado_en is not None else "Pendiente"

    @property
    def vencida(self):
        return self.finalizado_en is None and self.fecha_programada < timezone.localdate()

    maquinaria = models.ForeignKey(
        Maquinaria, on_delete=models.PROTECT, related_name="mantenimientos",
    )
    fecha_programada = models.DateField()
    iniciado_en = models.DateTimeField(null=True, blank=True)
    finalizado_en = models.DateTimeField(null=True, blank=True)
    # Fotografía del contador de uso al realizar la mantención.
    lectura_uso = models.DurationField(null=True, blank=True)
    descripcion = models.TextField()
    resultado = models.TextField(blank=True)
    responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="mantenimientos",
    )


class MovimientoMaquinaria(models.Model):
    class Tipo(models.TextChoices):
        ALERTA_USO = "ALERTA_USO", "Intervalo de mantención cumplido"
        ENTREGA = "ENTREGA", "Entrega de arriendo"
        RECEPCION = "RECEPCION", "Recepción pendiente de firma"
        DEVOLUCION = "DEVOLUCION", "Devolución confirmada"
        PROGRAMACION_MANTENCION = "PROG_MANT", "Programación de mantención"
        INICIO_MANTENCION = "INICIO_MANT", "Inicio de mantención"
        FIN_MANTENCION = "FIN_MANT", "Finalización de mantención"
        ANTERIOR = "ANTERIOR", "Registro anterior"
        ALTA = "ALTA", "Registro inicial"
        EDICION = "EDICION", "Edición de datos"
        TRASLADO = "TRASLADO", "Traslado"
        BAJA = "BAJA", "Baja"
        REACTIVACION = "REACTIVACION", "Reactivación"

    tipo = models.CharField(max_length=15, choices=Tipo.choices, default=Tipo.ANTERIOR)
    maquinaria = models.ForeignKey(
        Maquinaria, on_delete=models.PROTECT, related_name="movimientos",
    )
    origen = models.ForeignKey(
        Bodega, on_delete=models.PROTECT, related_name="movimientos_salida",
        null=True, blank=True,
    )
    destino = models.ForeignKey(
        Bodega, on_delete=models.PROTECT, related_name="movimientos_entrada",
    )
    estado_anterior = models.CharField(
        max_length=20, choices=Maquinaria.Estado.choices,
    )
    estado_nuevo = models.CharField(
        max_length=20, choices=Maquinaria.Estado.choices,
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
    )
    fecha = models.DateTimeField(default=timezone.now)
    motivo = models.TextField()




class HistorialSolicitud(models.Model):
    class Tipo(models.TextChoices):
        APROBACION = "APROBACION", "Aprobación"
        RECHAZO = "RECHAZO", "Rechazo"
        REENVIO = "REENVIO", "Reenvío"

    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="historial_solicitud",
    )
    tipo = models.CharField(max_length=12, choices=Tipo.choices)
    motivo = models.TextField(blank=True)
    fecha = models.DateTimeField(default=timezone.now)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="eventos_solicitud_registrados",
    )
    # Conserva la asociación empresarial de ese evento aunque se corrija
    # la empresa del usuario en un reenvío posterior.
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-fecha", "-pk"]







class HistorialUbicacion(models.Model):
    class Accion(models.TextChoices):
        DESACTIVACION = "DESACTIVACION", "Desactivación"
        REACTIVACION = "REACTIVACION", "Reactivación"

    obra = models.ForeignKey(
        Obra, on_delete=models.PROTECT, null=True, blank=True,
        related_name="historial_actividad",
    )
    bodega = models.ForeignKey(
        Bodega, on_delete=models.PROTECT, null=True, blank=True,
        related_name="historial_actividad",
    )
    accion = models.CharField(max_length=15, choices=Accion.choices)
    motivo = models.TextField()
    fecha = models.DateTimeField(default=timezone.now)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        ordering = ["-fecha", "-pk"]
        constraints = [
            # Cada evento pertenece a una obra o a una bodega, nunca a ambas.
            models.CheckConstraint(
                condition=(models.Q(obra__isnull=False, bodega__isnull=True)
                           | models.Q(obra__isnull=True, bodega__isnull=False)),
                name="historial_una_ubicacion",
            ),
        ]



class SolicitudEntrega(models.Model):
    # Se conserva el destino de cada documento. Los registros históricos
    # pueden estar incompletos; las altas se validan en formularios/servicios.
    direccion_uso = models.CharField(max_length=255, blank=True, default="", verbose_name="Dirección de uso de la maquinaria")
    comuna_uso = models.CharField(max_length=100, blank=True, default="", verbose_name="Comuna")
    indicaciones_acceso = models.TextField(blank=True, default="", verbose_name="Indicaciones de acceso")
    destino_legacy = models.BooleanField(default=False, editable=False)

    solicitud_arriendo = models.OneToOneField("SolicitudArriendo", on_delete=models.PROTECT,
        null=True, blank=True, related_name="solicitud_entrega")
    maquinaria = models.ForeignKey(Maquinaria, on_delete=models.PROTECT)
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregas_por_confirmar")
    obra_destino = models.ForeignKey(Obra, on_delete=models.PROTECT, null=True, blank=True)
    terminos = models.ForeignKey(TerminosCondiciones, on_delete=models.PROTECT)
    devolucion_prevista = models.DateTimeField()
    tarifa_diaria = models.DecimalField(max_digits=12, decimal_places=2)
    observaciones = models.TextField(blank=True)
    preparada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="entregas_preparadas")
    creada_en = models.DateTimeField(default=timezone.now)
    vence_en = models.DateTimeField(default=vencimiento_solicitud)
    cancelada_en = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="entregas_canceladas")
    motivo_cancelacion = models.TextField(blank=True)
    arriendo = models.OneToOneField(Arriendo, on_delete=models.PROTECT, null=True, blank=True, related_name="solicitud_entrega")

    @property
    def estado(self):
        if self.arriendo_id:
            return "Confirmada"
        if self.cancelada_en:
            return "Cancelada"
        return "Vencida" if self.vence_en <= timezone.now() else "Pendiente de firma"

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(tarifa_diaria__gte=0), name="solicitud_tarifa_no_negativa")]


class SolicitudDevolucion(models.Model):
    arriendo = models.ForeignKey(Arriendo, on_delete=models.PROTECT, related_name="recepciones")
    bodega = models.ForeignKey(Bodega, on_delete=models.PROTECT)
    observaciones = models.TextField()
    requiere_revision = models.BooleanField(default=False)
    preparada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="recepciones_preparadas")
    creada_en = models.DateTimeField(default=timezone.now)
    vence_en = models.DateTimeField(default=vencimiento_solicitud)
    cancelada_en = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="recepciones_canceladas")
    motivo_cancelacion = models.TextField(blank=True)
    confirmada_en = models.DateTimeField(null=True, blank=True)

    @property
    def estado(self):
        if self.confirmada_en:
            return "Confirmada"
        if self.cancelada_en:
            return "Cancelada"
        return "Vencida" if self.vence_en <= timezone.now() else "Pendiente de firma"

    class Meta:
        constraints = [models.UniqueConstraint(fields=["arriendo"], condition=models.Q(cancelada_en__isnull=True, confirmada_en__isnull=True), name="una_recepcion_pendiente_por_arriendo")]




class HistorialBloqueoEmpresa(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="historial_bloqueos")
    origen = models.CharField(max_length=10, choices=[("AUTOMATICO", "Automático por atraso"), ("MANUAL", "Manual")])
    accion = models.CharField(max_length=12, choices=[("BLOQUEO", "Bloqueo"), ("DESBLOQUEO", "Desbloqueo")])
    motivo = models.TextField()
    fecha = models.DateTimeField(default=timezone.now)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["-fecha", "-pk"]
        constraints = [models.CheckConstraint(
            condition=(models.Q(origen="AUTOMATICO", responsable__isnull=True)
                       | models.Q(origen="MANUAL", responsable__isnull=False)),
            name="autor_bloqueo_segun_origen",
        )]


class ControlAdministracion(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(id=1), name="control_administracion_unico")]


class HistorialAdministracionUsuario(models.Model):
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="historial_administracion")
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cambios_usuarios_realizados")
    accion = models.CharField(max_length=25)
    motivo = models.TextField()
    fecha = models.DateTimeField(default=timezone.now)
    datos_anteriores = models.JSONField(default=dict)
    datos_nuevos = models.JSONField(default=dict)

    class Meta:
        ordering = ["-fecha", "-pk"]


class SolicitudArriendo(models.Model):
    # Se conserva el destino de cada documento. Los registros históricos
    # pueden estar incompletos; las altas se validan en formularios/servicios.
    direccion_uso = models.CharField(max_length=255, blank=True, default="", verbose_name="Dirección de uso de la maquinaria")
    comuna_uso = models.CharField(max_length=100, blank=True, default="", verbose_name="Comuna")
    indicaciones_acceso = models.TextField(blank=True, default="", verbose_name="Indicaciones de acceso")
    destino_legacy = models.BooleanField(default=False, editable=False)

    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente de revisión"
        APROBADA = "APROBADA", "Aprobada, pendiente de entrega"
        RECHAZADA = "RECHAZADA", "Rechazada"
        CANCELADA = "CANCELADA", "Cancelada"
        VENCIDA = "VENCIDA", "Reserva vencida"
        ENTREGADA = "ENTREGADA", "Entregada"

    maquinaria = models.ForeignKey(Maquinaria, on_delete=models.PROTECT, related_name="solicitudes_arriendo")
    empresa = models.ForeignKey(Empresa, on_delete=models.PROTECT, related_name="solicitudes_arriendo")
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitudes_arriendo")
    obra_destino = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="solicitudes_arriendo", null=True, blank=True)
    creada_en = models.DateTimeField(default=timezone.now)
    devolucion_prevista = models.DateTimeField()
    observaciones = models.TextField(blank=True)
    # Estos datos son una fotografía de lo firmado, no referencias a la
    # tarifa actual. Los servicios copiarán el precio desde el catálogo.
    precio_diario_acordado = models.DecimalField(max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))])
    moneda = models.CharField(max_length=3, default="CLP", editable=False)
    terminos = models.ForeignKey(TerminosCondiciones, on_delete=models.PROTECT, related_name="solicitudes_arriendo")
    aceptado_en = models.DateTimeField()
    firmado_en = models.DateTimeField()
    firma_solicitud = models.FileField(upload_to="firmas/solicitudes_arriendo/")
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    revisada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="solicitudes_arriendo_revisadas")
    revisada_en = models.DateTimeField(null=True, blank=True)
    motivo_revision = models.TextField(blank=True)
    reserva_hasta = models.DateTimeField(null=True, blank=True)
    cancelada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="solicitudes_arriendo_canceladas")
    cancelada_en = models.DateTimeField(null=True, blank=True)
    motivo_cancelacion = models.TextField(blank=True)
    arriendo = models.OneToOneField(Arriendo, on_delete=models.PROTECT, null=True, blank=True, related_name="solicitud_origen")

    class Meta:
        ordering = ["-creada_en", "-pk"]
        permissions = [("revisar_solicitud_arriendo", "Puede aprobar o rechazar solicitudes de arriendo")]
        constraints = [
            models.CheckConstraint(condition=models.Q(precio_diario_acordado__gt=0), name="sol_arr_precio_positivo"),
            models.CheckConstraint(condition=models.Q(moneda="CLP"), name="sol_arr_moneda_clp"),
            models.CheckConstraint(condition=models.Q(devolucion_prevista__gt=models.F("creada_en")), name="sol_arr_devolucion_futura"),
            models.CheckConstraint(condition=models.Q(firmado_en__gte=models.F("aceptado_en")), name="sol_arr_firma_tras_aceptacion"),
            models.CheckConstraint(condition=~models.Q(firma_solicitud=""), name="sol_arr_firma_obligatoria"),
            models.UniqueConstraint(fields=["maquinaria"], condition=models.Q(estado="APROBADA"), name="sol_arr_una_reserva_por_maquina"),
            models.UniqueConstraint(fields=["maquinaria", "solicitante"], condition=models.Q(estado__in=["PENDIENTE", "APROBADA"]), name="sol_arr_una_activa_por_persona"),
            models.CheckConstraint(condition=~models.Q(estado="APROBADA") | models.Q(reserva_hasta__isnull=False,
                revisada_por__isnull=False, revisada_en__isnull=False), name="sol_arr_aprobacion_con_reserva"),
            models.CheckConstraint(condition=models.Q(reserva_hasta__isnull=True) | models.Q(reserva_hasta__gt=models.F("revisada_en")), name="sol_arr_reserva_posterior"),
            models.CheckConstraint(condition=(models.Q(estado="ENTREGADA", arriendo__isnull=False) |
                (~models.Q(estado="ENTREGADA") & models.Q(arriendo__isnull=True))), name="sol_arr_entrega_con_arriendo"),
            models.CheckConstraint(condition=~models.Q(estado="RECHAZADA") | (models.Q(revisada_por__isnull=False,
                revisada_en__isnull=False) & ~models.Q(motivo_revision="")), name="sol_arr_rechazo_con_motivo"),
            models.CheckConstraint(condition=~models.Q(estado="CANCELADA") | (models.Q(cancelada_por__isnull=False,
                cancelada_en__isnull=False) & ~models.Q(motivo_cancelacion="")), name="sol_arr_cancelacion_con_motivo"),
            models.CheckConstraint(condition=models.Q(estado__in=["PENDIENTE", "APROBADA", "RECHAZADA", "CANCELADA", "VENCIDA", "ENTREGADA"]), name="sol_arr_estado_valido"),
        ]

    def clean(self):
        super().clean()
        errores = {}
        if self.solicitante_id:
            usuario = self.solicitante
            if usuario.empresa_id != self.empresa_id:
                errores["solicitante"] = "El solicitante debe pertenecer a la empresa indicada."
            if usuario.rol != "CONTRATISTA" or usuario.is_staff or usuario.is_superuser:
                errores["solicitante"] = "La solicitud debe pertenecer a un contratista."
        if self._state.adding and self.maquinaria_id and self.maquinaria.precio_diario is None:
            errores["maquinaria"] = "La máquina todavía no tiene tarifa de arriendo."
        if self.estado == self.Estado.RECHAZADA and not self.motivo_revision.strip():
            errores["motivo_revision"] = "Indica el motivo del rechazo."
        if self.estado == self.Estado.CANCELADA and not self.motivo_cancelacion.strip():
            errores["motivo_cancelacion"] = "Indica el motivo de la cancelación."
        if self.arriendo_id and (self.arriendo.maquinaria_id != self.maquinaria_id or
                self.arriendo.responsable_id != self.solicitante_id or self.arriendo.empresa_id != self.empresa_id):
            errores["arriendo"] = "El arriendo debe corresponder al mismo equipo, solicitante y empresa."
        if errores:
            raise ValidationError(errores)

    @property
    def estado_actual(self):
        # La lectura no modifica estados; el comando persiste el vencimiento.
        if self.estado == "APROBADA" and self.reserva_hasta and self.reserva_hasta <= timezone.now():
            return "VENCIDA"
        return self.estado

    def __str__(self):
        return f"Solicitud #{self.pk} · {self.maquinaria} · {self.get_estado_display()}"


class HistorialSolicitudArriendo(models.Model):
    solicitud = models.ForeignKey(SolicitudArriendo, on_delete=models.PROTECT, related_name="historial")
    estado_anterior = models.CharField(max_length=12, choices=SolicitudArriendo.Estado.choices, blank=True)
    estado_nuevo = models.CharField(max_length=12, choices=SolicitudArriendo.Estado.choices)
    fecha = models.DateTimeField(default=timezone.now)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="cambios_solicitudes_arriendo")
    motivo = models.TextField(blank=True)

    class Meta:
        ordering = ["-fecha", "-pk"]
