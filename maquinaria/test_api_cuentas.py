from datetime import timedelta
from io import BytesIO

from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw
from rest_framework.test import APIClient

from .models import Usuario, Empresa, TerminosCondiciones, AceptacionTerminos, HistorialAdministracionUsuario
from .condiciones import CLAVE_ACEPTACION


@override_settings(STORAGES={"default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
                            "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}})
class APICuentasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_cuentas", rut="11111111-1", password="Seguro!Componente4820")
        cls.empresa = Empresa.objects.create(rut="77777777-7", razon_social="Empresa API")
        cls.cliente = Usuario.objects.create_user(username="cliente_cuentas", rut="22222222-2", empresa=cls.empresa,
            estado_aprobacion="APROBADO", password="Seguro!Componente4820")
        cls.interno = Usuario.objects.create_user(username="interno_cuentas", rut="33333333-3", rol="BODEGUERO", first_name="Original", email="antes@example.com")
        cls.pendiente = Usuario.objects.create_user(username="pendiente_cuentas", rut="44444444-4", empresa=cls.empresa,
            is_active=False, password="Seguro!Componente4820")
        cls.terminos = TerminosCondiciones.objects.create(version="CUENTAS-1", contenido="Condiciones vigentes")

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.admin)

    def accion(self, pk, accion, **datos):
        return self.api.post(f"/api/v1/usuarios/{pk}/{accion}/", datos, format="json")

    def revisar(self, accion, **datos):
        return self.api.post(f"/api/v1/solicitudes/{self.pendiente.pk}/{accion}/", datos, format="json")

    def firma(self):
        imagen = Image.new("RGB", (900, 300), "white")
        ImageDraw.Draw(imagen).line([(30, 200), (160, 40), (270, 220), (700, 100)], fill="black", width=6)
        salida = BytesIO()
        imagen.save(salida, "PNG")
        return SimpleUploadedFile("firma.png", salida.getvalue(), content_type="image/png")

    def aceptar(self):
        return self.api.post("/api/v1/perfil/aceptar/", {"version_id": self.terminos.pk, "acepto": True}, format="json")

    def firmar(self):
        return self.api.post("/api/v1/perfil/firmar/", {"firma": self.firma(), "confirmar": "true"}, format="multipart")

    def test_listado_no_expone_password_y_contratista_no_administra(self):
        respuesta = self.api.get("/api/v1/usuarios/")
        self.assertEqual(respuesta.status_code, 200)
        for usuario in respuesta.data["results"]:
            self.assertNotIn("password", usuario)
        self.api.force_login(self.cliente)
        for recurso in ("usuarios", "solicitudes"):
            self.assertEqual(self.api.get(f"/api/v1/{recurso}/").status_code, 403)

    def test_alta_interna_valida_password_y_no_expone_hash(self):
        datos = {"username": "nuevo_interno", "rut": "55555555-5", "email": "nuevo@example.com", "rol": "BODEGUERO",
            "password1": "Seguro!NuevoComponente4820", "password2": "Seguro!NuevoComponente4820", "motivo": "Nuevo equipo"}
        respuesta = self.api.post("/api/v1/usuarios/", datos, format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        usuario = Usuario.objects.get(pk=respuesta.data["id"])
        self.assertTrue(usuario.check_password(datos["password1"]))
        self.assertFalse(usuario.is_superuser)
        self.assertNotIn("password", respuesta.data)
        self.assertTrue(usuario.historial_administracion.filter(accion="CREACION").exists())
        datos["username"] = "invalido"
        datos["rut"] = "66666666-6"
        datos["password2"] = "Diferente!123"
        self.assertEqual(self.api.post("/api/v1/usuarios/", datos, format="json").status_code, 400)

    def test_patch_preserva_omitidos_y_rechaza_campos_protegidos(self):
        ruta = f"/api/v1/usuarios/{self.interno.pk}/"
        respuesta = self.api.patch(ruta, {"email": "despues@example.com", "motivo": "Corregir correo"}, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.interno.refresh_from_db()
        self.assertEqual(self.interno.first_name, "Original")
        self.assertEqual(self.interno.email, "despues@example.com")
        for campo, valor in (("is_superuser", True), ("rut", "99999999-9"), ("empresa", self.empresa.pk), ("password", "Cambio!123")):
            self.assertEqual(self.api.patch(ruta, {campo: valor, "motivo": "Intento"}, format="json").status_code, 400)

    def test_no_modifica_cuenta_propia_ni_contratista_como_interno(self):
        self.assertEqual(self.accion(self.admin.pk, "suspender", motivo="Prueba", confirmar=True).status_code, 400)
        respuesta = self.accion(self.cliente.pk, "permisos", rol="BODEGUERO", permisos=[], motivo="Intento")
        self.assertEqual(respuesta.status_code, 400)

    def test_permisos_catalogo_asignacion_y_historial(self):
        catalogo = self.api.get("/api/v1/usuarios/permisos-disponibles/")
        self.assertEqual(catalogo.status_code, 200)
        permiso = Permission.objects.get(content_type__app_label="maquinaria", codename="view_mantenimiento")
        respuesta = self.accion(self.interno.pk, "permisos", rol="BODEGUERO", permisos=[permiso.pk], motivo="Asignar tarea")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual([p["id"] for p in respuesta.data["permisos"]], [permiso.pk])
        self.assertEqual(self.api.get(f"/api/v1/usuarios/{self.interno.pk}/historial/").data["count"], 1)
        ajeno = Permission.objects.filter(content_type__app_label="auth").first()
        self.assertEqual(self.accion(self.interno.pk, "permisos", rol="BODEGUERO", permisos=[ajeno.pk], motivo="Intento").status_code, 400)

    def test_administrador_limitado_no_otorga_superusuario(self):
        gestor = Usuario.objects.create_user(username="gestor_limitado", rut="88888888-8", rol="ADMINISTRADOR")
        gestor.user_permissions.add(Permission.objects.get(content_type__app_label="maquinaria", codename="gestionar_usuarios"))
        self.api.force_login(gestor)
        self.assertEqual(self.accion(self.interno.pk, "permisos", rol="ADMINISTRADOR", permisos=[], superusuario=True, motivo="Intento").status_code, 400)
        self.assertEqual(self.accion(self.admin.pk, "suspender", motivo="Intento", confirmar=True).status_code, 403)

    def test_suspension_y_reactivacion_no_aprueban_solicitud(self):
        self.assertEqual(self.accion(self.pendiente.pk, "suspender", motivo="Revision", confirmar=True).status_code, 200)
        self.assertEqual(self.accion(self.pendiente.pk, "reactivar", motivo="Revision terminada", confirmar=True).status_code, 200)
        self.pendiente.refresh_from_db()
        self.assertEqual(self.pendiente.estado_aprobacion, "PENDIENTE")
        otro = APIClient()
        otro.force_authenticate(user=self.pendiente)
        self.assertEqual(otro.get("/api/v1/perfil/").status_code, 403)

    def test_rechazo_exige_motivo_y_aprobacion_no_se_repite(self):
        self.assertEqual(self.revisar("rechazar", motivo="").status_code, 400)
        respuesta = self.revisar("aprobar", motivo="Vinculo confirmado")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["estado_aprobacion"], "APROBADO")
        self.assertEqual(self.revisar("rechazar", motivo="Intento repetido").status_code, 400)
        self.assertEqual(self.api.get(f"/api/v1/solicitudes/{self.pendiente.pk}/historial/").data["count"], 1)

    def test_rechazo_login_limitado_consulta_y_reenvio(self):
        self.assertEqual(self.revisar("rechazar", motivo="Falta acreditar empresa").status_code, 200)
        self.api.logout()
        respuesta = self.api.post("/api/v1/acceso/ingresar/", {"username": self.pendiente.username,
            "password": "Seguro!Componente4820"}, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["acceso"], "solicitud")
        self.assertNotIn("_auth_user_id", self.api.session)
        self.assertEqual(self.api.get("/api/v1/perfil/").status_code, 403)
        estado = self.api.get("/api/v1/acceso/solicitud/")
        self.assertEqual(estado.status_code, 200)
        self.assertEqual(estado.data["solicitud"]["motivo_revision"], "Falta acreditar empresa")
        respuesta = self.api.post("/api/v1/acceso/reenviar/", {"rut_empresa": self.empresa.rut,
            "razon_social": self.empresa.razon_social, "comentario": "Adjunto antecedentes corregidos"}, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["estado_aprobacion"], "PENDIENTE")
        self.assertEqual(self.api.post("/api/v1/acceso/reenviar/", {"rut_empresa": self.empresa.rut,
            "razon_social": self.empresa.razon_social, "comentario": "Otra vez"}, format="json").status_code, 400)

    def test_registro_publico_pendiente_y_rechaza_privilegios(self):
        self.api.logout()
        datos = {"username": "nuevo_contratista", "rut": "55555555-5", "email": "nuevo@example.com",
            "rut_empresa": "77777777-7", "razon_social": "Empresa API", "password1": "Seguro!NuevoComponente4820",
            "password2": "Seguro!NuevoComponente4820"}
        self.assertEqual(self.api.post("/api/v1/acceso/registro/", {**datos, "is_superuser": True}, format="json").status_code, 400)
        respuesta = self.api.post("/api/v1/acceso/registro/", datos, format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        usuario = Usuario.objects.get(username=datos["username"])
        self.assertFalse(usuario.is_active)
        self.assertFalse(usuario.is_superuser)
        self.assertEqual(usuario.estado_aprobacion, "PENDIENTE")

    def test_perfil_patch_no_cambia_identidad_ni_privilegios(self):
        self.api.force_login(self.cliente)
        self.assertEqual(self.api.patch("/api/v1/perfil/", {"first_name": "Nuevo"}, format="json").status_code, 200)
        self.assertEqual(self.api.patch("/api/v1/perfil/", {"rol": "ADMINISTRADOR"}, format="json").status_code, 400)
        self.assertEqual(self.api.get("/api/v1/perfil/").data["usuario"]["first_name"], "Nuevo")
        for ruta in ("aceptar", "firmar"):
            self.assertEqual(self.api.patch(f"/api/v1/perfil/{ruta}/", {}, format="json").status_code, 405)

    def test_firma_exige_aceptacion_y_conserva_comprobante_privado(self):
        self.api.force_login(self.cliente)
        self.assertEqual(self.firmar().status_code, 400)
        self.assertEqual(self.aceptar().status_code, 200)
        respuesta = self.firmar()
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        pk = respuesta.data["id"]
        self.assertNotIn("firma", respuesta.data)
        self.assertEqual(self.api.get("/api/v1/comprobantes/").data["count"], 1)
        archivo = self.api.get(f"/api/v1/comprobantes/{pk}/firma/", HTTP_ACCEPT="image/png")
        self.assertEqual(archivo.status_code, 200)
        self.assertTrue(b"".join(archivo.streaming_content).startswith(b"\x89PNG"))
        self.api.force_login(self.interno)
        self.assertEqual(self.api.get(f"/api/v1/comprobantes/{pk}/").status_code, 404)
        self.assertEqual(self.api.get(f"/api/v1/comprobantes/{pk}/firma/", HTTP_ACCEPT="image/png").status_code, 404)

    def test_version_cambiada_y_aceptacion_vencida_impiden_firma(self):
        self.api.force_login(self.cliente)
        self.aceptar()
        TerminosCondiciones.objects.create(version="CUENTAS-2", contenido="Nuevas condiciones")
        self.assertEqual(self.firmar().status_code, 400)
        self.assertEqual(self.aceptar().status_code, 400)
        sesion = self.api.session
        sesion[CLAVE_ACEPTACION] = {"usuario_id": self.cliente.pk, "terminos_id": self.terminos.pk,
            "aceptado_en": (timezone.now() - timedelta(hours=1)).isoformat()}
        sesion.save()
        self.assertEqual(self.firmar().status_code, 400)
        self.assertFalse(AceptacionTerminos.objects.exists())

    def test_publicar_terminos_no_edita_versiones_previas(self):
        respuesta = self.api.post("/api/v1/condiciones/", {"version": "CUENTAS-2", "contenido": "Texto nuevo"}, format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(TerminosCondiciones.objects.count(), 2)
        self.api.force_login(self.cliente)
        self.assertEqual(self.api.post("/api/v1/condiciones/", {"version": "Intento", "contenido": "Texto"}, format="json").status_code, 403)

    def test_csrf_anonimo_login_registro_y_sesion_limitada(self):
        cliente = APIClient(enforce_csrf_checks=True)
        ruta = "/api/v1/acceso/ingresar/"
        datos = {"username": self.pendiente.username, "password": "Seguro!Componente4820"}
        self.assertEqual(cliente.post(ruta, datos, format="json").status_code, 403)
        respuesta = cliente.get("/api/v1/acceso/csrf/")
        self.assertEqual(respuesta.status_code, 200)
        respuesta = cliente.post(ruta, datos, format="json", HTTP_X_CSRFTOKEN=respuesta.data["csrfToken"])
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(cliente.post("/api/v1/acceso/reenviar/", {}, format="json").status_code, 403)
        self.assertEqual(cliente.post("/api/v1/acceso/registro/", {}, format="json").status_code, 403)

    def test_login_normal_y_logout(self):
        self.api.logout()
        respuesta = self.api.post("/api/v1/acceso/ingresar/", {"username": self.cliente.username,
            "password": "Seguro!Componente4820"}, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["acceso"], "sistema")
        self.assertEqual(self.api.get("/api/v1/perfil/").status_code, 200)
        self.assertEqual(self.api.post("/api/v1/acceso/salir/", {}, format="json").status_code, 200)
        self.assertEqual(self.api.get("/api/v1/perfil/").status_code, 403)

    def test_json_no_objeto_y_campos_desconocidos_devuelven_400(self):
        for ruta, metodo in [("/api/v1/usuarios/", self.api.post),
                            (f"/api/v1/usuarios/{self.interno.pk}/", self.api.patch),
                            (f"/api/v1/solicitudes/{self.pendiente.pk}/aprobar/", self.api.post)]:
            respuesta = metodo(ruta, ["invalido"], format="json")
            self.assertEqual(respuesta.status_code, 400, respuesta.data)
        self.assertEqual(self.revisar("aprobar", motivo="Prueba", is_superuser=True).status_code, 400)

    def test_filtros_solicitudes_y_usuarios_no_ignoran_parametros(self):
        self.assertEqual(self.api.get("/api/v1/solicitudes/?estado=pendiente").data["count"], 1)
        self.assertEqual(self.api.get("/api/v1/solicitudes/?estado=aprobada").data["count"], 1)
        for ruta in ("solicitudes/?rol=BODEGUERO", "usuarios/?estado=inexistente", "condiciones/?otro=1", "comprobantes/?otro=1"):
            self.assertEqual(self.api.get("/api/v1/" + ruta).status_code, 400)
        self.assertEqual(self.api.get("/api/v1/usuarios/?estado=pendiente").data["count"], 1)
        self.assertEqual(self.api.get("/api/v1/usuarios/?page=999").status_code, 404)

    def test_csrf_anonimo_falla_en_json_y_sesion_suspendida_no_ingresa(self):
        cliente = APIClient(enforce_csrf_checks=True)
        respuesta = cliente.post("/api/v1/acceso/ingresar/", {}, format="json")
        self.assertEqual(respuesta.status_code, 403)
        self.assertTrue(respuesta["Content-Type"].startswith("application/json"))
        self.cliente.suspendida = True
        self.cliente.save(update_fields=["suspendida"])
        self.api.logout()
        respuesta = self.api.post("/api/v1/acceso/ingresar/", {"username": self.cliente.username,
            "password": "Seguro!Componente4820"}, format="json")
        self.assertEqual(respuesta.status_code, 400)
        self.assertNotIn("_auth_user_id", self.api.session)

    def test_aceptacion_repetida_no_duplica_comprobante(self):
        self.api.force_login(self.cliente)
        self.aceptar()
        self.assertEqual(self.firmar().status_code, 200)
        self.aceptar()
        self.assertEqual(self.firmar().status_code, 200)
        self.assertEqual(AceptacionTerminos.objects.count(), 1)

    def test_administracion_exige_motivo_confirmacion_y_no_elimina(self):
        for datos in [{"motivo": "Prueba"}, {"motivo": "", "confirmar": True}]:
            self.assertEqual(self.accion(self.interno.pk, "suspender", **datos).status_code, 400)
        for recurso, pk in (("usuarios", self.interno.pk), ("solicitudes", self.pendiente.pk), ("condiciones", self.terminos.pk)):
            self.assertEqual(self.api.delete(f"/api/v1/{recurso}/{pk}/").status_code, 405)
