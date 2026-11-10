from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import (Empresa, Usuario, Obra, Bodega, Maquinaria, TerminosCondiciones,
                     SolicitudArriendo, HistorialSolicitudArriendo)


class ModelosSolicitudArriendoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(rut="77777777-7", razon_social="Empresa solicitudes")
        cls.usuario = Usuario.objects.create_user(username="solicitante_modelo", rut="11111111-1",
            empresa=cls.empresa, estado_aprobacion="APROBADO")
        cls.otro = Usuario.objects.create_user(username="otro_solicitante_modelo", rut="22222222-2",
            empresa=cls.empresa, estado_aprobacion="APROBADO")
        cls.admin = Usuario.objects.create_superuser(username="admin_solicitud_modelo", rut="33333333-3", password="Seguro!4820")
        cls.obra = Obra.objects.create(nombre="Obra", direccion="Direccion obra")
        cls.bodega = Bodega.objects.create(nombre="Central", direccion="Direccion central")
        cls.maquina = Maquinaria.objects.create(codigo="SOL-MOD-1", nombre="Equipo", bodega=cls.bodega,
            precio_diario=Decimal("25000"))
        cls.terminos = TerminosCondiciones.objects.create(version="SOL-MOD-1", contenido="Condiciones de solicitud")

    def solicitud(self, **cambios):
        ahora = timezone.now()
        datos = dict(maquinaria=self.maquina, empresa=self.empresa, solicitante=self.usuario,
            obra_destino=self.obra, creada_en=ahora, devolucion_prevista=ahora + timedelta(days=3),
            precio_diario_acordado=Decimal("25000"), terminos=self.terminos,
            aceptado_en=ahora, firmado_en=ahora, firma_solicitud="firmas/solicitudes_arriendo/prueba.png")
        datos.update(cambios)
        return SolicitudArriendo(**datos)

    def test_precio_maquinaria_positivo_o_pendiente_nunca_cero(self):
        for precio in (Decimal("0"), Decimal("-1")):
            maquina = Maquinaria.objects.get(pk=self.maquina.pk)
            maquina.precio_diario = precio
            with self.assertRaises(ValidationError):
                maquina.full_clean()
            with self.assertRaises(IntegrityError), transaction.atomic():
                Maquinaria.objects.filter(pk=maquina.pk).update(precio_diario=precio)
        Maquinaria.objects.filter(pk=self.maquina.pk).update(precio_diario=None)
        self.maquina.refresh_from_db()
        self.assertIsNone(self.maquina.precio_diario)

    def test_solicitud_sin_tarifa_o_precio_cero_no_es_valida(self):
        for precio in (Decimal("0"), Decimal("-1")):
            solicitud = self.solicitud(precio_diario_acordado=precio)
            with self.assertRaises(ValidationError):
                solicitud.full_clean()
            with self.assertRaises(IntegrityError), transaction.atomic():
                solicitud.save()
        self.maquina.precio_diario = None
        self.maquina.save(update_fields=["precio_diario"])
        with self.assertRaisesMessage(ValidationError, "todavía no tiene tarifa"):
            self.solicitud().full_clean()

    def test_conserva_precio_firmado_y_relaciones_al_cambiar_catalogo(self):
        solicitud = self.solicitud()
        solicitud.full_clean()
        solicitud.save()
        Maquinaria.objects.filter(pk=self.maquina.pk).update(precio_diario=Decimal("30000"))
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.precio_diario_acordado, Decimal("25000"))
        self.assertEqual(solicitud.estado, "PENDIENTE")
        self.assertIsNone(solicitud.arriendo_id)

    def test_una_solicitud_activa_por_persona_y_equipo(self):
        self.solicitud().save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.solicitud().save()
        self.solicitud(solicitante=self.otro).save()
        self.assertEqual(SolicitudArriendo.objects.count(), 2)

    def test_una_reserva_aprobada_por_maquina(self):
        ahora = timezone.now()
        datos = dict(estado="APROBADA", revisada_por=self.admin, revisada_en=ahora,
                     reserva_hasta=ahora + timedelta(hours=1))
        self.solicitud(**datos).save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.solicitud(solicitante=self.otro, **datos).save()

    def test_aprobacion_exige_revision_y_reserva(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.solicitud(estado="APROBADA").save()
        ahora = timezone.now()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.solicitud(estado="APROBADA", revisada_por=self.admin, revisada_en=ahora,
                reserva_hasta=ahora - timedelta(minutes=1)).save()

    def test_fechas_firma_y_estado_invalido_rechazados_por_bd(self):
        ahora = timezone.now()
        for cambios in ({"devolucion_prevista": ahora - timedelta(days=1)},
                        {"firmado_en": ahora - timedelta(days=1)}, {"firma_solicitud": ""},
                        {"estado": "ENTREGADA"}, {"estado": "INVENTADO"}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.solicitud(**cambios).save()

    def test_rechazo_y_cancelacion_exigen_autor_fecha_motivo(self):
        for estado in ("RECHAZADA", "CANCELADA"):
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.solicitud(estado=estado).save()
        solicitud = self.solicitud(estado="RECHAZADA", revisada_por=self.admin,
            revisada_en=timezone.now(), motivo_revision=" ")
        with self.assertRaises(ValidationError):
            solicitud.full_clean()

    def test_solicitante_debe_ser_contratista_de_la_empresa(self):
        with self.assertRaises(ValidationError):
            self.solicitud(solicitante=self.admin).full_clean()
        otra_empresa = Empresa.objects.create(rut="88888888-8", razon_social="Otra empresa")
        with self.assertRaises(ValidationError):
            self.solicitud(empresa=otra_empresa).full_clean()

    def test_historial_admite_vencimiento_automatico_sin_autor(self):
        solicitud = self.solicitud(estado="VENCIDA")
        solicitud.save()
        evento = HistorialSolicitudArriendo.objects.create(solicitud=solicitud,
            estado_anterior="APROBADA", estado_nuevo="VENCIDA", motivo="Reserva vencida")
        self.assertIsNone(evento.responsable_id)
        self.assertEqual(solicitud.historial.get().estado_nuevo, "VENCIDA")
