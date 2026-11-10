from datetime import timedelta
from decimal import Decimal
from io import BytesIO, StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.storage import default_storage
from django.db import IntegrityError
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image, ImageDraw
from rest_framework.test import APIClient

from .models import (Usuario, Empresa, Obra, Bodega, Maquinaria, AceptacionTerminos,
                     TerminosCondiciones, SolicitudArriendo, Arriendo, Mantenimiento)
from .reservas import vencer_reservas


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class FlujoSolicitudesArriendoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_peticion", rut="11111111-1", password="Seguro!4820")
        cls.empresa = Empresa.objects.create(rut="77777777-7", razon_social="Empresa peticiones")
        cls.usuario = Usuario.objects.create_user(username="contratista_peticion", rut="22222222-2", empresa=cls.empresa,
            estado_aprobacion="APROBADO", password="Seguro!4820")
        cls.otro = Usuario.objects.create_user(username="otro_peticion", rut="33333333-3", empresa=cls.empresa,
            estado_aprobacion="APROBADO")
        cls.obra = Obra.objects.create(nombre="Obra peticion", direccion="Direccion obra")
        cls.bodega = Bodega.objects.create(nombre="Central", direccion="Direccion central")
        cls.destino = Bodega.objects.create(nombre="Sucursal", direccion="Direccion sucursal")
        cls.maquina = Maquinaria.objects.create(codigo="PET-001", nombre="Equipo", bodega=cls.bodega,
            precio_diario=Decimal("25000"), revision_pendiente=False, ultima_mantencion_conocida=True)
        cls.terminos = TerminosCondiciones.objects.create(version="PET-1", contenido="Condiciones de peticion")
        ahora = timezone.now()
        for usuario in (cls.usuario, cls.otro):
            AceptacionTerminos.objects.create(usuario=usuario, terminos=cls.terminos,
                aceptado_en=ahora, firmado_en=ahora, firma="perfil.png")

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.usuario)

    def firma(self):
        imagen = Image.new("RGB", (900, 300), "white")
        ImageDraw.Draw(imagen).line([(30, 200), (150, 40), (250, 240), (700, 100)], fill="black", width=5)
        salida = BytesIO()
        imagen.save(salida, "PNG")
        return SimpleUploadedFile("firma.png", salida.getvalue(), content_type="image/png")

    def datos(self):
        return {"maquinaria": self.maquina.pk, "direccion_uso": "Calle Destino 123", "comuna_uso": "Santiago", "indicaciones_acceso": "Acceso por portón principal",
            "devolucion_prevista": (timezone.now() + timedelta(days=2)).isoformat(),
            "precio_visto": "25000.00", "version_id": self.terminos.pk, "acepto": "true",
            "confirmar": "true", "firma": self.firma(), "observaciones": "Accesorios solicitados"}

    def enviar(self, **cambios):
        datos = self.datos()
        datos.update(cambios)
        return self.api.post("/api/v1/solicitudes-arriendo/enviar/", datos, format="multipart")

    def nueva(self):
        respuesta = self.enviar()
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        return respuesta.data["id"]

    def accion(self, pk, accion, **datos):
        return self.api.post(f"/api/v1/solicitudes-arriendo/{pk}/{accion}/", datos, format="json")

    def aprobar(self, pk):
        self.api.force_login(self.admin)
        respuesta = self.accion(pk, "aprobar", motivo="Equipo y antecedentes revisados")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        return respuesta

    def test_flujo_firmado_aprobacion_entrega_conserva_precio_y_no_inicia_timer(self):
        pk = self.nueva()
        self.assertEqual(Arriendo.objects.count(), 0)
        self.aprobar(pk)
        Maquinaria.objects.filter(pk=self.maquina.pk).update(precio_diario=Decimal("30000"))
        entrega = self.accion(pk, "entregar", confirmar=True)
        self.assertEqual(entrega.status_code, 201, entrega.data)
        self.assertEqual(entrega.data["tarifa_diaria"], "25000.00")
        self.assertEqual(entrega.data["solicitud_arriendo"], pk)
        solicitud = SolicitudArriendo.objects.get(pk=pk)
        self.assertLessEqual(timezone.datetime.fromisoformat(entrega.data["vence_en"]), solicitud.reserva_hasta)
        self.assertEqual(Arriendo.objects.count(), 0)
        self.api.force_login(self.usuario)
        respuesta = self.api.post(f"/api/v1/entregas/{entrega.data['id']}/confirmar/",
            {"firma": self.firma(), "confirmar": "true"}, format="multipart")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "ENTREGADA")
        self.assertEqual(solicitud.arriendo_id, respuesta.data["id"])
        self.assertEqual(solicitud.arriendo.tarifa_diaria, Decimal("25000"))
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "EN_USO")
        self.assertFalse(solicitud.arriendo.sesiones_uso.exists())
        self.assertEqual(solicitud.historial.count(), 3)

    def test_otro_contratista_no_ve_solicitud_historial_o_firma(self):
        pk = self.nueva()
        self.api.force_login(self.otro)
        for sufijo in ("", "historial/", "firma/"):
            self.assertEqual(self.api.get(f"/api/v1/solicitudes-arriendo/{pk}/{sufijo}").status_code, 404)
        self.assertEqual(self.api.get("/api/v1/solicitudes-arriendo/").data["count"], 0)
        self.assertEqual(self.accion(pk, "cancelar", motivo="Intento").status_code, 404)

    def test_contratista_no_revisa_ni_prepara_entrega_y_personal_no_solicita(self):
        pk = self.nueva()
        for accion in ("aprobar", "rechazar", "entregar"):
            self.assertEqual(self.accion(pk, accion, motivo="Intento", confirmar=True).status_code, 403)
        self.api.force_login(self.admin)
        self.assertEqual(self.enviar().status_code, 403)

    def test_campos_precio_identidad_y_fecha_se_validan(self):
        for cambios in ({"precio_visto": "1"}, {"precio_diario_acordado": "1"}, {"empresa": self.empresa.pk},
                        {"solicitante": self.otro.pk}, {"acepto": "false"}, {"version_id": 999999},
                        {"devolucion_prevista": (timezone.now() - timedelta(days=1)).isoformat()}):
            self.assertEqual(self.enviar(**cambios).status_code, 400)
        self.assertFalse(SolicitudArriendo.objects.exists())

    def test_sin_tarifa_o_perfil_firmado_no_solicita(self):
        Maquinaria.objects.filter(pk=self.maquina.pk).update(precio_diario=None)
        self.assertEqual(self.enviar().status_code, 400)
        Maquinaria.objects.filter(pk=self.maquina.pk).update(precio_diario=25000)
        AceptacionTerminos.objects.filter(usuario=self.usuario).delete()
        self.assertEqual(self.enviar().status_code, 400)

    def test_firma_invalida_y_multipart_obligatorio(self):
        self.assertEqual(self.enviar(firma=SimpleUploadedFile("firma.png", b"invalido")).status_code, 400)
        self.assertEqual(self.api.post("/api/v1/solicitudes-arriendo/enviar/", {}, format="json").status_code, 415)
        self.assertFalse(SolicitudArriendo.objects.exists())

    def test_solicitud_duplicada_no_deja_archivo_huerfano(self):
        self.nueva()
        _, antes = default_storage.listdir("firmas/solicitudes_arriendo")
        self.assertEqual(self.enviar().status_code, 400)
        _, despues = default_storage.listdir("firmas/solicitudes_arriendo")
        self.assertEqual(set(antes), set(despues))

    def test_rechazo_y_revision_repetida_con_motivo(self):
        pk = self.nueva()
        self.api.force_login(self.admin)
        self.assertEqual(self.accion(pk, "rechazar", motivo=" ").status_code, 400)
        self.assertEqual(self.accion(pk, "rechazar", motivo="Datos insuficientes").status_code, 200)
        self.assertEqual(self.accion(pk, "aprobar", motivo="Otra revision").status_code, 400)
        self.assertFalse(self.maquina.reserva_vigente)
        self.api.force_login(self.usuario)
        self.assertEqual(self.enviar().status_code, 201)

    def test_dos_pendientes_permitidas_pero_una_sola_aprobacion(self):
        primera = self.nueva()
        self.api.force_login(self.otro)
        segunda = self.nueva()
        self.aprobar(primera)
        self.assertEqual(self.accion(segunda, "aprobar", motivo="Intento").status_code, 400)
        self.assertEqual(SolicitudArriendo.objects.filter(estado="APROBADA").count(), 1)

    def test_cancelacion_libera_reserva_e_impide_firma_de_entrega_preparada(self):
        pk = self.nueva()
        self.aprobar(pk)
        entrega = self.accion(pk, "entregar", confirmar=True).data["id"]
        self.api.force_login(self.usuario)
        self.assertEqual(self.accion(pk, "cancelar", motivo="Ya no necesito el equipo").status_code, 200)
        self.assertFalse(self.maquina.reserva_vigente)
        respuesta = self.api.post(f"/api/v1/entregas/{entrega}/confirmar/", {"firma": self.firma(), "confirmar": "true"}, format="multipart")
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Arriendo.objects.exists())

    def test_reserva_vencida_falla_operacion_pero_persiste_vencimiento(self):
        pk = self.nueva()
        self.aprobar(pk)
        SolicitudArriendo.objects.filter(pk=pk).update(reserva_hasta=timezone.now() - timedelta(seconds=1), revisada_en=timezone.now() - timedelta(hours=2))
        self.assertEqual(self.accion(pk, "entregar", confirmar=True).status_code, 400)
        solicitud = SolicitudArriendo.objects.get(pk=pk)
        self.assertEqual(solicitud.estado, "VENCIDA")
        self.assertEqual(solicitud.historial.filter(estado_nuevo="VENCIDA").count(), 1)
        self.assertEqual(vencer_reservas(), 0)

    def test_comando_vencimiento_y_filtros_muestran_expiracion_sin_escribir_get(self):
        pk = self.nueva()
        self.aprobar(pk)
        SolicitudArriendo.objects.filter(pk=pk).update(reserva_hasta=timezone.now() - timedelta(seconds=1), revisada_en=timezone.now() - timedelta(hours=2))
        self.assertEqual(self.api.get("/api/v1/solicitudes-arriendo/?estado=VENCIDA").data["count"], 1)
        self.assertEqual(SolicitudArriendo.objects.get(pk=pk).estado, "APROBADA")
        salida = StringIO()
        call_command("vencer_reservas", stdout=salida)
        self.assertIn("Reservas vencidas: 1", salida.getvalue())
        self.assertEqual(SolicitudArriendo.objects.get(pk=pk).estado, "VENCIDA")

    def test_reserva_impide_traslado_baja_mantenimiento_y_entrega_ajena(self):
        pk = self.nueva()
        self.aprobar(pk)
        for accion, datos in (("trasladar", {"destino": self.destino.pk}), ("baja", {})):
            respuesta = self.api.post(f"/api/v1/maquinaria/{self.maquina.pk}/{accion}/", {"motivo": "Intento", **datos}, format="json")
            self.assertEqual(respuesta.status_code, 400)
        respuesta = self.api.post("/api/v1/mantenimientos/", {"maquinaria": self.maquina.pk,
            "fecha_programada": timezone.localdate().isoformat(), "descripcion": "Intento"}, format="json")
        self.assertEqual(respuesta.status_code, 400)
        respuesta = self.api.post("/api/v1/entregas/", {"maquinaria": self.maquina.pk, "empresa": self.empresa.pk,
            "responsable": self.otro.pk, "direccion_uso": "Calle Destino 123", "comuna_uso": "Santiago", "indicaciones_acceso": "Acceso por portón principal",
            "devolucion_prevista": (timezone.now() + timedelta(days=2)).isoformat(), "tarifa_diaria": "25000"}, format="json")
        self.assertEqual(respuesta.status_code, 400)
        mantenimiento = Mantenimiento.objects.create(maquinaria=self.maquina, fecha_programada=timezone.localdate() + timedelta(days=2), descripcion="Programado previamente")
        self.assertEqual(self.api.post(f"/api/v1/mantenimientos/{mantenimiento.pk}/iniciar/", {"confirmar": True}, format="json").status_code, 400)

    def test_revalida_bloqueo_empresa_y_condiciones_antes_de_aprobar(self):
        pk = self.nueva()
        Empresa.objects.filter(pk=self.empresa.pk).update(bloqueada=True, motivo_bloqueo="Incidente")
        self.api.force_login(self.admin)
        self.assertEqual(self.accion(pk, "aprobar", motivo="Intento").status_code, 400)
        Empresa.objects.filter(pk=self.empresa.pk).update(bloqueada=False)
        TerminosCondiciones.objects.create(version="PET-2", contenido="Nuevas condiciones")
        self.assertEqual(self.accion(pk, "aprobar", motivo="Intento").status_code, 400)

    def test_entrega_idempotente_y_confirmacion_no_repetible(self):
        pk = self.nueva()
        self.aprobar(pk)
        primera = self.accion(pk, "entregar", confirmar=True)
        segunda = self.accion(pk, "entregar", confirmar=True)
        self.assertEqual(primera.data["id"], segunda.data["id"])
        self.api.force_login(self.usuario)
        ruta = f"/api/v1/entregas/{primera.data['id']}/confirmar/"
        self.assertEqual(self.api.post(ruta, {"firma": self.firma(), "confirmar": "true"}, format="multipart").status_code, 201)
        self.assertEqual(self.api.post(ruta, {"firma": self.firma(), "confirmar": "true"}, format="multipart").status_code, 400)
        self.assertEqual(Arriendo.objects.count(), 1)

    def test_firma_privada_y_metodos_no_permitidos(self):
        pk = self.nueva()
        respuesta = self.api.get(f"/api/v1/solicitudes-arriendo/{pk}/firma/", HTTP_ACCEPT="image/png")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(b"".join(respuesta.streaming_content).startswith(b"\x89PNG"))
        for metodo in (self.api.patch, self.api.put, self.api.delete):
            self.assertEqual(metodo(f"/api/v1/solicitudes-arriendo/{pk}/", {}, format="json").status_code, 405)
        self.assertEqual(self.api.get("/api/v1/solicitudes-arriendo/?otro=1").status_code, 400)

    def test_templates_catalogo_solicitud_revision_y_rechazo(self):
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get("/maquinaria/"), "Solicitar arriendo")
        ruta = f"/solicitudes-arriendo/nueva/{self.maquina.pk}/"
        self.assertContains(self.client.get(ruta), 'id="firma"')
        datos = self.datos()
        datos.pop("maquinaria")
        datos.pop("confirmar")
        respuesta = self.client.post(ruta, datos)
        self.assertEqual(respuesta.status_code, 302)
        pk = SolicitudArriendo.objects.get().pk
        self.assertContains(self.client.get(f"/solicitudes-arriendo/{pk}/"), "Condiciones firmadas")
        self.client.force_login(self.admin)
        self.assertContains(self.client.get("/solicitudes-arriendo/"), "Revisar solicitudes")
        self.assertContains(self.client.get(f"/solicitudes-arriendo/{pk}/"), "Aprobar y reservar")
        respuesta = self.client.post(f"/solicitudes-arriendo/{pk}/rechazar/", {"motivo": "", "confirmar": "on"})
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(SolicitudArriendo.objects.get().estado, "PENDIENTE")

    def test_csrf_real_para_solicitar_y_revisar(self):
        cliente = APIClient(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post("/api/v1/solicitudes-arriendo/enviar/", self.datos(), format="multipart").status_code, 403)
        cliente.get("/perfil/")
        respuesta = cliente.post("/api/v1/solicitudes-arriendo/enviar/", self.datos(), format="multipart",
            HTTP_X_CSRFTOKEN=cliente.cookies["csrftoken"].value)
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        pk = respuesta.data["id"]
        cliente.force_login(self.admin)
        self.assertEqual(cliente.post(f"/api/v1/solicitudes-arriendo/{pk}/aprobar/", {"motivo": "Prueba"}, format="json").status_code, 403)

    def test_ninguna_entrega_nueva_admite_tarifa_cero(self):
        self.api.force_login(self.admin)
        datos = {"maquinaria": self.maquina.pk, "empresa": self.empresa.pk, "responsable": self.usuario.pk,
            "direccion_uso": "Calle Destino 123", "comuna_uso": "Santiago", "indicaciones_acceso": "Acceso por portón principal", "devolucion_prevista": (timezone.now() + timedelta(days=2)).isoformat(),
            "tarifa_diaria": "0"}
        self.assertEqual(self.api.post("/api/v1/entregas/", datos, format="json").status_code, 400)

    def test_reserva_menor_a_una_hora_no_supera_devolucion_prevista(self):
        fecha = timezone.now() + timedelta(minutes=20)
        respuesta = self.enviar(devolucion_prevista=fecha.isoformat())
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.aprobar(respuesta.data["id"])
        self.assertEqual(SolicitudArriendo.objects.get().reserva_hasta, fecha)

    def test_fallo_historial_no_deja_solicitud_o_firma(self):
        cantidad = SolicitudArriendo.objects.count()
        try:
            _, anteriores = default_storage.listdir("firmas/solicitudes_arriendo")
        except FileNotFoundError:
            anteriores = []
        with patch("maquinaria.servicios_solicitudes_arriendo.registrar_cambio", side_effect=IntegrityError("Fallo de prueba")):
            respuesta = self.enviar()
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(SolicitudArriendo.objects.count(), cantidad)
        try:
            _, archivos = default_storage.listdir("firmas/solicitudes_arriendo")
        except FileNotFoundError:
            archivos = []
        self.assertEqual(set(archivos), set(anteriores))

    def test_solicita_y_usa_maquina_sin_ninguna_obra_registrada(self):
        self.obra.delete()
        pk = self.nueva()
        solicitud = SolicitudArriendo.objects.get(pk=pk)
        self.assertIsNone(solicitud.obra_destino_id)
        self.assertEqual(solicitud.direccion_uso, "Calle Destino 123")
        self.assertEqual(solicitud.comuna_uso, "Santiago")
        self.aprobar(pk)
        entrega = self.accion(pk, "entregar", confirmar=True)
        self.assertEqual(entrega.status_code, 201, entrega.data)
        self.assertIsNone(entrega.data["obra_destino"])
        self.api.force_login(self.usuario)
        respuesta = self.api.post(f"/api/v1/entregas/{entrega.data['id']}/confirmar/",
            {"firma": self.firma(), "confirmar": "true"}, format="multipart")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        arriendo_id = respuesta.data["id"]
        self.assertIsNone(respuesta.data["obra_destino"])
        for campo in ("direccion_uso", "comuna_uso", "indicaciones_acceso"):
            self.assertEqual(respuesta.data[campo], getattr(solicitud, campo))
        self.assertEqual(self.api.post(f"/api/v1/arriendos/{arriendo_id}/uso/iniciar/", {}, format="json").status_code, 200)
        self.assertEqual(self.api.post(f"/api/v1/arriendos/{arriendo_id}/uso/pausar/", {}, format="json").status_code, 200)
        self.api.force_login(self.admin)
        recibida = self.api.post(f"/api/v1/arriendos/{arriendo_id}/recibir/", {"bodega": self.bodega.pk,
            "observaciones": "Equipo recibido", "confirmar": True}, format="json")
        self.assertEqual(recibida.status_code, 201, recibida.data)
        self.api.force_login(self.usuario)
        self.assertEqual(self.api.post(f"/api/v1/devoluciones/{recibida.data['id']}/confirmar/",
            {"firma": self.firma(), "confirmar": "true"}, format="multipart").status_code, 200)

    def test_direccion_comuna_obligatorias_y_limites_sin_aceptar_obra(self):
        for datos in ({"direccion_uso": " "}, {"comuna_uso": " "}, {"direccion_uso": "x" * 256},
                      {"comuna_uso": "x" * 101}, {"indicaciones_acceso": "x" * 3001},
                      {"obra_destino": self.obra.pk}, {"destino_legacy": "true"}):
            respuesta = self.enviar(**datos)
            self.assertEqual(respuesta.status_code, 400, respuesta.data)
        self.assertFalse(SolicitudArriendo.objects.exists())

    def test_formulario_sin_selector_de_obra_y_destino_en_revision(self):
        self.client.force_login(self.usuario)
        respuesta = self.client.get(f"/solicitudes-arriendo/nueva/{self.maquina.pk}/")
        self.assertContains(respuesta, 'name="direccion_uso"')
        self.assertContains(respuesta, 'name="comuna_uso"')
        self.assertNotContains(respuesta, 'name="obra_destino"')
        pk = self.nueva()
        respuesta = self.client.get(f"/solicitudes-arriendo/{pk}/")
        self.assertContains(respuesta, "Calle Destino 123")
        self.assertContains(respuesta, "Santiago")
        self.assertContains(respuesta, "Acceso por portón principal")

    def test_destino_firmado_no_es_editable_por_api(self):
        pk = self.nueva()
        respuesta = self.api.patch(f"/api/v1/solicitudes-arriendo/{pk}/", {"direccion_uso": "Otra calle"}, format="json")
        self.assertEqual(respuesta.status_code, 405)
        self.aprobar(pk)
        self.assertEqual(self.accion(pk, "entregar", confirmar=True, direccion_uso="Otra calle").status_code, 400)
        self.assertEqual(SolicitudArriendo.objects.get(pk=pk).direccion_uso, "Calle Destino 123")

    def test_manipular_destino_del_comprobante_impide_confirmar(self):
        from .models import SolicitudEntrega
        pk = self.nueva()
        self.aprobar(pk)
        entrega = self.accion(pk, "entregar", confirmar=True).data["id"]
        SolicitudEntrega.objects.filter(pk=entrega).update(direccion_uso="Dirección alterada")
        self.api.force_login(self.usuario)
        respuesta = self.api.post(f"/api/v1/entregas/{entrega}/confirmar/", {"firma": self.firma(), "confirmar": "true"}, format="multipart")
        self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(Arriendo.objects.exists())

    def test_visor_privado_y_acciones_del_personal_segun_estado(self):
        pk = self.nueva()
        self.client.force_login(self.admin)
        respuesta = self.client.get(f"/solicitudes-arriendo/{pk}/")
        self.assertContains(respuesta, "data-firma-preview")
        self.assertContains(respuesta, 'id="visor-firma"')
        self.assertContains(respuesta, 'aria-label="Cerrar firma"')
        self.assertContains(respuesta, "Aprobar y reservar")
        self.assertNotContains(respuesta, ">Cancelar solicitud</button>")
        self.api.force_login(self.admin)
        self.assertEqual(self.accion(pk, "cancelar", motivo="Intento").status_code, 400)
        self.aprobar(pk)
        respuesta = self.client.get(f"/solicitudes-arriendo/{pk}/")
        self.assertContains(respuesta, ">Cancelar solicitud</button>")
        self.assertEqual(self.accion(pk, "cancelar", motivo="Imposible entregar").status_code, 200)
