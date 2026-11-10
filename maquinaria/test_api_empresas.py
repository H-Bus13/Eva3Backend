from datetime import timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (AceptacionTerminos, Arriendo, Bodega, Empresa, HistorialBloqueoEmpresa,
                     Maquinaria, Obra, TerminosCondiciones, Usuario)
from .servicios_bloqueos import actualizar_bloqueo_por_atraso


class APIEmpresasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_empresa_api", rut="11111111-1", password="Clave!4820")
        cls.gestor = Usuario.objects.create_user(username="gestor_empresa_api", rut="22222222-2", rol="BODEGUERO")
        cls.gestor.user_permissions.add(Permission.objects.get(content_type__app_label="maquinaria", codename="gestionar_bloqueos_empresa"))
        cls.arriendos = Usuario.objects.create_user(username="arriendos_empresa_api", rut="33333333-3", rol="BODEGUERO")
        cls.arriendos.user_permissions.add(Permission.objects.get(content_type__app_label="maquinaria", codename="gestionar_arriendos"))
        cls.empresa = Empresa.objects.create(rut="77777777-7", razon_social="Constructora API")
        cls.otra = Empresa.objects.create(rut="88888888-8", razon_social="Segunda empresa")
        cls.cliente = Usuario.objects.create_user(username="cliente_empresa_api", rut="44444444-4", empresa=cls.empresa, estado_aprobacion="APROBADO")
        cls.bodega = Bodega.objects.create(nombre="Central API", direccion="Direccion central")
        cls.obra = Obra.objects.create(nombre="Obra API", direccion="Direccion obra")
        cls.terminos = TerminosCondiciones.objects.create(version="EMP-API", contenido="Condiciones")
        ahora = timezone.now()
        cls.aceptacion = AceptacionTerminos.objects.create(usuario=cls.cliente, terminos=cls.terminos,
            aceptado_en=ahora, firmado_en=ahora, firma="perfil.png")

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.admin)

    def accion(self, accion, **datos):
        return self.api.post(f"/api/v1/empresas/{self.empresa.pk}/{accion}/", datos, format="json")

    def detalle(self):
        return self.api.get(f"/api/v1/empresas/{self.empresa.pk}/")

    def atrasado(self, empresa=None):
        maquina = Maquinaria.objects.create(codigo=f"EMP-{Maquinaria.objects.count()}", nombre="Equipo API",
            marca="Marca", modelo="Modelo", bodega=self.bodega, estado="EN_USO")
        ahora = timezone.now()
        return Arriendo.objects.create(maquinaria=maquina, empresa=empresa or self.empresa, responsable=self.cliente,
            obra_destino=self.obra, aceptacion=self.aceptacion, entregado_en=ahora - timedelta(days=3),
            devolucion_prevista=ahora - timedelta(days=1), tarifa_diaria=0, firma_entrega="entrega.png")

    def test_bloqueo_desbloqueo_con_motivo_autor_e_historial(self):
        respuesta = self.accion("bloquear", motivo="Incidente revisado")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertTrue(respuesta.data["tiene_bloqueo"])
        self.assertEqual(respuesta.data["motivo_bloqueo"], "Incidente revisado")
        respuesta = self.accion("desbloquear", motivo="Incidente resuelto")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.data["tiene_bloqueo"])
        self.assertEqual(respuesta.data["motivo_bloqueo"], "")
        eventos = self.api.get(f"/api/v1/empresas/{self.empresa.pk}/historial/").data
        self.assertEqual(eventos["count"], 2)
        self.assertEqual(eventos["results"][0]["accion"], "DESBLOQUEO")
        self.assertEqual(eventos["results"][0]["responsable"], self.admin.pk)
        self.assertEqual(eventos["results"][0]["origen"], "MANUAL")

    def test_motivo_vacio_ausente_o_campos_adicionales_no_modifican(self):
        for datos in [{}, {"motivo": " "}, {"motivo": "x" * 1001}, {"motivo": "Prueba", "bloqueada": True},
                      {"motivo": "Prueba", "responsable": self.cliente.pk}]:
            self.assertEqual(self.accion("bloquear", **datos).status_code, 400)
        self.assertFalse(HistorialBloqueoEmpresa.objects.exists())
        self.empresa.refresh_from_db()
        self.assertFalse(self.empresa.bloqueada)

    def test_operacion_repetida_no_duplica_historial(self):
        self.assertEqual(self.accion("desbloquear", motivo="Prueba").status_code, 400)
        self.assertEqual(self.accion("bloquear", motivo="Prueba").status_code, 200)
        self.assertEqual(self.accion("bloquear", motivo="Prueba repetida").status_code, 400)
        self.assertEqual(HistorialBloqueoEmpresa.objects.count(), 1)

    def test_desbloqueo_manual_conserva_bloqueo_por_atraso(self):
        self.atrasado()
        actualizar_bloqueo_por_atraso(self.empresa.pk)
        self.accion("bloquear", motivo="Incidente adicional")
        respuesta = self.accion("desbloquear", motivo="Incidente resuelto")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.data["bloqueada"])
        self.assertTrue(respuesta.data["bloqueada_por_atraso"])
        self.assertTrue(respuesta.data["bloqueo_por_atraso_actual"])
        self.assertTrue(respuesta.data["tiene_bloqueo"])

    def test_get_evalua_atraso_sin_escribir_flag_ni_historial(self):
        self.atrasado()
        respuesta = self.detalle()
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.data["bloqueada_por_atraso"])
        self.assertTrue(respuesta.data["bloqueo_por_atraso_actual"])
        self.assertTrue(respuesta.data["tiene_bloqueo"])
        self.api.get("/api/v1/empresas/?estado=bloqueadas")
        self.empresa.refresh_from_db()
        self.assertFalse(self.empresa.bloqueada_por_atraso)
        self.assertFalse(HistorialBloqueoEmpresa.objects.exists())

    def test_recepcion_fisica_termina_atraso_aunque_firma_este_pendiente(self):
        arriendo = self.atrasado()
        actualizar_bloqueo_por_atraso(self.empresa.pk)
        Arriendo.objects.filter(pk=arriendo.pk).update(recibido_en=timezone.now())
        respuesta = self.detalle()
        self.assertTrue(respuesta.data["bloqueada_por_atraso"])
        self.assertFalse(respuesta.data["bloqueo_por_atraso_actual"])
        self.assertFalse(respuesta.data["tiene_bloqueo"])
        self.assertEqual(self.api.get(f"/api/v1/empresas/{self.empresa.pk}/atrasos/").data["count"], 0)

    def test_permisos_separan_gestion_bloqueos_y_detalle_arriendos(self):
        self.atrasado()
        self.api.force_login(self.gestor)
        self.assertEqual(self.detalle().status_code, 200)
        self.assertEqual(self.accion("bloquear", motivo="Prueba").status_code, 200)
        self.assertEqual(self.api.get(f"/api/v1/empresas/{self.empresa.pk}/historial/").status_code, 200)
        self.assertEqual(self.api.get(f"/api/v1/empresas/{self.empresa.pk}/atrasos/").status_code, 403)
        self.api.force_login(self.arriendos)
        self.assertEqual(self.detalle().status_code, 200)
        self.assertEqual(self.api.get(f"/api/v1/empresas/{self.empresa.pk}/atrasos/").status_code, 200)
        self.assertEqual(self.accion("desbloquear", motivo="Prueba").status_code, 403)

    def test_anonimo_contratista_y_suspendido_no_acceden(self):
        self.api.logout()
        self.assertEqual(self.detalle().status_code, 403)
        self.api.force_login(self.cliente)
        for sufijo in ("", "historial/", "atrasos/"):
            self.assertEqual(self.api.get(f"/api/v1/empresas/{self.empresa.pk}/{sufijo}").status_code, 403)
        self.admin.suspendida = True
        self.api.force_authenticate(user=self.admin)
        self.assertEqual(self.detalle().status_code, 403)

    def test_atrasos_filtrados_por_empresa_no_incluyen_otros_ni_futuros(self):
        propio = self.atrasado()
        self.atrasado(self.otra)
        futuro = self.atrasado()
        Arriendo.objects.filter(pk=futuro.pk).update(devolucion_prevista=timezone.now() + timedelta(days=1))
        respuesta = self.api.get(f"/api/v1/empresas/{self.empresa.pk}/atrasos/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["count"], 1)
        self.assertEqual(respuesta.data["results"][0]["id"], propio.pk)
        self.assertNotIn("firma_entrega", respuesta.data["results"][0])

    def test_filtros_busqueda_y_paginacion(self):
        self.atrasado()
        self.assertEqual(self.api.get("/api/v1/empresas/?estado=bloqueadas").data["count"], 1)
        self.assertEqual(self.api.get("/api/v1/empresas/?estado=habilitadas").data["count"], 1)
        self.assertEqual(self.api.get("/api/v1/empresas/?q=Constructora").data["count"], 1)
        self.assertEqual(self.api.get("/api/v1/empresas/?q=77777777").data["count"], 1)
        for datos in ("estado=otro", "page=0", "desconocido=1"):
            self.assertEqual(self.api.get("/api/v1/empresas/?" + datos).status_code, 400)
        self.assertEqual(self.api.get("/api/v1/empresas/?page=2").status_code, 404)
        for accion in ("historial", "atrasos"):
            self.assertEqual(self.api.get(f"/api/v1/empresas/{self.empresa.pk}/{accion}/?desconocido=1").status_code, 400)

    def test_sin_altas_edicion_eliminacion_y_formatos(self):
        self.assertEqual(self.api.post("/api/v1/empresas/", {}, format="json").status_code, 405)
        for metodo in (self.api.patch, self.api.put, self.api.delete):
            self.assertEqual(metodo(f"/api/v1/empresas/{self.empresa.pk}/", {}, format="json").status_code, 405)
        self.assertEqual(self.api.get("/api/v1/empresas/999999/").status_code, 404)
        self.assertEqual(self.api.get(f"/api/v1/empresas/{self.empresa.pk}.json").status_code, 200)
        self.assertIn("no-store", self.detalle()["Cache-Control"])

    def test_csrf_real_en_bloqueo_y_desbloqueo(self):
        cliente = APIClient(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        ruta = f"/api/v1/empresas/{self.empresa.pk}/"
        self.assertEqual(cliente.post(ruta + "bloquear/", {"motivo": "Prueba"}, format="json").status_code, 403)
        cliente.get("/perfil/")
        token = cliente.cookies["csrftoken"].value
        for accion in ("bloquear", "desbloquear"):
            respuesta = cliente.post(ruta + accion + "/", {"motivo": "Prueba CSRF"}, format="json", HTTP_X_CSRFTOKEN=token)
            self.assertEqual(respuesta.status_code, 200, respuesta.data)
