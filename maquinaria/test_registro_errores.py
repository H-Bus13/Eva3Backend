from django.test import TestCase
from .models import Usuario, Empresa


class RegistroErroresVisiblesTests(TestCase):
    def datos(self):
        return {"username": "nuevo_registro_visible", "first_name": "Nombre", "last_name": "Apellido",
            "email": "nombre@example.com", "rut": "12345678-5", "rut_empresa": "77777777-7",
            "razon_social": "Empresa de pruebas", "password1": "ClaveSegura!4820",
            "password2": "ClaveSegura!4820"}

    def test_correo_invalido_muestra_motivo_y_resumen_sin_crear_cuenta(self):
        datos = self.datos()
        datos["email"] = "correo-sin-arroba"
        respuesta = self.client.post("/registro/", datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "No se pudo enviar la solicitud")
        self.assertContains(respuesta, "Ingresa un correo válido")
        self.assertContains(respuesta, 'href="#id_email"')
        self.assertContains(respuesta, "novalidate")
        self.assertNotContains(respuesta, datos["password1"])
        self.assertIn("email", respuesta.context["form"].errors)
        self.assertFalse(Usuario.objects.exists())
        self.assertFalse(Empresa.objects.exists())

    def test_post_vacio_tambien_muestra_errores_obligatorios(self):
        respuesta = self.client.post("/registro/", {})
        self.assertTrue(respuesta.context["form"].is_bound)
        self.assertContains(respuesta, "Ingresa tu correo electrónico.")
        self.assertContains(respuesta, "data-resumen-errores")
        self.assertIn("username", respuesta.context["form"].errors)

    def test_registro_valido_sigue_pendiente_y_sin_privilegios(self):
        respuesta = self.client.post("/registro/", self.datos())
        self.assertEqual(respuesta.status_code, 302)
        usuario = Usuario.objects.get()
        self.assertEqual(usuario.estado_aprobacion, "PENDIENTE")
        self.assertFalse(usuario.is_active)
        self.assertFalse(usuario.is_superuser)
