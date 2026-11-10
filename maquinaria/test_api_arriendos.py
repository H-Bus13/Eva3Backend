from datetime import timedelta
from io import BytesIO

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image, ImageDraw
from rest_framework.test import APIClient

from .models import (AceptacionTerminos, Arriendo, Bodega, Empresa, Maquinaria, Obra,
                     SesionUso, SolicitudEntrega, TerminosCondiciones, Usuario)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class APIArriendosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_arriendo_api", rut="11111111-1", password="Clave!4820")
        cls.empresa = Empresa.objects.create(rut="77777777-7", razon_social="Empresa API")
        cls.dueno = Usuario.objects.create_user(username="responsable_api", rut="22222222-2", empresa=cls.empresa,
            estado_aprobacion="APROBADO", password="Clave!4820")
        cls.otro = Usuario.objects.create_user(username="otro_api", rut="33333333-3", empresa=cls.empresa,
            estado_aprobacion="APROBADO", password="Clave!4820")
        cls.obra = Obra.objects.create(nombre="Obra API", direccion="Direccion obra")
        cls.bodega = Bodega.objects.create(nombre="Central", direccion="Direccion central")
        cls.maquina = Maquinaria.objects.create(codigo="ARR-001", nombre="Equipo API", marca="Marca", modelo="Modelo",
            bodega=cls.bodega, revision_pendiente=False, ultima_mantencion_conocida=True,
            tiempo_uso_acumulado=timedelta(hours=10), tiempo_uso_inicial=timedelta(hours=10))
        cls.terminos = TerminosCondiciones.objects.create(version="API-1", contenido="Condiciones de arriendo")
        ahora = timezone.now()
        AceptacionTerminos.objects.create(usuario=cls.dueno, terminos=cls.terminos,
            aceptado_en=ahora, firmado_en=ahora, firma="perfil.png")

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.admin)

    def firma(self, vacia=False):
        imagen = Image.new("RGB", (900, 300), "white")
        if not vacia:
            ImageDraw.Draw(imagen).line([(40, 240), (180, 40), (250, 210), (600, 100)], fill="black", width=6)
        salida = BytesIO()
        imagen.save(salida, "PNG")
        return SimpleUploadedFile("firma.png", salida.getvalue(), content_type="image/png")

    def preparar(self, **cambios):
        datos = {"maquinaria": self.maquina.pk, "empresa": self.empresa.pk, "responsable": self.dueno.pk,
            "direccion_uso": "Calle Destino 123", "comuna_uso": "Santiago", "indicaciones_acceso": "Acceso por portón principal", "devolucion_prevista": (timezone.now() + timedelta(days=3)).isoformat(),
            "tarifa_diaria": "25000.00", "observaciones": "Entrega API"}
        datos.update(cambios)
        return self.api.post("/api/v1/entregas/", datos, format="json")

    def confirmar(self, tipo, pk, **cambios):
        datos = {"firma": self.firma(), "confirmar": "true"}
        datos.update(cambios)
        return self.api.post(f"/api/v1/{tipo}/{pk}/confirmar/", datos, format="multipart")

    def arrendar(self):
        self.api.force_login(self.admin)
        solicitud = self.preparar()
        self.assertEqual(solicitud.status_code, 201, solicitud.data)
        self.api.force_login(self.dueno)
        respuesta = self.confirmar("entregas", solicitud.data["id"])
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        return respuesta.data["id"]

    def recibir(self, pk, **cambios):
        self.api.force_login(self.admin)
        datos = {"bodega": self.bodega.pk, "observaciones": "Equipo recibido sin problemas", "confirmar": True}
        datos.update(cambios)
        return self.api.post(f"/api/v1/arriendos/{pk}/recibir/", datos, format="json")

    def uso(self, pk, accion, **datos):
        return self.api.post(f"/api/v1/arriendos/{pk}/uso/{accion}/", datos, format="json")

    def test_flujo_entrega_uso_recepcion_firma_y_archivos_privados(self):
        pk = self.arrendar()
        self.assertEqual(self.uso(pk, "iniciar").status_code, 200)
        SesionUso.objects.filter(arriendo_id=pk).update(inicio=timezone.now() - timedelta(minutes=30))
        recibida = self.recibir(pk)
        self.assertEqual(recibida.status_code, 201, recibida.data)
        self.maquina.refresh_from_db()
        self.assertGreaterEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=10, minutes=30))
        self.assertFalse(SesionUso.objects.filter(arriendo_id=pk, fin__isnull=True).exists())
        self.api.force_login(self.dueno)
        self.assertEqual(self.uso(pk, "iniciar").status_code, 400)
        respuesta = self.confirmar("devoluciones", recibida.data["id"])
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["estado"], "Cerrado")
        self.assertNotIn("firma_entrega", respuesta.data)
        for tipo in ("entrega", "devolucion"):
            imagen = self.api.get(f"/api/v1/arriendos/{pk}/firmas/{tipo}/", HTTP_ACCEPT="image/png")
            self.assertEqual(imagen.status_code, 200)
            self.assertEqual(imagen["Content-Type"], "image/png")
            self.assertIn("no-store", imagen["Cache-Control"])
            self.assertTrue(b"".join(imagen.streaming_content).startswith(b"\x89PNG"))
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")

    def test_otro_usuario_misma_empresa_no_ve_arriendo_sesiones_ni_firmas(self):
        pk = self.arrendar()
        solicitud = SolicitudEntrega.objects.get(arriendo_id=pk)
        self.api.force_login(self.otro)
        for ruta in [f"arriendos/{pk}/", f"arriendos/{pk}/sesiones/", f"arriendos/{pk}/firmas/entrega/", f"entregas/{solicitud.pk}/"]:
            respuesta = self.api.get("/api/v1/" + ruta)
            self.assertEqual(respuesta.status_code, 404)
        for recurso in ("arriendos", "entregas", "devoluciones"):
            self.assertEqual(self.api.get(f"/api/v1/{recurso}/").data["count"], 0)
        self.assertEqual(self.confirmar("entregas", solicitud.pk).status_code, 404)

    def test_personal_no_firma_ni_inicia_por_el_responsable(self):
        solicitud = self.preparar().data["id"]
        self.assertEqual(self.confirmar("entregas", solicitud).status_code, 403)
        self.api.force_login(self.dueno)
        arriendo = self.confirmar("entregas", solicitud).data["id"]
        self.api.force_login(self.admin)
        self.assertEqual(self.uso(arriendo, "iniciar").status_code, 403)

    def test_contratista_no_prepara_cancela_ni_recibe(self):
        solicitud = self.preparar().data["id"]
        self.api.force_login(self.dueno)
        self.assertEqual(self.preparar().status_code, 403)
        self.assertEqual(self.api.post(f"/api/v1/entregas/{solicitud}/cancelar/", {"motivo": "Prueba"}, format="json").status_code, 403)
        pk = self.confirmar("entregas", solicitud).data["id"]
        self.assertEqual(self.api.post(f"/api/v1/arriendos/{pk}/recibir/", {}, format="json").status_code, 403)

    def test_entrega_no_reserva_equipo_y_no_admite_duplicado(self):
        self.assertEqual(self.preparar().status_code, 201)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertEqual(Arriendo.objects.count(), 0)
        self.assertEqual(self.preparar().status_code, 400)

    def test_entrada_rechaza_cambios_sensibles_y_fecha_pasada(self):
        for cambios in [{"estado": "EN_USO"}, {"responsable": self.admin.pk},
                        {"devolucion_prevista": (timezone.now() - timedelta(days=1)).isoformat()}, {"tarifa_diaria": "-1"}]:
            self.assertEqual(self.preparar(**cambios).status_code, 400)
        self.assertFalse(SolicitudEntrega.objects.exists())

    def test_revalida_empresa_bloqueada_al_firmar(self):
        pk = self.preparar().data["id"]
        Empresa.objects.filter(pk=self.empresa.pk).update(bloqueada=True, motivo_bloqueo="Prueba")
        self.api.force_login(self.dueno)
        self.assertEqual(self.confirmar("entregas", pk).status_code, 400)
        self.assertFalse(Arriendo.objects.exists())

    def test_firma_invalida_vacia_o_sin_confirmacion_no_entrega(self):
        pk = self.preparar().data["id"]
        self.api.force_login(self.dueno)
        for datos in [{"firma": self.firma(vacia=True)}, {"confirmar": "false"},
                      {"firma": SimpleUploadedFile("firma.png", b"no es PNG")}, {"horas": "100"}]:
            self.assertEqual(self.confirmar("entregas", pk, **datos).status_code, 400)
        self.assertFalse(Arriendo.objects.exists())

    def test_confirmar_solo_admite_multipart(self):
        pk = self.preparar().data["id"]
        self.api.force_login(self.dueno)
        respuesta = self.api.post(f"/api/v1/entregas/{pk}/confirmar/", {"confirmar": True}, format="json")
        self.assertEqual(respuesta.status_code, 415)

    def test_vencida_cancelada_y_confirmada_no_se_pueden_reutilizar(self):
        pk = self.preparar().data["id"]
        SolicitudEntrega.objects.filter(pk=pk).update(vence_en=timezone.now() - timedelta(seconds=1))
        self.api.force_login(self.dueno)
        self.assertEqual(self.confirmar("entregas", pk).status_code, 400)
        self.api.force_login(self.admin)
        pk2 = self.preparar().data["id"]
        self.assertEqual(self.api.post(f"/api/v1/entregas/{pk2}/cancelar/", {"motivo": ""}, format="json").status_code, 400)
        self.assertEqual(self.api.post(f"/api/v1/entregas/{pk2}/cancelar/", {"motivo": "Cambio solicitado"}, format="json").status_code, 200)
        self.api.force_login(self.dueno)
        self.assertEqual(self.confirmar("entregas", pk2).status_code, 400)
        self.api.force_login(self.admin)
        pk3 = self.preparar().data["id"]
        self.api.force_login(self.dueno)
        self.assertEqual(self.confirmar("entregas", pk3).status_code, 201)
        self.assertEqual(self.confirmar("entregas", pk3).status_code, 400)
        self.assertEqual(Arriendo.objects.count(), 1)

    def test_timer_servidor_no_permite_horas_del_cliente_ni_doble_suma(self):
        pk = self.arrendar()
        self.assertEqual(self.uso(pk, "iniciar", segundos=5000).status_code, 400)
        self.assertEqual(self.uso(pk, "iniciar").status_code, 200)
        self.assertEqual(self.uso(pk, "iniciar").status_code, 400)
        SesionUso.objects.filter(arriendo_id=pk).update(inicio=timezone.now() - timedelta(hours=1))
        respuesta = self.uso(pk, "pausar")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.maquina.refresh_from_db()
        acumulado = self.maquina.tiempo_uso_acumulado
        self.assertGreaterEqual(acumulado, timedelta(hours=11))
        self.assertEqual(self.uso(pk, "pausar").status_code, 400)
        self.assertEqual(self.uso(pk, "sincronizar").status_code, 200)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, acumulado)
        self.assertEqual(self.api.get(f"/api/v1/arriendos/{pk}/sesiones/").data["count"], 1)

    def test_umbral_250_horas_programa_revision_sin_detener_sesion(self):
        pk = self.arrendar()
        Maquinaria.objects.filter(pk=self.maquina.pk).update(tiempo_uso_acumulado=timedelta(hours=249))
        self.assertEqual(self.uso(pk, "iniciar").status_code, 200)
        SesionUso.objects.filter(arriendo_id=pk).update(inicio=timezone.now() - timedelta(hours=2))
        respuesta = self.uso(pk, "sincronizar")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertTrue(respuesta.data["revision_pendiente"])
        self.assertTrue(SesionUso.objects.filter(arriendo_id=pk, fin__isnull=True).exists())
        self.uso(pk, "sincronizar")
        self.assertEqual(self.maquina.mantenimientos.count(), 1)

    def test_cancelar_devolucion_no_revierte_recepcion(self):
        pk = self.arrendar()
        recepcion = self.recibir(pk)
        self.assertEqual(recepcion.status_code, 201, recepcion.data)
        ruta = f"/api/v1/devoluciones/{recepcion.data['id']}/cancelar/"
        self.assertEqual(self.api.post(ruta, {"motivo": "Corregir observacion"}, format="json").status_code, 200)
        self.assertIsNotNone(Arriendo.objects.get(pk=pk).recibido_en)
        self.api.force_login(self.dueno)
        self.assertEqual(self.uso(pk, "iniciar").status_code, 400)
        nueva = self.recibir(pk)
        self.assertEqual(nueva.status_code, 201, nueva.data)
        self.api.force_login(self.dueno)
        self.assertEqual(self.confirmar("devoluciones", nueva.data["id"]).status_code, 200)

    def test_recepcion_exige_confirmacion_y_admite_devolver_empresa_bloqueada(self):
        pk = self.arrendar()
        self.assertEqual(self.recibir(pk, confirmar=False).status_code, 400)
        self.assertIsNone(Arriendo.objects.get(pk=pk).recibido_en)
        Empresa.objects.filter(pk=self.empresa.pk).update(bloqueada=True, motivo_bloqueo="Prueba")
        recibida = self.recibir(pk, requiere_revision=True)
        self.assertEqual(recibida.status_code, 201, recibida.data)
        self.api.force_login(self.dueno)
        self.assertEqual(self.confirmar("devoluciones", recibida.data["id"]).status_code, 200)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")

    def test_metodos_no_permitidos_y_filtros_invalidos(self):
        pk = self.arrendar()
        for verbo in (self.api.patch, self.api.put, self.api.delete):
            self.assertEqual(verbo(f"/api/v1/arriendos/{pk}/", {}, format="json").status_code, 405)
        self.assertEqual(self.api.post("/api/v1/arriendos/", {}, format="json").status_code, 405)
        self.assertEqual(self.api.post("/api/v1/devoluciones/", {}, format="json").status_code, 405)
        for ruta in ("arriendos/?estado=otro", "entregas/?estado=otro", "devoluciones/?invalido=1"):
            self.assertEqual(self.api.get("/api/v1/" + ruta).status_code, 400)
        self.assertEqual(self.api.get("/api/v1/arriendos/?estado=abierto").data["count"], 1)
        self.assertEqual(self.api.get("/api/v1/entregas/?estado=confirmada").data["count"], 1)

    def test_error_firma_negociada_png_sigue_siendo_json(self):
        pk = self.arrendar()
        self.api.force_login(self.otro)
        respuesta = self.api.get(f"/api/v1/arriendos/{pk}/firmas/entrega/", HTTP_ACCEPT="image/png")
        self.assertEqual(respuesta.status_code, 404)
        self.assertTrue(respuesta["Content-Type"].startswith("application/json"))

    def test_csrf_requerido_en_preparacion_y_firma(self):
        cliente = APIClient(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.post("/api/v1/entregas/", {}, format="json").status_code, 403)
        pk = self.preparar().data["id"]
        cliente.force_login(self.dueno)
        self.assertEqual(cliente.post(f"/api/v1/entregas/{pk}/confirmar/",
            {"firma": self.firma(), "confirmar": "true"}, format="multipart").status_code, 403)
        cliente.get("/perfil/")
        self.assertIn("csrftoken", cliente.cookies)
        respuesta = cliente.post(f"/api/v1/entregas/{pk}/confirmar/",
            {"firma": self.firma(), "confirmar": "true"}, format="multipart",
            HTTP_X_CSRFTOKEN=cliente.cookies["csrftoken"].value)
        self.assertEqual(respuesta.status_code, 201, respuesta.data)

    def test_no_habilitados_no_consultan_recursos_privados(self):
        pk = self.arrendar()
        self.api.logout()
        for recurso in ("arriendos", "entregas", "devoluciones"):
            self.assertEqual(self.api.get(f"/api/v1/{recurso}/").status_code, 403)
        self.dueno.suspendida = True
        self.api.force_authenticate(user=self.dueno)
        self.assertEqual(self.api.get(f"/api/v1/arriendos/{pk}/").status_code, 403)

    def test_nueva_version_condiciones_impide_confirmar_solicitud_anterior(self):
        pk = self.preparar().data["id"]
        nueva = TerminosCondiciones.objects.create(version="API-2", contenido="Nuevas condiciones")
        ahora = timezone.now()
        AceptacionTerminos.objects.create(usuario=self.dueno, terminos=nueva,
            aceptado_en=ahora, firmado_en=ahora, firma="nueva.png")
        self.api.force_login(self.dueno)
        self.assertEqual(self.confirmar("entregas", pk).status_code, 400)
        self.assertFalse(Arriendo.objects.exists())

    def test_recepcion_repetida_no_duplica_horas_y_firma_ausente_da_404(self):
        pk = self.arrendar()
        self.uso(pk, "iniciar")
        SesionUso.objects.filter(arriendo_id=pk).update(inicio=timezone.now() - timedelta(hours=1))
        self.assertEqual(self.recibir(pk).status_code, 201)
        self.maquina.refresh_from_db()
        horas = self.maquina.tiempo_uso_acumulado
        self.assertEqual(self.recibir(pk).status_code, 400)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, horas)
        respuesta = self.api.get(f"/api/v1/arriendos/{pk}/firmas/devolucion/", HTTP_ACCEPT="image/png")
        self.assertEqual(respuesta.status_code, 404)
        self.assertTrue(respuesta["Content-Type"].startswith("application/json"))
