from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from .models import Usuario, TerminosCondiciones, AceptacionTerminos
from .condiciones import CLAVE_ACEPTACION


class PerfilPorRolTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superusuario = Usuario.objects.create_superuser(username="super_perfil", rut="11111111-1", password="Seguro!4820")
        cls.administrador = Usuario.objects.create_user(username="admin_perfil", rut="22222222-2", rol="ADMINISTRADOR")
        cls.bodeguero = Usuario.objects.create_user(username="bodega_perfil", rut="33333333-3", rol="BODEGUERO")
        cls.staff = Usuario.objects.create_user(username="staff_perfil", rut="44444444-4", is_staff=True, estado_aprobacion="APROBADO")
        cls.contratista = Usuario.objects.create_user(username="contratista_perfil", rut="55555555-5", estado_aprobacion="APROBADO")
        cls.terminos = TerminosCondiciones.objects.create(version="PERFIL-ROL", contenido="Condiciones para contratistas")

    def test_personal_ve_datos_y_rol_sin_seccion_de_firma(self):
        for usuario in (self.superusuario, self.administrador, self.bodeguero, self.staff):
            self.client.force_login(usuario)
            respuesta = self.client.get("/perfil/")
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, "Rol:")
            self.assertNotContains(respuesta, "<h2>Condiciones y firma</h2>")
            self.assertNotContains(respuesta, "Mis comprobantes")
            self.assertNotContains(respuesta, "Condiciones para contratistas")
            self.assertFalse(respuesta.context["perfil_contratista"])
            self.assertNotContains(self.client.get("/"), "Completar condiciones y firma en mi perfil")

    def test_personal_no_acepta_ni_firma_por_html_o_api(self):
        for usuario in (self.superusuario, self.administrador, self.bodeguero, self.staff):
            self.client.force_login(usuario)
            self.assertEqual(self.client.post("/perfil/aceptar/", {"acepto": "si", "version_id": self.terminos.pk}).status_code, 403)
            self.assertEqual(self.client.post("/perfil/firmar/", {}).status_code, 403)
            self.assertNotIn(CLAVE_ACEPTACION, self.client.session)
            api = APIClient()
            api.force_login(usuario)
            perfil = api.get("/api/v1/perfil/")
            self.assertEqual(perfil.status_code, 200)
            self.assertFalse(perfil.data["puede_firmar_condiciones"])
            self.assertNotIn("condiciones_vigentes", perfil.data)
            self.assertNotIn("aceptaciones", perfil.data)
            respuesta = api.post("/api/v1/perfil/aceptar/", {"acepto": True, "version_id": self.terminos.pk}, format="json")
            self.assertEqual(respuesta.status_code, 403)
            self.assertTrue(respuesta["Content-Type"].startswith("application/json"))
            self.assertEqual(api.post("/api/v1/perfil/firmar/", {}, format="multipart").status_code, 403)
            self.assertNotIn(CLAVE_ACEPTACION, api.session)
        self.assertFalse(AceptacionTerminos.objects.exists())

    def test_contratista_conserva_condiciones_y_aceptacion(self):
        self.client.force_login(self.contratista)
        self.assertContains(self.client.get("/"), "Completar condiciones y firma en mi perfil")
        self.assertContains(self.client.get("/perfil/"), "<h2>Condiciones y firma</h2>")
        self.assertEqual(self.client.post("/perfil/aceptar/", {"acepto": "si", "version_id": self.terminos.pk}).status_code, 302)
        self.assertIn(CLAVE_ACEPTACION, self.client.session)
        api = APIClient()
        api.force_login(self.contratista)
        self.assertEqual(api.get("/api/v1/perfil/").data["condiciones_vigentes"]["id"], self.terminos.pk)
        self.assertEqual(api.post("/api/v1/perfil/aceptar/", {"acepto": True, "version_id": self.terminos.pk}, format="json").status_code, 200)

    def test_personal_autorizado_sigue_publicando_y_consultando_comprobantes(self):
        ahora = timezone.now()
        comprobante = AceptacionTerminos.objects.create(usuario=self.contratista, terminos=self.terminos,
            aceptado_en=ahora, firmado_en=ahora, firma="prueba.png")
        self.client.force_login(self.superusuario)
        self.assertEqual(self.client.get("/condiciones/publicar/").status_code, 200)
        self.assertEqual(self.client.get(f"/comprobantes/{comprobante.pk}/").status_code, 200)
        api = APIClient()
        api.force_login(self.superusuario)
        self.assertEqual(api.get(f"/api/v1/comprobantes/{comprobante.pk}/").status_code, 200)
