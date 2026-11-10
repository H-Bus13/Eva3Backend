from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from .models import (
    AceptacionTerminos, Arriendo, Bodega, Empresa, Maquinaria,
    Obra, SesionUso, TerminosCondiciones, Usuario,
)


class ReglasModelosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ahora = timezone.now()
        cls.empresa = Empresa.objects.create(
            rut="76123456-0", razon_social="Contratista de prueba",
        )
        cls.usuario = Usuario.objects.create_user(
            username="responsable", rut="12345678-5", empresa=cls.empresa,
        )
        cls.obra = Obra.objects.create(nombre="Obra", direccion="Dirección")
        cls.bodega = Bodega.objects.create(nombre="Central", obra=cls.obra)
        cls.maquina = Maquinaria.objects.create(
            codigo="M-001", nombre="Generador", bodega=cls.bodega,
        )
        cls.terminos = TerminosCondiciones.objects.create(
            version="1", contenido="Condiciones de prueba",
        )
        cls.aceptacion = AceptacionTerminos.objects.create(
            usuario=cls.usuario, terminos=cls.terminos,
            aceptado_en=cls.ahora, firmado_en=cls.ahora,
            firma="firmas/perfiles/prueba.png",
        )
        cls.arriendo = Arriendo.objects.create(
            maquinaria=cls.maquina, empresa=cls.empresa,
            responsable=cls.usuario, obra_destino=cls.obra,
            aceptacion=cls.aceptacion, entregado_en=cls.ahora,
            devolucion_prevista=cls.ahora + timedelta(days=1),
            tarifa_diaria="20000.00", firma_entrega="firmas/entregas/prueba.png",
        )

    def test_mantencion_se_calcula_desde_ultima_revision(self):
        self.maquina.tiempo_uso_ultima_mantencion = timedelta(hours=650)
        self.maquina.tiempo_uso_acumulado = timedelta(hours=899, minutes=59)
        self.assertFalse(self.maquina.requiere_mantencion_por_uso)
        self.maquina.tiempo_uso_acumulado = timedelta(hours=900)
        self.assertTrue(self.maquina.requiere_mantencion_por_uso)
        self.assertEqual(self.maquina.tiempo_uso_total, timedelta(hours=900))

    def test_contador_incluye_sesion_abierta_sin_escribir_acumulado(self):
        self.maquina.tiempo_uso_acumulado = timedelta(hours=249)
        self.maquina.save()
        SesionUso.objects.create(arriendo=self.arriendo, inicio=self.ahora)
        with patch("maquinaria.models.timezone.now", return_value=self.ahora + timedelta(hours=1)):
            self.assertEqual(self.maquina.tiempo_uso_total, timedelta(hours=250))
            self.assertTrue(self.maquina.requiere_mantencion_por_uso)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=249))

    def test_sesion_cerrada_no_se_vuelve_a_sumar(self):
        self.maquina.tiempo_uso_acumulado = timedelta(hours=10)
        SesionUso.objects.create(
            arriendo=self.arriendo, inicio=self.ahora,
            fin=self.ahora + timedelta(hours=2),
        )
        self.assertEqual(self.maquina.tiempo_uso_total, timedelta(hours=10))

    def test_no_se_pueden_abrir_dos_arriendos_de_la_misma_maquina(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.arriendo.pk = None
            self.arriendo.save(force_insert=True)

    def test_no_se_pueden_abrir_dos_sesiones_del_mismo_arriendo(self):
        SesionUso.objects.create(arriendo=self.arriendo)
        with self.assertRaises(IntegrityError), transaction.atomic():
            SesionUso.objects.create(arriendo=self.arriendo)

    def test_no_se_puede_firmar_antes_de_aceptar(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            AceptacionTerminos.objects.create(
                usuario=self.usuario, terminos=self.terminos,
                aceptado_en=self.ahora,
                firmado_en=self.ahora - timedelta(seconds=1),
                firma="firmas/perfiles/prueba.png",
            )

    def test_no_se_permite_plazo_anterior_a_la_entrega(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.arriendo.devolucion_prevista = self.ahora - timedelta(days=1)
            self.arriendo.save()

    def test_arriendo_devuelto_no_se_considera_atrasado(self):
        with patch("maquinaria.models.timezone.now", return_value=self.ahora + timedelta(days=2)):
            self.assertTrue(self.arriendo.esta_atrasado)
            self.arriendo.devuelto_en = self.ahora + timedelta(days=1)
            self.assertFalse(self.arriendo.esta_atrasado)

class RegistroAprobacionTests(TestCase):
    def datos_registro(self, **cambios):
        datos = {
            "username": "nuevo", "first_name": "Ana", "last_name": "Soto",
            "email": "ana@example.com", "rut": "12.345.678-5",
            "rut_empresa": "76.123.456-0", "razon_social": "Constructora",
            "password1": "ClaveSegura!4820", "password2": "ClaveSegura!4820",
        }
        datos.update(cambios)
        return datos

    def registrar(self):
        respuesta = self.client.post("/registro/", self.datos_registro())
        self.assertRedirects(respuesta, "/ingresar/")
        return Usuario.objects.get(username="nuevo")

    def admin(self):
        admin = Usuario.objects.create_superuser(
            username="administrador", rut="11111111-1", password="ClaveAdmin!4820",
        )
        self.client.force_login(admin)
        return admin

    def test_registro_queda_pendiente_sin_privilegios(self):
        datos = self.datos_registro(
            rol="ADMINISTRADOR", is_superuser="true", is_staff="true",
            is_active="true", estado_aprobacion="APROBADO",
        )
        self.client.post("/registro/", datos)
        usuario = Usuario.objects.get(username="nuevo")
        self.assertFalse(usuario.is_active)
        self.assertFalse(usuario.is_staff)
        self.assertFalse(usuario.is_superuser)
        self.assertEqual(usuario.rol, Usuario.Rol.CONTRATISTA)
        self.assertEqual(usuario.estado_aprobacion, "PENDIENTE")
        self.assertEqual(usuario.rut, "12345678-5")
        self.assertEqual(usuario.empresa.rut, "76123456-0")
        self.assertTrue(usuario.check_password("ClaveSegura!4820"))

    def test_rut_incorrecto_no_crea_cuenta_ni_empresa(self):
        respuesta = self.client.post("/registro/", self.datos_registro(rut="12345678-9"))
        self.assertContains(respuesta, "dígito verificador")
        self.assertFalse(Usuario.objects.exists())
        self.assertFalse(Empresa.objects.exists())

    def test_rut_formateado_duplicado_se_rechaza(self):
        self.registrar()
        respuesta = self.client.post("/registro/", self.datos_registro(username="otro", rut="123456785"))
        self.assertContains(respuesta, "Ya existe una cuenta con ese RUT")
        self.assertEqual(Usuario.objects.count(), 1)

    def test_registro_no_modifica_empresa_existente(self):
        empresa = Empresa.objects.create(rut="76.123.456-0", razon_social="Original", bloqueada=True)
        usuario = self.registrar()
        empresa.refresh_from_db()
        self.assertEqual(usuario.empresa_id, empresa.pk)
        self.assertEqual(empresa.razon_social, "Original")
        self.assertTrue(empresa.bloqueada)

    def test_pendiente_no_puede_autenticarse_aunque_este_activo(self):
        usuario = self.registrar()
        usuario.is_active = True
        usuario.save()
        self.assertFalse(self.client.login(username="nuevo", password="ClaveSegura!4820"))

    def test_aprobacion_habilita_login_y_guarda_responsable(self):
        usuario = self.registrar()
        admin = self.admin()
        respuesta = self.client.post(f"/cuentas/{usuario.pk}/revisar/", {"accion": "aprobar", "motivo": "Identidad verificada"})
        self.assertRedirects(respuesta, "/cuentas/pendientes/")
        usuario.refresh_from_db()
        self.assertTrue(usuario.is_active)
        self.assertEqual(usuario.estado_aprobacion, "APROBADO")
        self.assertEqual(usuario.revisado_por, admin)
        self.assertIsNotNone(usuario.revisado_en)
        self.assertEqual(usuario.motivo_revision, "Identidad verificada")
        self.client.logout()
        self.assertTrue(self.client.login(username="nuevo", password="ClaveSegura!4820"))
        self.assertContains(self.client.get("/"), "Bienvenido")

    def test_rechazo_exige_motivo_y_mantiene_cuenta_inactiva(self):
        usuario = self.registrar()
        self.admin()
        url = f"/cuentas/{usuario.pk}/revisar/"
        # El servidor mantiene el listado y el aviso aunque no se ejecute JS.
        for motivo in ("", "   "):
            respuesta = self.client.post(url, {"accion": "rechazar", "motivo": motivo}, follow=True)
            self.assertRedirects(respuesta, "/cuentas/pendientes/")
            self.assertContains(respuesta, "Indica el motivo del rechazo.")
            self.assertContains(respuesta, "Solicitudes pendientes")
            usuario.refresh_from_db()
            self.assertEqual(usuario.estado_aprobacion, "PENDIENTE")
            self.assertFalse(usuario.is_active)
            self.assertIsNone(usuario.revisado_en)
            self.assertIsNone(usuario.revisado_por)
        self.client.post(url, {"accion": "rechazar", "motivo": "No se acreditó el vínculo"})
        usuario.refresh_from_db()
        self.assertFalse(usuario.is_active)
        self.assertEqual(usuario.estado_aprobacion, "RECHAZADO")
        self.assertFalse(self.client.login(username="nuevo", password="ClaveSegura!4820"))

    def test_rol_administrador_sin_permiso_no_puede_revisar(self):
        usuario = self.registrar()
        impostor = Usuario.objects.create_user(username="sinpermiso", rut="22222222-2", rol=Usuario.Rol.ADMINISTRADOR)
        self.client.force_login(impostor)
        self.assertEqual(self.client.get("/cuentas/pendientes/").status_code, 403)
        self.assertEqual(self.client.post(f"/cuentas/{usuario.pk}/revisar/", {"accion": "aprobar"}).status_code, 403)

    def test_revision_solo_post_y_no_se_puede_repetir(self):
        usuario = self.registrar()
        self.admin()
        url = f"/cuentas/{usuario.pk}/revisar/"
        self.assertEqual(self.client.get(url).status_code, 405)
        self.client.post(url, {"accion": "aprobar"})
        self.assertEqual(self.client.post(url, {"accion": "rechazar", "motivo": "Cambio"}).status_code, 404)

    def test_aprobar_no_desbloquea_la_empresa(self):
        usuario = self.registrar()
        usuario.empresa.bloqueada = True
        usuario.empresa.save()
        self.admin()
        self.client.post(f"/cuentas/{usuario.pk}/revisar/", {"accion": "aprobar"})
        usuario.empresa.refresh_from_db()
        self.assertTrue(usuario.empresa.bloqueada)

    def test_csrf_y_cierre_sesion_por_post(self):
        from django.test import Client
        self.assertEqual(Client(enforce_csrf_checks=True).post("/registro/", self.datos_registro()).status_code, 403)
        self.admin()
        self.assertEqual(self.client.get("/salir/").status_code, 405)
        self.assertRedirects(self.client.post("/salir/"), "/ingresar/")

    def test_paginas_publicas_renderizan(self):
        self.assertContains(self.client.get("/registro/"), "Solicita tu cuenta")
        self.assertContains(self.client.get("/ingresar/"), "Ingresa a BuildCorp")
        self.assertRedirects(self.client.get("/"), "/ingresar/?next=/")

from django.test import override_settings


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class CondicionesFirmaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = Usuario.objects.create_user(
            username="firmante", rut="12345678-5", password="ClaveSegura!4820",
            estado_aprobacion="APROBADO",
        )
        cls.otro = Usuario.objects.create_user(
            username="otro", rut="11111111-1", estado_aprobacion="APROBADO",
        )
        cls.admin = Usuario.objects.create_superuser(
            username="administracion", rut="22222222-2", password="ClaveAdmin!4820",
        )
        cls.terminos = TerminosCondiciones.objects.create(version="1", contenido="Texto original de prueba")

    def setUp(self):
        self.client.force_login(self.usuario)

    def png(self, blanco=False, tamano=(900, 300), formato="PNG"):
        from io import BytesIO
        from PIL import Image, ImageDraw
        from django.core.files.uploadedfile import SimpleUploadedFile
        imagen = Image.new("RGBA", tamano, "white")
        if not blanco:
            ImageDraw.Draw(imagen).line([(20, 80), (100, 150), (180, 60), (220, 140)], fill="black", width=5)
        salida = BytesIO()
        if formato == "JPEG":
            imagen = imagen.convert("RGB")
        imagen.save(salida, format=formato)
        return SimpleUploadedFile("firma.png", salida.getvalue(), content_type="image/png")

    def aceptar(self):
        return self.client.post("/perfil/aceptar/", {"acepto": "si", "version_id": self.terminos.pk})

    def firmar(self, **opciones):
        return self.client.post("/perfil/firmar/", {"firma": self.png(**opciones)})

    def comprobante(self):
        self.aceptar()
        self.firmar()
        return AceptacionTerminos.objects.get(usuario=self.usuario, terminos=self.terminos)

    def test_perfil_muestra_condiciones_y_datos_sin_canvas_antes_de_aceptar(self):
        respuesta = self.client.get("/perfil/")
        self.assertContains(respuesta, "Texto original de prueba")
        self.assertContains(respuesta, 'name="acepto"')
        self.assertNotContains(respuesta, '<canvas')

    def test_aceptacion_obligatoria_y_firma_no_puede_adelantarse(self):
        self.assertEqual(self.client.post("/perfil/aceptar/", {"version_id": self.terminos.pk}).status_code, 400)
        self.assertEqual(self.firmar().status_code, 400)
        self.assertFalse(AceptacionTerminos.objects.exists())

    def test_aceptacion_habilita_canvas_y_firma_guarda_comprobante(self):
        self.assertRedirects(self.aceptar(), "/perfil/")
        self.assertContains(self.client.get("/perfil/"), '<canvas')
        self.assertRedirects(self.firmar(), "/perfil/")
        prueba = AceptacionTerminos.objects.get()
        self.assertEqual(prueba.usuario, self.usuario)
        self.assertEqual(prueba.terminos, self.terminos)
        self.assertGreaterEqual(prueba.firmado_en, prueba.aceptado_en)
        self.assertNotIn("aceptacion_pendiente", self.client.session)
        self.assertContains(self.client.get("/perfil/"), "Ya aceptaste y firmaste esta versión")
        self.assertContains(self.client.get(f"/comprobantes/{prueba.pk}/"), "Texto original de prueba")
        respuesta = self.client.get(f"/comprobantes/{prueba.pk}/firma/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta["Content-Type"], "image/png")
        self.assertIn("no-store", respuesta["Cache-Control"])
        self.assertTrue(b"".join(respuesta.streaming_content).startswith(b"\x89PNG"))

    def test_rechaza_firmas_vacias_corruptas_grandes_y_formato_falso(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.aceptar()
        archivos = [
            self.png(blanco=True), self.png(tamano=(100, 50)), self.png(formato="JPEG"),
            SimpleUploadedFile("firma.png", b"no es PNG", content_type="image/png"),
            SimpleUploadedFile("firma.png", b"x" * (500 * 1024 + 1), content_type="image/png"),
        ]
        for archivo in archivos:
            with self.subTest(nombre=archivo.name, tamano=archivo.size):
                respuesta = self.client.post("/perfil/firmar/", {"firma": archivo}, follow=True)
                self.assertEqual(respuesta.status_code, 200)
                self.assertFalse(AceptacionTerminos.objects.exists())
                self.assertTrue(list(respuesta.context["messages"]))

    def test_imagen_transparente_vacia_se_rechaza(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.aceptar()
        salida = BytesIO()
        Image.new("RGBA", (900, 300), (0, 0, 0, 0)).save(salida, format="PNG")
        self.client.post("/perfil/firmar/", {"firma": SimpleUploadedFile("vacia.png", salida.getvalue())})
        self.assertFalse(AceptacionTerminos.objects.exists())

    def test_aceptacion_vencida_futura_invalida_o_ajena_no_firma(self):
        for fecha in [(timezone.now() - timedelta(minutes=31)).isoformat(),
                      (timezone.now() + timedelta(minutes=1)).isoformat(), "invalida", None]:
            with self.subTest(fecha=fecha):
                self.aceptar()
                sesion = self.client.session
                pendiente = sesion["aceptacion_pendiente"]
                pendiente["aceptado_en"] = fecha
                sesion["aceptacion_pendiente"] = pendiente
                sesion.save()
                self.assertEqual(self.firmar().status_code, 400)
        self.aceptar()
        sesion = self.client.session
        pendiente = sesion["aceptacion_pendiente"]
        pendiente["usuario_id"] = self.otro.pk
        sesion["aceptacion_pendiente"] = pendiente
        sesion.save()
        self.assertEqual(self.firmar().status_code, 400)

    def test_version_nueva_invalida_aceptacion_y_conserva_historial(self):
        prueba = self.comprobante()
        self.aceptar()
        nueva = TerminosCondiciones.objects.create(version="2", contenido="Condiciones nuevas")
        respuesta = self.client.get("/perfil/")
        self.assertIsNone(respuesta.context["comprobante"])
        self.assertFalse(respuesta.context["puede_firmar"])
        self.assertEqual(self.aceptar().status_code, 400)
        self.assertEqual(self.firmar().status_code, 400)
        self.assertEqual(AceptacionTerminos.objects.count(), 1)
        self.assertContains(self.client.get(f"/comprobantes/{prueba.pk}/"), "Texto original de prueba")
        self.terminos = nueva
        self.aceptar()
        self.firmar()
        self.assertEqual(AceptacionTerminos.objects.count(), 2)

    def test_envio_repetido_no_duplica_comprobante(self):
        self.comprobante()
        self.aceptar()
        self.firmar()
        self.assertEqual(AceptacionTerminos.objects.count(), 1)

    def test_firma_y_comprobante_ajenos_no_son_publicos(self):
        prueba = self.comprobante()
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(f"/comprobantes/{prueba.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/comprobantes/{prueba.pk}/firma/").status_code, 404)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(f"/comprobantes/{prueba.pk}/").status_code, 200)
        respuesta = self.client.get(f"/comprobantes/{prueba.pk}/firma/")
        self.assertEqual(respuesta.status_code, 200)
        # Consumir el streaming deja que el cliente de pruebas cierre la
        # respuesta sin disparar el cierre de la conexión de su transacción.
        self.assertTrue(b"".join(respuesta.streaming_content).startswith(b"\x89PNG"))
        self.client.logout()
        self.assertEqual(self.client.get(f"/comprobantes/{prueba.pk}/firma/").status_code, 302)
        self.assertEqual(self.client.get(f"/media/{prueba.firma.name}").status_code, 404)

    def test_publicacion_exige_permiso_y_no_modifica_version_anterior(self):
        self.assertEqual(self.client.get("/condiciones/publicar/").status_code, 403)
        self.assertEqual(self.client.post("/condiciones/publicar/", {"version": "2", "contenido": "Intruso"}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get("/condiciones/publicar/"), "Ejemplo académico")
        respuesta = self.client.post("/condiciones/publicar/", {"version": "2", "contenido": "Nuevo texto", "publicado_por": self.otro.pk})
        self.assertRedirects(respuesta, "/condiciones/publicar/")
        self.assertEqual(TerminosCondiciones.objects.get(version="2").publicado_por, self.admin)
        self.terminos.refresh_from_db()
        self.assertEqual(self.terminos.contenido, "Texto original de prueba")
        respuesta = self.client.post("/condiciones/publicar/", {"version": "2", "contenido": "Intento de editar"})
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(TerminosCondiciones.objects.get(version="2").contenido, "Nuevo texto")

    def test_sin_condiciones_publicadas_no_permite_aceptar(self):
        TerminosCondiciones.objects.all().delete()
        self.assertContains(self.client.get("/perfil/"), "Todavía no hay condiciones publicadas")
        self.assertEqual(self.aceptar().status_code, 400)
        self.assertEqual(self.firmar().status_code, 400)

    def test_csrf_y_metodos_http(self):
        from django.test import Client
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.usuario)
        self.assertEqual(estricto.post("/perfil/aceptar/", {"acepto": "si", "version_id": self.terminos.pk}).status_code, 403)
        self.assertEqual(self.client.get("/perfil/aceptar/").status_code, 405)
        self.assertEqual(self.client.get("/perfil/firmar/").status_code, 405)

    def test_archivo_se_elimina_si_falla_guardado_en_base(self):
        from django.core.files.storage import default_storage
        self.aceptar()
        try:
            anteriores = set(default_storage.listdir("firmas/perfiles")[1])
        except FileNotFoundError:
            anteriores = set()
        with patch("maquinaria.models.AceptacionTerminos.save", side_effect=RuntimeError("Fallo simulado")):
            with self.assertRaises(RuntimeError):
                self.firmar()
        self.assertFalse(AceptacionTerminos.objects.exists())
        self.assertEqual(set(default_storage.listdir("firmas/perfiles")[1]), anteriores)




class ConsultaSolicitudTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(rut="76123456-0", razon_social="Constructora original", bloqueada=True)
        cls.usuario = Usuario.objects.create_user(
            username="solicitante", rut="12345678-5", password="ClaveConsulta!4820",
            empresa=cls.empresa, estado_aprobacion="RECHAZADO", is_active=False,
            motivo_revision="Debes acreditar tu relación con la empresa.",
        )
        cls.admin = Usuario.objects.create_superuser(
            username="admin_solicitudes", rut="11111111-1", password="ClaveAdmin!4820",
        )

    def consultar(self, **cambios):
        datos = {"username": "solicitante", "password": "ClaveConsulta!4820"}
        datos.update(cambios)
        return self.client.post("/ingresar/", datos)

    def datos_reenvio(self, **cambios):
        datos = {"rut_empresa": "76.123.456-0", "razon_social": "No sobrescribir",
                 "comentario": "Adjunto antecedentes corregidos para nueva revisión."}
        datos.update(cambios)
        return datos

    def test_rechazado_ve_motivo_sin_obtener_sesion_normal(self):
        self.assertRedirects(self.consultar(), "/solicitud/")
        respuesta = self.client.get("/solicitud/")
        self.assertContains(respuesta, "Debes acreditar tu relación con la empresa.")
        self.assertContains(respuesta, "Corregir y reenviar")
        self.assertNotContains(respuesta, '>Mi perfil</a>')
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn("consulta_solicitud", self.client.session)
        self.assertFalse(respuesta.wsgi_request.user.is_authenticated)
        self.assertIn("no-store", respuesta["Cache-Control"])
        self.usuario.refresh_from_db()
        self.assertFalse(self.usuario.is_active)

    def test_pendiente_ve_estado_sin_formulario_de_reenvio(self):
        self.usuario.estado_aprobacion = "PENDIENTE"
        self.usuario.save()
        self.consultar()
        self.assertContains(self.client.get("/solicitud/"), "pendiente de revisión")
        self.assertNotContains(self.client.get("/solicitud/"), 'action="/solicitud/reenviar/"')
        respuesta = self.client.post("/solicitud/reenviar/", self.datos_reenvio())
        self.assertRedirects(respuesta, "/solicitud/")
        from .models import HistorialSolicitud
        self.assertFalse(HistorialSolicitud.objects.exists())

    def test_credenciales_incorrectas_no_identifican(self):
        for datos in [{"password": "incorrecta"}, {"username": "noexiste"}]:
            with self.subTest(datos=datos):
                respuesta = self.consultar(**datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertNotIn("consulta_solicitud", self.client.session)
                self.assertNotIn("_auth_user_id", self.client.session)

    def test_acceso_limitado_no_habilita_perfil_firma_ni_administracion(self):
        self.consultar(next="/perfil/")
        for ruta in ["/", "/perfil/", "/cuentas/pendientes/", "/condiciones/publicar/", "/comprobantes/1/"]:
            with self.subTest(ruta=ruta):
                respuesta = self.client.get(ruta, follow=True)
                self.assertEqual(respuesta.request["PATH_INFO"], "/solicitud/")
                self.assertContains(respuesta, "Estado de mi solicitud")
        self.assertEqual(self.client.post("/perfil/aceptar/", {"acepto": "si"}).status_code, 302)
        self.assertEqual(self.client.post("/perfil/firmar/", {}).status_code, 302)
        self.assertFalse(AceptacionTerminos.objects.exists())

    def test_reenvio_conserva_historial_y_no_desbloquea_empresa(self):
        from .models import HistorialSolicitud
        HistorialSolicitud.objects.create(usuario=self.usuario, tipo="RECHAZO", empresa=self.empresa,
                                          registrado_por=self.admin, motivo=self.usuario.motivo_revision)
        self.consultar()
        self.assertRedirects(self.client.post("/solicitud/reenviar/", self.datos_reenvio(
            is_active="true", is_superuser="true", estado_aprobacion="APROBADO", rol="ADMINISTRADOR",
        )), "/solicitud/")
        self.usuario.refresh_from_db()
        self.empresa.refresh_from_db()
        self.assertEqual(self.usuario.estado_aprobacion, "PENDIENTE")
        self.assertFalse(self.usuario.is_active)
        self.assertFalse(self.usuario.is_superuser)
        self.assertEqual(self.usuario.rol, "CONTRATISTA")
        self.assertIsNone(self.usuario.revisado_en)
        self.assertEqual(self.usuario.motivo_revision, "")
        self.assertTrue(self.empresa.bloqueada)
        self.assertEqual(self.empresa.razon_social, "Constructora original")
        self.assertEqual(HistorialSolicitud.objects.count(), 2)
        self.assertEqual(HistorialSolicitud.objects.get(tipo="REENVIO").registrado_por, self.usuario)
        self.assertContains(self.client.get("/solicitud/"), "Debes acreditar tu relación con la empresa.")
        self.client.post("/solicitud/reenviar/", self.datos_reenvio())
        self.assertEqual(HistorialSolicitud.objects.count(), 2)

    def test_puede_corregir_empresa_y_preservar_empresa_anterior(self):
        from .models import HistorialSolicitud
        HistorialSolicitud.objects.create(usuario=self.usuario, tipo="RECHAZO", empresa=self.empresa,
                                          registrado_por=self.admin, motivo="Empresa incorrecta")
        nueva = Empresa.objects.create(rut="11111111-1", razon_social="Empresa correcta")
        self.consultar()
        self.client.post("/solicitud/reenviar/", self.datos_reenvio(rut_empresa="11.111.111-1"))
        self.usuario.refresh_from_db()
        self.assertEqual(self.usuario.empresa_id, nueva.pk)
        self.assertEqual(HistorialSolicitud.objects.get(tipo="RECHAZO").empresa_id, self.empresa.pk)

    def test_rut_invalido_y_comentario_vacio_no_reenvian(self):
        self.consultar()
        for datos in [self.datos_reenvio(rut_empresa="12345678-9"), self.datos_reenvio(comentario="   ")]:
            respuesta = self.client.post("/solicitud/reenviar/", datos)
            self.assertEqual(respuesta.status_code, 200)
            self.assertTrue(respuesta.context["form"].errors)
            self.usuario.refresh_from_db()
            self.assertEqual(self.usuario.estado_aprobacion, "RECHAZADO")

    def test_aprobacion_actualiza_historial_y_exige_ingreso_normal(self):
        from .models import HistorialSolicitud
        self.consultar()
        self.usuario.estado_aprobacion = "PENDIENTE"
        self.usuario.save()
        from django.test import Client
        administrador = Client()
        administrador.force_login(self.admin)
        self.assertContains(administrador.get("/cuentas/pendientes/"), "Historial de la solicitud")
        administrador.post(f"/cuentas/{self.usuario.pk}/revisar/", {"accion": "aprobar", "motivo": "Vínculo acreditado"})
        self.assertEqual(HistorialSolicitud.objects.get().tipo, "APROBACION")
        self.assertContains(self.client.get("/solicitud/"), "Tu solicitud fue aprobada")
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertNotIn("consulta_solicitud", self.client.session)
        self.assertRedirects(self.consultar(), "/")
        self.assertIn("_auth_user_id", self.client.session)

    def test_rechazo_registra_responsable_motivo_y_fecha(self):
        from .models import HistorialSolicitud
        self.usuario.estado_aprobacion = "PENDIENTE"
        self.usuario.save()
        self.client.force_login(self.admin)
        self.client.post(f"/cuentas/{self.usuario.pk}/revisar/", {"accion": "rechazar", "motivo": "Falta autorización"})
        evento = HistorialSolicitud.objects.get()
        self.assertEqual(evento.tipo, "RECHAZO")
        self.assertEqual(evento.registrado_por, self.admin)
        self.assertEqual(evento.motivo, "Falta autorización")
        self.usuario.refresh_from_db()
        self.assertEqual(evento.fecha, self.usuario.revisado_en)

    def test_aprobado_desactivado_no_obtiene_acceso_limitado(self):
        self.usuario.estado_aprobacion = "APROBADO"
        self.usuario.save()
        self.assertEqual(self.consultar().status_code, 200)
        self.assertNotIn("consulta_solicitud", self.client.session)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_consulta_expira_y_cambio_clave_la_invalida(self):
        self.consultar()
        sesion = self.client.session
        datos = sesion["consulta_solicitud"]
        datos["iniciada_en"] = (timezone.now() - timedelta(minutes=31)).isoformat()
        sesion["consulta_solicitud"] = datos
        sesion.save()
        self.assertRedirects(self.client.get("/solicitud/"), "/ingresar/")
        self.consultar()
        self.usuario.set_password("NuevaClave!4820")
        self.usuario.save()
        self.assertRedirects(self.client.get("/solicitud/"), "/ingresar/")

    def test_consulta_no_admite_cambiar_el_usuario_por_parametros(self):
        self.consultar()
        respuesta = self.client.get(f"/solicitud/?usuario_id={self.admin.pk}")
        self.assertEqual(respuesta.context["solicitante"].pk, self.usuario.pk)
        sesion = self.client.session
        datos = sesion["consulta_solicitud"]
        datos["usuario_id"] = self.admin.pk
        sesion["consulta_solicitud"] = datos
        sesion.save()
        self.assertRedirects(self.client.get("/solicitud/"), "/ingresar/")

    def test_consulta_se_cierra_y_reenvio_exige_csrf(self):
        from django.test import Client
        estricto = Client(enforce_csrf_checks=True)
        estricto.post("/ingresar/", {})
        self.consultar()
        sesion = estricto.session
        sesion["consulta_solicitud"] = self.client.session["consulta_solicitud"]
        sesion.save()
        self.assertEqual(estricto.post("/solicitud/reenviar/", self.datos_reenvio()).status_code, 403)
        self.assertEqual(self.client.get("/solicitud/reenviar/").status_code, 405)
        self.assertRedirects(self.client.post("/salir/"), "/ingresar/")
        self.assertNotIn("consulta_solicitud", self.client.session)
        self.assertRedirects(self.client.get("/solicitud/"), "/ingresar/")

    def test_migracion_copia_solo_revision_con_datos_conocidos(self):
        import importlib
        from django.apps import apps
        from django.db import connection
        from .models import HistorialSolicitud
        self.usuario.revisado_por = self.admin
        self.usuario.revisado_en = timezone.now() - timedelta(days=1)
        self.usuario.save()
        modulo = importlib.import_module("maquinaria.migrations.0004_historialsolicitud")
        # La función de datos solo usa el alias de conexión, no modifica
        # el esquema; no abrimos un schema_editor dentro de TestCase.
        from types import SimpleNamespace
        editor = SimpleNamespace(connection=connection)
        modulo.conservar_ultima_revision(apps, editor)
        modulo.conservar_ultima_revision(apps, editor)
        self.assertEqual(HistorialSolicitud.objects.count(), 1)
        evento = HistorialSolicitud.objects.get()
        self.assertEqual(evento.fecha, self.usuario.revisado_en)
        self.assertEqual(evento.motivo, self.usuario.motivo_revision)



class GestionMaquinariaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_equipos", rut="12345678-5", password="ClaveAdmin!4820")
        cls.contratista = Usuario.objects.create_user(username="lector_equipos", rut="11111111-1", estado_aprobacion="APROBADO")
        cls.obra = Obra.objects.create(nombre="Obra Norte", direccion="Calle Norte 100")
        cls.otra_obra = Obra.objects.create(nombre="Obra Sur", direccion="Calle Sur 200")
        cls.bodega = Bodega.objects.create(nombre="Bodega Norte", obra=cls.obra)
        cls.destino = Bodega.objects.create(nombre="Bodega Sur", obra=cls.otra_obra)
        cls.maquina = Maquinaria.objects.create(
            codigo="M-001", nombre="Generador", marca="Marca", modelo="A",
            bodega=cls.bodega, tiempo_uso_inicial=timedelta(hours=10),
            tiempo_uso_acumulado=timedelta(hours=10),
            ultima_mantencion_conocida=True, revision_pendiente=False,
        )

    def setUp(self):
        self.client.force_login(self.admin)

    def datos_alta(self, **cambios):
        datos = {"codigo": " m-002 ", "nombre": "Compactadora", "marca": "Marca",
                 "modelo": "B", "bodega": self.bodega.pk, "precio_diario": "25000.00", "horas_iniciales": "100.25",
                 "horas_ultima_mantencion": "50.25"}
        datos.update(cambios)
        return datos

    def operar(self, accion, **cambios):
        datos = {"motivo": "Verificación de operación", "confirmar": "on"}
        datos.update(cambios)
        return self.client.post(f"/maquinaria/{self.maquina.pk}/operacion/{accion}/", datos)

    def test_alta_registra_lecturas_autor_y_evento_sin_aceptar_estado_inyectado(self):
        from .models import MovimientoMaquinaria
        respuesta = self.client.post("/maquinaria/nueva/", self.datos_alta(
            estado="BAJA", tiempo_uso_acumulado="0", revision_pendiente="true", registrado_por=self.contratista.pk,
        ))
        maquina = Maquinaria.objects.get(codigo="M-002")
        self.assertRedirects(respuesta, f"/maquinaria/{maquina.pk}/")
        self.assertEqual(maquina.estado, "DISPONIBLE")
        self.assertEqual(maquina.tiempo_uso_inicial, timedelta(hours=100, minutes=15))
        self.assertEqual(maquina.tiempo_uso_ultima_mantencion, timedelta(hours=50, minutes=15))
        self.assertEqual(maquina.registrado_por, self.admin)
        self.assertFalse(maquina.revision_pendiente)
        self.assertTrue(maquina.ultima_mantencion_conocida)
        self.assertEqual(maquina.movimientos.get().tipo, MovimientoMaquinaria.Tipo.ALTA)
        self.assertFalse(maquina.mantenimientos.exists())

    def test_ultima_mantencion_desconocida_programa_revision_y_no_deja_disponible(self):
        self.client.post("/maquinaria/nueva/", self.datos_alta(horas_ultima_mantencion=""))
        maquina = Maquinaria.objects.get(codigo="M-002")
        self.assertEqual(maquina.estado, "MANTENIMIENTO")
        self.assertTrue(maquina.revision_pendiente)
        self.assertFalse(maquina.ultima_mantencion_conocida)
        self.assertEqual(maquina.mantenimientos.count(), 1)

    def test_250_horas_desde_ultima_mantencion_programa_revision(self):
        self.client.post("/maquinaria/nueva/", self.datos_alta(horas_iniciales="900", horas_ultima_mantencion="650"))
        maquina = Maquinaria.objects.get(codigo="M-002")
        self.assertEqual(maquina.estado, "MANTENIMIENTO")
        self.assertTrue(maquina.requiere_mantencion_por_uso)
        self.assertEqual(maquina.mantenimientos.count(), 1)

    def test_lecturas_invalidas_y_codigo_duplicado_no_crean_equipo(self):
        for datos in [self.datos_alta(horas_iniciales="-1"),
                      self.datos_alta(horas_ultima_mantencion="101"),
                      self.datos_alta(codigo="m-001")]:
            with self.subTest(datos=datos):
                respuesta = self.client.post("/maquinaria/nueva/", datos)
                self.assertEqual(respuesta.status_code, 200)
                self.assertTrue(respuesta.context["form"].errors)
                self.assertEqual(Maquinaria.objects.count(), 1)

    def test_base_rechaza_codigos_que_solo_difieren_en_mayusculas(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Maquinaria.objects.create(codigo="m-001", nombre="Duplicado", bodega=self.bodega)

    def test_edicion_no_permite_manipular_codigo_bodega_horas_ni_estado(self):
        respuesta = self.client.post(f"/maquinaria/{self.maquina.pk}/editar/", {
            "nombre": "Generador corregido", "marca": "Marca", "modelo": "A", "precio_diario": "25000.00",
            "codigo": "OTRO", "bodega": self.destino.pk, "estado": "BAJA", "tiempo_uso_acumulado": "0",
        })
        self.assertRedirects(respuesta, f"/maquinaria/{self.maquina.pk}/")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.nombre, "Generador corregido")
        self.assertEqual(self.maquina.codigo, "M-001")
        self.assertEqual(self.maquina.bodega_id, self.bodega.pk)
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=10))
        self.assertEqual(self.maquina.movimientos.get().tipo, "EDICION")

    def test_traslado_registra_origen_destino_y_responsable(self):
        self.assertRedirects(self.operar("trasladar", destino=self.destino.pk), f"/maquinaria/{self.maquina.pk}/")
        self.maquina.refresh_from_db()
        evento = self.maquina.movimientos.get()
        self.assertEqual(self.maquina.bodega_id, self.destino.pk)
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertEqual(evento.origen, self.bodega)
        self.assertEqual(evento.destino, self.destino)
        self.assertEqual(evento.registrado_por, self.admin)
        self.assertEqual(evento.tipo, "TRASLADO")

    def test_no_traslada_a_la_misma_bodega(self):
        respuesta = self.operar("trasladar", destino=self.bodega.pk)
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors)
        self.assertFalse(self.maquina.movimientos.exists())

    def test_baja_y_reactivacion_conservan_historial_y_no_habilitan_disponibilidad(self):
        self.assertRedirects(self.operar("baja", motivo="Retiro registrado"), f"/maquinaria/{self.maquina.pk}/")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "BAJA")
        self.assertRedirects(self.operar("reactivar", motivo="Se eligió la máquina equivocada"), f"/maquinaria/{self.maquina.pk}/")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")
        self.assertTrue(self.maquina.revision_pendiente)
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=10))
        self.assertEqual(self.maquina.tiempo_uso_inicial, timedelta(hours=10))
        self.assertEqual(set(self.maquina.movimientos.values_list("tipo", flat=True)), {"BAJA", "REACTIVACION"})
        self.assertEqual(self.maquina.mantenimientos.count(), 1)
        self.assertEqual(self.operar("reactivar").status_code, 200)
        self.assertEqual(self.maquina.mantenimientos.count(), 1)

    def test_baja_exige_motivo_y_confirmacion(self):
        for datos in [{"motivo": "   "}, {"confirmar": ""}]:
            respuesta = self.operar("baja", **datos)
            self.assertEqual(respuesta.status_code, 200)
            self.assertTrue(respuesta.context["form"].errors)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertFalse(self.maquina.movimientos.exists())

    def test_no_opera_sobre_maquinaria_en_uso_o_mantenimiento(self):
        for estado in ["EN_USO", "MANTENIMIENTO"]:
            self.maquina.estado = estado
            self.maquina.save()
            self.operar("baja")
            self.operar("trasladar", destino=self.destino.pk)
            self.maquina.refresh_from_db()
            self.assertEqual(self.maquina.estado, estado)
            self.assertFalse(self.maquina.movimientos.exists())

    def test_arriendo_abierto_bloquea_operacion_aunque_estado_sea_disponible(self):
        empresa = Empresa.objects.create(rut="76123456-0", razon_social="Prueba")
        terminos = TerminosCondiciones.objects.create(version="equipos", contenido="Prueba")
        ahora = timezone.now()
        aceptacion = AceptacionTerminos.objects.create(usuario=self.contratista, terminos=terminos, aceptado_en=ahora, firmado_en=ahora, firma="prueba.png")
        Arriendo.objects.create(maquinaria=self.maquina, empresa=empresa, responsable=self.contratista,
                               obra_destino=self.obra, aceptacion=aceptacion, entregado_en=ahora,
                               devolucion_prevista=ahora + timedelta(days=1), tarifa_diaria=100, firma_entrega="prueba.png")
        respuesta = self.operar("baja")
        self.assertContains(respuesta, "arriendo, sesión de uso o mantenimiento abierto")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")

    def test_permisos_restringen_escritura_pero_permiten_consulta(self):
        self.client.force_login(self.contratista)
        self.assertContains(self.client.get("/maquinaria/"), "Generador")
        self.assertContains(self.client.get(f"/maquinaria/{self.maquina.pk}/"), "Historial del equipo")
        for ruta in ["/maquinaria/nueva/", f"/maquinaria/{self.maquina.pk}/editar/",
                     f"/maquinaria/{self.maquina.pk}/operacion/baja/", "/ubicaciones/obra/nueva/"]:
            self.assertEqual(self.client.get(ruta).status_code, 403)
            self.assertEqual(self.client.post(ruta, {}).status_code, 403)

    def test_reactivacion_no_permitida_a_bodeguero_aunque_tenga_permiso(self):
        from django.contrib.auth.models import Permission
        bodeguero = Usuario.objects.create_user(username="bodeguero_equipos", rut="22222222-2", rol="BODEGUERO")
        bodeguero.user_permissions.add(Permission.objects.get(codename="reactivar_maquinaria"))
        self.maquina.estado = "BAJA"
        self.maquina.save()
        self.client.force_login(bodeguero)
        self.assertEqual(self.operar("reactivar").status_code, 403)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "BAJA")

    def test_falla_historial_revierte_baja_completa(self):
        with patch("maquinaria.servicios_maquinaria.MovimientoMaquinaria.objects.create", side_effect=RuntimeError("Fallo de historial")):
            with self.assertRaises(RuntimeError):
                self.operar("baja")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")

    def test_catalogo_filtra_y_pagina_con_entradas_invalidas_controladas(self):
        Maquinaria.objects.bulk_create([Maquinaria(codigo=f"E-{i:03}", nombre="Excavadora", bodega=self.destino, estado="BAJA") for i in range(14)])
        respuesta = self.client.get("/maquinaria/?q=Excavadora&estado=BAJA")
        self.assertEqual(respuesta.context["pagina"].paginator.count, 14)
        self.assertEqual(len(respuesta.context["pagina"]), 12)
        self.assertContains(respuesta, "Siguiente")
        self.assertEqual(len(self.client.get("/maquinaria/?q=Excavadora&page=2").context["pagina"]), 2)
        self.assertEqual(self.client.get(f"/maquinaria/?bodega={self.bodega.pk}").context["pagina"].paginator.count, 1)
        respuesta = self.client.get("/maquinaria/?bodega=no-es-un-id&estado=INVALIDO")
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context["form"].errors)

    def test_obras_bodegas_y_asociacion_historica(self):
        self.assertEqual(self.client.get("/ubicaciones/").status_code, 200)
        self.assertRedirects(self.client.post("/ubicaciones/obra/nueva/", {"nombre": "Nueva obra", "direccion": "Nueva dirección"}), "/ubicaciones/")
        self.assertRedirects(self.client.post("/ubicaciones/bodega/nueva/", {"nombre": "Nueva bodega", "direccion": "Calle Bodega 100", "obra": self.obra.pk}), "/ubicaciones/")
        self.client.post(f"/ubicaciones/bodega/{self.bodega.pk}/editar/", {"nombre": "Nombre corregido", "direccion": "Calle Bodega 200", "obra": self.otra_obra.pk})
        self.bodega.refresh_from_db()
        self.assertEqual(self.bodega.nombre, "Nombre corregido")
        self.assertEqual(self.bodega.obra_id, self.obra.pk)

    def test_get_no_ejecuta_operaciones_y_csrf_es_obligatorio(self):
        from django.test import Client
        self.assertEqual(self.client.get(f"/maquinaria/{self.maquina.pk}/operacion/baja/").status_code, 200)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.admin)
        self.assertEqual(estricto.post(f"/maquinaria/{self.maquina.pk}/operacion/baja/", {"motivo": "Prueba", "confirmar": "on"}).status_code, 403)

    def test_acceso_limitado_no_permite_catalogo(self):
        self.client.logout()
        pendiente = Usuario.objects.create_user(username="pendiente_equipos", rut="33333333-3", password="ClaveConsulta!4820", is_active=False)
        self.client.post("/ingresar/", {"username": pendiente.username, "password": "ClaveConsulta!4820"})
        self.assertRedirects(self.client.get("/maquinaria/", follow=True), "/solicitud/")



class BodegasSinObraTests(TestCase):
    def setUp(self):
        self.admin = Usuario.objects.create_superuser(username="admin_bodegas", rut="12345678-5", password="ClaveAdmin!4820")
        self.client.force_login(self.admin)

    def test_crear_bodega_de_empresa_sin_obras_registradas(self):
        self.assertFalse(Obra.objects.exists())
        respuesta = self.client.post("/ubicaciones/bodega/nueva/", {
            "nombre": "Bodega Central BuildCorp", "direccion": "Avenida Central 500", "obra": "",
        })
        self.assertRedirects(respuesta, "/ubicaciones/")
        bodega = Bodega.objects.get()
        self.assertIsNone(bodega.obra)
        self.assertEqual(bodega.direccion, "Avenida Central 500")
        self.assertEqual(str(bodega), "Bodega Central BuildCorp")
        self.assertContains(self.client.get("/ubicaciones/"), "Bodega de empresa, sin obra asociada")

    def test_direccion_obligatoria_aunque_obra_sea_opcional(self):
        respuesta = self.client.post("/ubicaciones/bodega/nueva/", {"nombre": "Central", "direccion": "   ", "obra": ""})
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("direccion", respuesta.context["form"].errors)
        self.assertNotIn("obra", respuesta.context["form"].errors)
        self.assertFalse(Bodega.objects.exists())

    def test_maquina_y_traslado_funcionan_entre_bodegas_sin_obra(self):
        origen = Bodega.objects.create(nombre="Central", direccion="Calle Central 100")
        destino = Bodega.objects.create(nombre="Sucursal", direccion="Calle Sucursal 200")
        respuesta = self.client.post("/maquinaria/nueva/", {
            "codigo": "CENTRAL-001", "nombre": "Generador", "marca": "", "modelo": "",
            "bodega": origen.pk, "precio_diario": "25000.00", "horas_iniciales": "0", "horas_ultima_mantencion": "0",
        })
        maquina = Maquinaria.objects.get()
        self.assertRedirects(respuesta, f"/maquinaria/{maquina.pk}/")
        detalle = self.client.get(f"/maquinaria/{maquina.pk}/")
        self.assertContains(detalle, "Calle Central 100")
        self.assertContains(detalle, "Bodega de empresa, sin obra asociada")
        self.assertContains(self.client.get("/maquinaria/"), "Generador")
        self.assertRedirects(self.client.post(f"/maquinaria/{maquina.pk}/operacion/trasladar/", {
            "destino": destino.pk, "motivo": "Reposición de inventario", "confirmar": "on",
        }), f"/maquinaria/{maquina.pk}/")
        maquina.refresh_from_db()
        self.assertEqual(maquina.bodega, destino)
        self.assertEqual(maquina.movimientos.get(tipo="TRASLADO").origen, origen)

    def test_bodega_de_obra_conserva_relacion_y_permite_corregir_direccion(self):
        obra = Obra.objects.create(nombre="Edificio", direccion="Dirección del trabajo")
        bodega = Bodega.objects.create(nombre="Bodega de obra", obra=obra)
        self.assertContains(self.client.get("/ubicaciones/"), "Sin registrar")
        respuesta = self.client.post(f"/ubicaciones/bodega/{bodega.pk}/editar/", {
            "nombre": "Bodega de obra", "direccion": "Acceso de bodega 10", "obra": "",
        })
        self.assertRedirects(respuesta, "/ubicaciones/")
        bodega.refresh_from_db()
        self.assertEqual(bodega.obra_id, obra.pk)
        self.assertEqual(bodega.direccion, "Acceso de bodega 10")


class ActividadUbicacionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_actividad", rut="12345678-5", password="ClaveAdmin!4820")
        cls.lector = Usuario.objects.create_user(username="lector_actividad", rut="11111111-1", estado_aprobacion="APROBADO")
        cls.obra = Obra.objects.create(nombre="Obra de actividad", direccion="Calle Trabajo 100")
        cls.bodega = Bodega.objects.create(nombre="Central de actividad", direccion="Calle Central 200")
        cls.bodega_obra = Bodega.objects.create(nombre="Bodega en obra", direccion="Acceso Obra 300", obra=cls.obra)
        cls.maquina = Maquinaria.objects.create(codigo="ACT-001", nombre="Generador de actividad", bodega=cls.bodega, revision_pendiente=False)

    def setUp(self):
        self.client.force_login(self.admin)

    def cambiar(self, tipo, pk, accion="desactivar", **datos):
        payload = {"motivo": "Cierre temporal de la ubicación", "confirmar": "on"}
        payload.update(datos)
        return self.client.post(f"/ubicaciones/{tipo}/{pk}/actividad/{accion}/", payload)

    def arriendo(self):
        ahora = timezone.now()
        empresa = Empresa.objects.create(rut="76123456-0", razon_social="Contratista de actividad")
        terminos = TerminosCondiciones.objects.create(version="actividad", contenido="Prueba de actividad")
        aceptacion = AceptacionTerminos.objects.create(usuario=self.lector, terminos=terminos, aceptado_en=ahora, firmado_en=ahora, firma="prueba.png")
        return Arriendo.objects.create(maquinaria=self.maquina, empresa=empresa, responsable=self.lector,
                                       obra_destino=self.obra, aceptacion=aceptacion, entregado_en=ahora,
                                       devolucion_prevista=ahora + timedelta(days=1), tarifa_diaria=100, firma_entrega="prueba.png")

    def test_desactivar_reactivar_bodega_vacia_conserva_historial(self):
        from .models import HistorialUbicacion
        respuesta = self.cambiar("bodega", self.bodega_obra.pk)
        self.assertRedirects(respuesta, f"/ubicaciones/bodega/{self.bodega_obra.pk}/historial/")
        self.bodega_obra.refresh_from_db()
        self.assertFalse(self.bodega_obra.activa)
        evento = HistorialUbicacion.objects.get()
        self.assertEqual(evento.bodega, self.bodega_obra)
        self.assertIsNone(evento.obra)
        self.assertEqual(evento.responsable, self.admin)
        self.assertEqual(evento.accion, "DESACTIVACION")
        self.assertRedirects(self.cambiar("bodega", self.bodega_obra.pk, "reactivar", motivo="Reapertura"), f"/ubicaciones/bodega/{self.bodega_obra.pk}/historial/")
        self.bodega_obra.refresh_from_db()
        self.assertTrue(self.bodega_obra.activa)
        self.assertEqual(HistorialUbicacion.objects.count(), 2)
        self.assertContains(self.client.get(f"/ubicaciones/bodega/{self.bodega_obra.pk}/historial/"), "Reapertura")

    def test_bodega_con_equipo_operativo_no_se_desactiva(self):
        for estado in ["DISPONIBLE", "EN_USO", "MANTENIMIENTO"]:
            self.maquina.estado = estado
            self.maquina.save()
            respuesta = self.cambiar("bodega", self.bodega.pk)
            self.assertContains(respuesta, "Primero debes trasladar la maquinaria")
            self.bodega.refresh_from_db()
            self.assertTrue(self.bodega.activa)
            self.assertFalse(self.bodega.historial_actividad.exists())

    def test_equipo_baja_permite_cierre_pero_no_reactivacion_en_bodega_inactiva(self):
        self.maquina.estado = "BAJA"
        self.maquina.save()
        self.cambiar("bodega", self.bodega.pk)
        respuesta = self.client.post(f"/maquinaria/{self.maquina.pk}/operacion/reactivar/", {"motivo": "Corrección de baja", "confirmar": "on"})
        self.assertContains(respuesta, "La bodega está desactivada")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "BAJA")
        self.assertFalse(self.maquina.mantenimientos.exists())
        self.cambiar("bodega", self.bodega.pk, "reactivar")
        respuesta = self.client.post(f"/maquinaria/{self.maquina.pk}/operacion/reactivar/", {"motivo": "Corrección de baja", "confirmar": "on"})
        self.assertRedirects(respuesta, f"/maquinaria/{self.maquina.pk}/")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")

    def test_obra_con_bodegas_activas_no_se_desactiva(self):
        self.assertContains(self.cambiar("obra", self.obra.pk), "todavía tiene bodegas activas")
        self.obra.refresh_from_db()
        self.assertTrue(self.obra.activa)

    def test_obra_con_arriendo_abierto_no_se_desactiva(self):
        self.cambiar("bodega", self.bodega_obra.pk)
        self.arriendo()
        self.assertContains(self.cambiar("obra", self.obra.pk), "arriendos pendientes de devolución")
        self.obra.refresh_from_db()
        self.assertTrue(self.obra.activa)

    def test_bodega_con_arriendo_abierto_no_se_cierra_aunque_equipo_figure_baja(self):
        self.arriendo()
        self.maquina.estado = "BAJA"
        self.maquina.save()
        self.assertContains(self.cambiar("bodega", self.bodega.pk), "arriendo pendiente de devolución")
        self.bodega.refresh_from_db()
        self.assertTrue(self.bodega.activa)

    def test_obra_se_reactiva_antes_que_su_bodega_sin_cambiar_maquinas(self):
        self.maquina.bodega = self.bodega_obra
        self.maquina.estado = "BAJA"
        self.maquina.save()
        self.cambiar("bodega", self.bodega_obra.pk)
        self.cambiar("obra", self.obra.pk)
        self.assertContains(self.cambiar("bodega", self.bodega_obra.pk, "reactivar"), "Primero debes reactivar la obra")
        self.bodega_obra.refresh_from_db()
        self.assertFalse(self.bodega_obra.activa)
        self.cambiar("obra", self.obra.pk, "reactivar")
        self.cambiar("bodega", self.bodega_obra.pk, "reactivar")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "BAJA")
        self.assertFalse(self.maquina.movimientos.exists())
        self.assertEqual(self.obra.historial_actividad.count(), 2)

    def test_formularios_excluyen_ubicaciones_inactivas_y_conservan_historial(self):
        from .forms_maquinaria import CrearMaquinariaForm, TrasladarMaquinariaForm, BodegaForm
        self.bodega.activa = False
        self.bodega.save()
        self.obra.activa = False
        self.obra.save()
        self.assertNotIn(self.bodega, CrearMaquinariaForm().fields["bodega"].queryset)
        self.assertNotIn(self.bodega_obra, CrearMaquinariaForm().fields["bodega"].queryset)
        self.assertNotIn(self.bodega_obra, TrasladarMaquinariaForm().fields["destino"].queryset)
        self.assertNotIn(self.obra, BodegaForm().fields["obra"].queryset)
        self.assertContains(self.client.get(f"/maquinaria/{self.maquina.pk}/"), "La ubicación está inactiva")
        self.assertContains(self.client.get("/maquinaria/"), self.maquina.nombre)

    def test_no_crea_maquina_en_bodega_desactivada_desde_post_o_servicio(self):
        from decimal import Decimal
        from django.core.exceptions import ValidationError
        from .servicios_maquinaria import crear_maquinaria
        # Se conserva un objeto leído antes del cierre para comprobar que el
        # servicio vuelve a consultar su estado en la base de datos.
        bodega_anterior = self.bodega_obra
        self.cambiar("bodega", bodega_anterior.pk)
        datos = {"codigo": "ACT-002", "nombre": "Equipo nuevo", "marca": "", "modelo": "",
                 "bodega": bodega_anterior.pk, "precio_diario": "25000.00", "horas_iniciales": "0", "horas_ultima_mantencion": "0"}
        respuesta = self.client.post("/maquinaria/nueva/", datos)
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("bodega", respuesta.context["form"].errors)
        datos.update(bodega=bodega_anterior, horas_iniciales=Decimal("0"), horas_ultima_mantencion=Decimal("0"))
        with self.assertRaises(ValidationError):
            crear_maquinaria(datos=datos, responsable=self.admin)
        self.assertFalse(Maquinaria.objects.filter(codigo="ACT-002").exists())

    def test_traslado_vuelve_a_validar_destino_que_cerro_despues_de_abrir_formulario(self):
        from django.core.exceptions import ValidationError
        from .servicios_maquinaria import operar_maquinaria
        destino_anterior = self.bodega_obra
        self.cambiar("bodega", destino_anterior.pk)
        with self.assertRaises(ValidationError):
            operar_maquinaria(maquinaria_id=self.maquina.pk, accion="trasladar", destino=destino_anterior, motivo="Traslado", responsable=self.admin)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.bodega_id, self.bodega.pk)
        self.assertFalse(self.maquina.movimientos.exists())

    def test_no_crea_bodega_en_obra_inactiva_desde_post_o_servicio(self):
        from django.core.exceptions import ValidationError
        from .servicios_ubicaciones import guardar_ubicacion
        self.cambiar("bodega", self.bodega_obra.pk)
        self.cambiar("obra", self.obra.pk)
        respuesta = self.client.post("/ubicaciones/bodega/nueva/", {"nombre": "Otra", "direccion": "Nueva dirección", "obra": self.obra.pk})
        self.assertIn("obra", respuesta.context["form"].errors)
        with self.assertRaises(ValidationError):
            guardar_ubicacion(tipo="bodega", datos={"nombre": "Otra", "direccion": "Nueva dirección", "obra": self.obra}, responsable=self.admin)
        self.assertFalse(Bodega.objects.filter(nombre="Otra").exists())

    def test_editar_no_permite_modificar_actividad_por_post(self):
        self.cambiar("bodega", self.bodega_obra.pk)
        respuesta = self.client.post(f"/ubicaciones/bodega/{self.bodega_obra.pk}/editar/", {
            "nombre": "Nombre corregido", "direccion": "Dirección corregida", "activa": "true",
        })
        self.assertRedirects(respuesta, "/ubicaciones/")
        self.bodega_obra.refresh_from_db()
        self.assertFalse(self.bodega_obra.activa)
        self.assertEqual(self.bodega_obra.nombre, "Nombre corregido")
        self.assertEqual(self.bodega_obra.historial_actividad.count(), 1)

    def test_motivo_confirmacion_y_estado_repetido_no_crean_eventos(self):
        for datos in [{"motivo": "   "}, {"confirmar": ""}]:
            respuesta = self.cambiar("bodega", self.bodega_obra.pk, **datos)
            self.assertTrue(respuesta.context["form"].errors)
        self.assertFalse(self.bodega_obra.historial_actividad.exists())
        self.cambiar("bodega", self.bodega_obra.pk)
        self.assertContains(self.cambiar("bodega", self.bodega_obra.pk), "ya tiene ese estado")
        self.assertEqual(self.bodega_obra.historial_actividad.count(), 1)

    def test_permisos_impiden_desactivar_y_reactivar_a_contratistas(self):
        self.client.force_login(self.lector)
        for accion in ("desactivar", "reactivar"):
            self.assertEqual(self.cambiar("bodega", self.bodega_obra.pk, accion).status_code, 403)
        self.assertNotContains(self.client.get("/ubicaciones/"), '>Desactivar bodega</a>')

    def test_reactivacion_exige_administrador_ademas_del_permiso(self):
        from django.contrib.auth.models import Permission
        self.cambiar("bodega", self.bodega_obra.pk)
        bodeguero = Usuario.objects.create_user(username="bodeguero_actividad", rut="22222222-2", rol="BODEGUERO")
        bodeguero.user_permissions.add(Permission.objects.get(codename="reactivar_bodega"))
        self.client.force_login(bodeguero)
        self.assertEqual(self.cambiar("bodega", self.bodega_obra.pk, "reactivar").status_code, 403)
        self.bodega_obra.refresh_from_db()
        self.assertFalse(self.bodega_obra.activa)

    def test_falla_historial_revierte_desactivacion(self):
        with patch("maquinaria.servicios_ubicaciones.HistorialUbicacion.objects.create", side_effect=RuntimeError("Fallo simulado")):
            with self.assertRaises(RuntimeError):
                self.cambiar("bodega", self.bodega_obra.pk)
        self.bodega_obra.refresh_from_db()
        self.assertTrue(self.bodega_obra.activa)
        self.assertFalse(self.bodega_obra.historial_actividad.exists())

    def test_filtro_activas_por_defecto_inactivas_y_todas(self):
        self.cambiar("bodega", self.bodega_obra.pk)
        respuesta = self.client.get("/ubicaciones/")
        self.assertNotIn(self.bodega_obra, respuesta.context["bodegas"])
        self.assertIn(self.bodega, respuesta.context["bodegas"])
        self.assertIn(self.bodega_obra, self.client.get("/ubicaciones/?estado=inactivas").context["bodegas"])
        self.assertEqual(self.client.get("/ubicaciones/?estado=todas").context["bodegas"].count(), 2)
        self.assertTrue(self.client.get("/ubicaciones/?estado=INVALIDO").context["form"].errors)

    def test_get_no_cambia_estado_y_post_exige_csrf(self):
        from django.test import Client
        ruta = f"/ubicaciones/bodega/{self.bodega_obra.pk}/actividad/desactivar/"
        self.assertEqual(self.client.get(ruta).status_code, 200)
        self.bodega_obra.refresh_from_db()
        self.assertTrue(self.bodega_obra.activa)
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.admin)
        self.assertEqual(estricto.post(ruta, {"motivo": "Prueba", "confirmar": "on"}).status_code, 403)

    def test_historial_no_admite_ninguna_o_ambas_ubicaciones(self):
        from .models import HistorialUbicacion
        for datos in [{}, {"obra": self.obra, "bodega": self.bodega}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                HistorialUbicacion.objects.create(accion="DESACTIVACION", motivo="Prueba", responsable=self.admin, **datos)


class FlujoMantencionesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_mantencion", rut="12345678-5", password="ClaveAdmin!4820")
        cls.lector = Usuario.objects.create_user(username="lector_mantencion", rut="11111111-1", estado_aprobacion="APROBADO")
        cls.bodega = Bodega.objects.create(nombre="Taller central", direccion="Calle Taller 100")
        cls.maquina = Maquinaria.objects.create(codigo="MANT-001", nombre="Equipo de mantención", bodega=cls.bodega,
            tiempo_uso_acumulado=timedelta(hours=900), tiempo_uso_inicial=timedelta(hours=100),
            tiempo_uso_ultima_mantencion=timedelta(hours=650), revision_pendiente=True,
            ultima_mantencion_conocida=True, estado="MANTENIMIENTO")
        from .models import Mantenimiento
        cls.orden = Mantenimiento.objects.create(maquinaria=cls.maquina, fecha_programada=timezone.localdate(), descripcion="Revisión de 250 horas")

    def setUp(self):
        self.client.force_login(self.admin)

    def iniciar(self, orden=None):
        return self.client.post(f"/mantenciones/{(orden or self.orden).pk}/iniciar/", {"confirmar": "on"})

    def finalizar(self, apta="si", **cambios):
        datos = {"resultado": "Se realizó revisión y prueba funcional.", "apta_para_servicio": apta, "confirmar": "on"}
        datos.update(cambios)
        return self.client.post(f"/mantenciones/{self.orden.pk}/finalizar/", datos)

    def test_inicio_finalizacion_satisfactoria_conservan_horas_y_establecen_referencia(self):
        self.assertRedirects(self.iniciar(), f"/mantenciones/{self.orden.pk}/")
        self.orden.refresh_from_db()
        self.assertEqual(self.orden.estado, "En curso")
        self.assertEqual(self.orden.responsable, self.admin)
        self.assertIsNotNone(self.orden.iniciado_en)
        self.assertRedirects(self.finalizar(), f"/mantenciones/{self.orden.pk}/")
        self.orden.refresh_from_db()
        self.maquina.refresh_from_db()
        self.assertEqual(self.orden.estado, "Finalizada")
        self.assertTrue(self.orden.apta_para_servicio)
        self.assertEqual(self.orden.finalizado_por, self.admin)
        self.assertEqual(self.orden.lectura_uso, timedelta(hours=900))
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=900))
        self.assertEqual(self.maquina.tiempo_uso_inicial, timedelta(hours=100))
        self.assertEqual(self.maquina.tiempo_uso_ultima_mantencion, timedelta(hours=900))
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertFalse(self.maquina.bloqueada_por_mantencion)
        self.maquina.tiempo_uso_acumulado = timedelta(hours=1150)
        self.assertTrue(self.maquina.requiere_mantencion_por_uso)
        self.assertEqual(set(self.maquina.movimientos.values_list("tipo", flat=True)), {"INICIO_MANT", "FIN_MANT"})

    def test_resultado_no_apto_mantiene_bloqueo_y_genera_seguimiento(self):
        from .models import Mantenimiento
        self.iniciar()
        self.finalizar(apta="no")
        self.maquina.refresh_from_db()
        self.orden.refresh_from_db()
        self.assertFalse(self.orden.apta_para_servicio)
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")
        self.assertTrue(self.maquina.revision_pendiente)
        self.assertEqual(self.maquina.tiempo_uso_ultima_mantencion, timedelta(hours=650))
        seguimiento = Mantenimiento.objects.exclude(pk=self.orden.pk).get()
        self.assertIsNone(seguimiento.iniciado_en)
        self.assertIn(f"#{self.orden.pk}", seguimiento.descripcion)
        self.assertEqual(seguimiento.fecha_programada, timezone.localdate())
        self.assertRedirects(self.iniciar(seguimiento), f"/mantenciones/{seguimiento.pk}/")

    def test_otra_revision_exigible_impide_liberar_pero_no_pierde_resultado(self):
        from .models import Mantenimiento
        otra = Mantenimiento.objects.create(maquinaria=self.maquina, fecha_programada=timezone.localdate(), descripcion="Revisión eléctrica adicional")
        self.iniciar()
        self.finalizar()
        self.orden.refresh_from_db()
        self.maquina.refresh_from_db()
        self.assertIsNotNone(self.orden.finalizado_en)
        self.assertTrue(self.orden.apta_para_servicio)
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")
        self.assertTrue(self.maquina.revision_pendiente)
        self.assertRedirects(self.iniciar(otra), f"/mantenciones/{otra.pk}/")

    def test_otra_revision_futura_no_impide_retorno_disponible(self):
        from .models import Mantenimiento
        Mantenimiento.objects.create(maquinaria=self.maquina, fecha_programada=timezone.localdate() + timedelta(days=30), descripcion="Revisión futura")
        self.iniciar()
        self.finalizar()
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertFalse(self.maquina.bloqueada_por_mantencion)

    def test_no_puede_finalizar_sin_iniciar_ni_repetir_inicio_o_finalizacion(self):
        self.assertContains(self.finalizar(), "Solo se puede finalizar una mantención en curso")
        self.iniciar()
        self.assertContains(self.iniciar(), "ya fue iniciada o finalizada")
        self.assertEqual(self.maquina.movimientos.count(), 1)
        self.finalizar()
        self.assertContains(self.finalizar(), "Solo se puede finalizar una mantención en curso")
        self.assertEqual(self.maquina.movimientos.count(), 2)

    def test_no_inicia_segunda_intervencion_simultanea(self):
        from .models import Mantenimiento
        otra = Mantenimiento.objects.create(maquinaria=self.maquina, fecha_programada=timezone.localdate(), descripcion="Otra revisión")
        self.iniciar()
        self.assertContains(self.iniciar(otra), "ya tiene una mantención en curso")
        otra.refresh_from_db()
        self.assertIsNone(otra.iniciado_en)

    def test_programacion_futura_no_cambia_disponibilidad_y_se_vuelve_exigible_por_fecha(self):
        from .models import Mantenimiento
        nueva = Maquinaria.objects.create(codigo="MANT-002", nombre="Equipo disponible", bodega=self.bodega,
                                          revision_pendiente=False, ultima_mantencion_conocida=True)
        fecha = timezone.localdate() + timedelta(days=10)
        datos = {"maquinaria": nueva.pk, "fecha_programada": fecha.isoformat(), "descripcion": "Control preventivo"}
        respuesta = self.client.post("/mantenciones/nueva/", datos)
        orden = Mantenimiento.objects.get(maquinaria=nueva)
        self.assertRedirects(respuesta, f"/mantenciones/{orden.pk}/")
        nueva.refresh_from_db()
        self.assertEqual(nueva.estado, "DISPONIBLE")
        self.assertFalse(nueva.bloqueada_por_mantencion)
        self.assertEqual(orden.programado_por, self.admin)
        self.assertIsNone(orden.iniciado_en)
        with patch("maquinaria.models.timezone.localdate", return_value=fecha):
            self.assertTrue(nueva.bloqueada_por_mantencion)
        self.assertContains(self.client.post("/mantenciones/nueva/", datos), "Ya hay una mantención pendiente")
        self.assertEqual(Mantenimiento.objects.filter(maquinaria=nueva).count(), 1)

    def test_programacion_para_hoy_bloquea_equipo_inmediatamente(self):
        nueva = Maquinaria.objects.create(codigo="MANT-003", nombre="Equipo para hoy", bodega=self.bodega, revision_pendiente=False)
        self.client.post("/mantenciones/nueva/", {"maquinaria": nueva.pk, "fecha_programada": timezone.localdate().isoformat(), "descripcion": "Trabajo de hoy"})
        nueva.refresh_from_db()
        self.assertEqual(nueva.estado, "MANTENIMIENTO")
        self.assertTrue(nueva.revision_pendiente)

    def test_bodega_inactiva_no_permite_iniciar_ni_liberar(self):
        self.bodega.activa = False
        self.bodega.save()
        self.assertContains(self.iniciar(), "La bodega está desactivada")
        self.bodega.activa = True
        self.bodega.save()
        self.iniciar()
        self.bodega.activa = False
        self.bodega.save()
        self.assertContains(self.finalizar(), "La bodega está desactivada")
        self.orden.refresh_from_db()
        self.assertIsNone(self.orden.finalizado_en)

    def test_arriendo_abierto_impide_intervencion_aunque_estado_este_mal(self):
        empresa = Empresa.objects.create(rut="76123456-0", razon_social="Empresa prueba mantención")
        terminos = TerminosCondiciones.objects.create(version="mantencion", contenido="Prueba")
        ahora = timezone.now()
        aceptacion = AceptacionTerminos.objects.create(usuario=self.lector, terminos=terminos, aceptado_en=ahora, firmado_en=ahora, firma="prueba.png")
        obra = Obra.objects.create(nombre="Obra mantención", direccion="Calle Obra")
        Arriendo.objects.create(maquinaria=self.maquina, empresa=empresa, responsable=self.lector,
            obra_destino=obra, aceptacion=aceptacion, entregado_en=ahora,
            devolucion_prevista=ahora + timedelta(days=2), tarifa_diaria=100, firma_entrega="prueba.png")
        self.assertContains(self.iniciar(), "arriendo o sesión de uso abierta")
        self.orden.refresh_from_db()
        self.assertIsNone(self.orden.iniciado_en)

    def test_no_interviene_maquina_dada_baja(self):
        self.maquina.estado = "BAJA"
        self.maquina.save()
        self.assertContains(self.iniciar(), "estado actual de la máquina")
        self.assertFalse(self.maquina.movimientos.exists())

    def test_confirmacion_y_resultado_son_obligatorios(self):
        respuesta = self.client.post(f"/mantenciones/{self.orden.pk}/iniciar/", {})
        self.assertTrue(respuesta.context["form"].errors)
        self.iniciar()
        for cambios in [{"resultado": "   "}, {"confirmar": ""}, {"apta_para_servicio": "incorrecto"}]:
            respuesta = self.finalizar(**cambios)
            self.assertTrue(respuesta.context["form"].errors)
        self.orden.refresh_from_db()
        self.assertIsNone(self.orden.finalizado_en)

    def test_permisos_impiden_operaciones_y_consulta_a_contratistas(self):
        self.client.force_login(self.lector)
        for ruta in ["/mantenciones/", "/mantenciones/nueva/", f"/mantenciones/{self.orden.pk}/",
                     f"/mantenciones/{self.orden.pk}/iniciar/", f"/mantenciones/{self.orden.pk}/finalizar/"]:
            self.assertEqual(self.client.get(ruta).status_code, 403)
            self.assertEqual(self.client.post(ruta, {}).status_code, 403)

    def test_fallo_evento_revierte_finalizacion_y_referencia(self):
        self.iniciar()
        with patch("maquinaria.servicios_mantenimiento.registrar_evento", side_effect=RuntimeError("Fallo de historial")):
            with self.assertRaises(RuntimeError):
                self.finalizar()
        self.orden.refresh_from_db()
        self.maquina.refresh_from_db()
        self.assertIsNone(self.orden.finalizado_en)
        self.assertEqual(self.maquina.tiempo_uso_ultima_mantencion, timedelta(hours=650))
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")

    def test_listado_detalle_filtros_y_csrf(self):
        from django.test import Client
        self.assertContains(self.client.get("/mantenciones/"), "Revisión de 250 horas")
        self.assertContains(self.client.get(f"/mantenciones/{self.orden.pk}/"), "Iniciar mantención")
        self.assertEqual(self.client.get("/mantenciones/?estado=finalizada").context["pagina"].paginator.count, 0)
        self.iniciar()
        self.assertEqual(self.client.get("/mantenciones/?estado=curso").context["pagina"].paginator.count, 1)
        self.finalizar()
        self.assertContains(self.client.get(f"/mantenciones/{self.orden.pk}/"), "Satisfactoria")
        self.assertEqual(self.client.get(f"/mantenciones/?estado=finalizada&maquinaria={self.maquina.pk}").context["pagina"].paginator.count, 1)
        self.assertTrue(self.client.get("/mantenciones/?estado=incorrecto").context["form"].errors)
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.admin)
        self.assertEqual(estricto.post(f"/mantenciones/{self.orden.pk}/iniciar/", {"confirmar": "on"}).status_code, 403)


@override_settings(STORAGES={
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
})
class EntregaDevolucionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_arriendos", rut="12345678-5", password="ClaveAdmin!4820")
        cls.empresa = Empresa.objects.create(rut="76123456-0", razon_social="Empresa de arriendos")
        cls.usuario = Usuario.objects.create_user(username="responsable_arriendo", rut="11111111-1", empresa=cls.empresa, estado_aprobacion="APROBADO")
        cls.otro = Usuario.objects.create_user(username="otro_arriendo", rut="22222222-2", empresa=cls.empresa, estado_aprobacion="APROBADO")
        cls.obra = Obra.objects.create(nombre="Obra de destino", direccion="Calle Obra 100")
        cls.bodega = Bodega.objects.create(nombre="Origen arriendo", direccion="Calle Origen 200")
        cls.recepcion = Bodega.objects.create(nombre="Recepción arriendo", direccion="Calle Recepción 300")
        cls.maquina = Maquinaria.objects.create(codigo="ARR-001", nombre="Máquina de arriendo", bodega=cls.bodega,
            tiempo_uso_acumulado=timedelta(hours=10), revision_pendiente=False, ultima_mantencion_conocida=True)
        cls.terminos = TerminosCondiciones.objects.create(version="arriendos-1", contenido="Condiciones de prueba para arriendos")
        ahora = timezone.now()
        for usuario in [cls.usuario, cls.otro]:
            AceptacionTerminos.objects.create(usuario=usuario, terminos=cls.terminos, aceptado_en=ahora, firmado_en=ahora, firma="prueba-perfil.png")

    def setUp(self):
        self.client.force_login(self.admin)

    def png(self, blanco=False):
        from io import BytesIO
        from PIL import Image, ImageDraw
        from django.core.files.uploadedfile import SimpleUploadedFile
        imagen = Image.new("RGB", (900, 300), "white")
        if not blanco:
            ImageDraw.Draw(imagen).line([(20, 100), (150, 50), (200, 200), (400, 100)], fill="black", width=5)
        salida = BytesIO()
        imagen.save(salida, format="PNG")
        return SimpleUploadedFile("firma.png", salida.getvalue(), content_type="image/png")

    def preparar(self, responsable=None):
        from .models import SolicitudEntrega
        self.client.force_login(self.admin)
        respuesta = self.client.post("/arriendos/entrega/nueva/", {
            "maquinaria": self.maquina.pk, "empresa": self.empresa.pk,
            "responsable": (responsable or self.usuario).pk, "direccion_uso": "Calle Obra 100", "comuna_uso": "Santiago",
            "devolucion_prevista": (timezone.now() + timedelta(days=2)).isoformat(),
            "tarifa_diaria": "25000.00", "observaciones": "Equipo entregado con accesorios.",
        })
        solicitud = SolicitudEntrega.objects.order_by("-pk").first()
        self.assertRedirects(respuesta, f"/arriendos/solicitudes/entrega/{solicitud.pk}/")
        return solicitud

    def entregar(self):
        solicitud = self.preparar()
        self.client.force_login(self.usuario)
        respuesta = self.client.post(f"/arriendos/solicitudes/entrega/{solicitud.pk}/", {"confirmar": "on", "firma": self.png()})
        arriendo = Arriendo.objects.get(maquinaria=self.maquina)
        self.assertRedirects(respuesta, f"/arriendos/{arriendo.pk}/")
        return arriendo

    def recibir(self, arriendo, revision=False):
        from .models import SolicitudDevolucion
        self.client.force_login(self.admin)
        respuesta = self.client.post(f"/arriendos/{arriendo.pk}/recibir/", {"bodega": self.recepcion.pk,
            "observaciones": "Equipo recibido para comprobación.", "requiere_revision": "on" if revision else "", "confirmar": "on"})
        solicitud = SolicitudDevolucion.objects.filter(arriendo=arriendo).latest("pk")
        self.assertRedirects(respuesta, f"/arriendos/solicitudes/devolucion/{solicitud.pk}/")
        return solicitud

    def devolver(self, solicitud):
        self.client.force_login(self.usuario)
        return self.client.post(f"/arriendos/solicitudes/devolucion/{solicitud.pk}/", {"confirmar": "on", "firma": self.png()})

    def test_preparacion_no_reserva_equipo_y_muestra_resumen(self):
        solicitud = self.preparar()
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertFalse(Arriendo.objects.exists())
        self.assertEqual(solicitud.terminos_id, self.terminos.pk)
        self.assertContains(self.client.get(f"/arriendos/solicitudes/entrega/{solicitud.pk}/"), "no reserva la máquina")

    def test_entrega_firmada_cambia_estado_y_conserva_comprobante(self):
        arriendo = self.entregar()
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "EN_USO")
        self.assertEqual(arriendo.bodega_origen, self.bodega)
        self.assertEqual(arriendo.aceptacion.usuario, self.usuario)
        self.assertTrue(arriendo.firma_entrega.name)
        self.assertEqual(self.maquina.movimientos.get().tipo, "ENTREGA")
        self.assertContains(self.client.get(f"/arriendos/{arriendo.pk}/"), "Condiciones de prueba para arriendos")

    def test_otro_usuario_no_ve_ni_firma_solicitudes_ajenas_y_admin_no_firma_por_responsable(self):
        solicitud = self.preparar()
        ruta = f"/arriendos/solicitudes/entrega/{solicitud.pk}/"
        self.assertEqual(self.client.post(ruta, {"confirmar": "on", "firma": self.png()}).status_code, 403)
        self.client.force_login(self.otro)
        self.assertEqual(self.client.get(ruta).status_code, 404)
        self.assertEqual(self.client.post(ruta, {"confirmar": "on", "firma": self.png()}).status_code, 404)
        self.assertFalse(Arriendo.objects.exists())

    def test_entrega_repetida_no_duplica_arriendo_ni_historial(self):
        arriendo = self.entregar()
        solicitud = arriendo.solicitud_entrega
        self.assertEqual(self.client.post(f"/arriendos/solicitudes/entrega/{solicitud.pk}/", {"confirmar": "on", "firma": self.png()}).status_code, 200)
        self.assertEqual(Arriendo.objects.count(), 1)
        self.assertEqual(self.maquina.movimientos.count(), 1)

    def test_solicitudes_concurrentes_compiten_por_disponibilidad_al_confirmar(self):
        primera = self.preparar()
        segunda = self.preparar(responsable=self.otro)
        self.client.force_login(self.usuario)
        self.client.post(f"/arriendos/solicitudes/entrega/{primera.pk}/", {"confirmar": "on", "firma": self.png()})
        self.client.force_login(self.otro)
        respuesta = self.client.post(f"/arriendos/solicitudes/entrega/{segunda.pk}/", {"confirmar": "on", "firma": self.png()})
        self.assertContains(respuesta, "no está disponible")
        self.assertEqual(Arriendo.objects.count(), 1)

    def test_cambio_condiciones_exige_nueva_solicitud_aunque_haya_nueva_aceptacion(self):
        solicitud = self.preparar()
        nuevos = TerminosCondiciones.objects.create(version="arriendos-2", contenido="Condiciones nuevas")
        ahora = timezone.now()
        AceptacionTerminos.objects.create(usuario=self.usuario, terminos=nuevos, aceptado_en=ahora, firmado_en=ahora, firma="nueva.png")
        self.client.force_login(self.usuario)
        self.assertContains(self.client.post(f"/arriendos/solicitudes/entrega/{solicitud.pk}/", {"confirmar": "on", "firma": self.png()}), "Las condiciones cambiaron")
        self.assertFalse(Arriendo.objects.exists())

    def test_empresa_bloqueada_despues_preparar_impide_entrega(self):
        solicitud = self.preparar()
        self.empresa.bloqueada = True
        self.empresa.save()
        self.client.force_login(self.usuario)
        self.assertContains(self.client.post(f"/arriendos/solicitudes/entrega/{solicitud.pk}/", {"confirmar": "on", "firma": self.png()}), "empresa está bloqueada")
        self.assertFalse(Arriendo.objects.exists())

    def test_entrega_rechaza_vencimiento_cancelacion_y_revisiones_sobrevenidas(self):
        solicitud = self.preparar()
        ruta = f"/arriendos/solicitudes/entrega/{solicitud.pk}/"
        self.client.force_login(self.usuario)
        solicitud.vence_en = timezone.now() - timedelta(seconds=1)
        solicitud.save()
        self.assertContains(self.client.post(ruta, {"confirmar": "on", "firma": self.png()}), "cancelada o venció")
        solicitud.vence_en = timezone.now() + timedelta(hours=1)
        solicitud.save()
        self.maquina.revision_pendiente = True
        self.maquina.save()
        self.assertContains(self.client.post(ruta, {"confirmar": "on", "firma": self.png()}), "revisiones, uso o arriendos pendientes")
        self.assertFalse(Arriendo.objects.exists())

    def test_recepcion_cierra_timer_una_vez_sin_liberar_maquina(self):
        arriendo = self.entregar()
        inicio = timezone.now() - timedelta(hours=2)
        sesion = SesionUso.objects.create(arriendo=arriendo, inicio=inicio)
        ahora = inicio + timedelta(hours=2)
        with patch("maquinaria.servicios_arriendos.timezone.now", return_value=ahora):
            solicitud = self.recibir(arriendo)
        sesion.refresh_from_db()
        arriendo.refresh_from_db()
        self.maquina.refresh_from_db()
        self.assertEqual(sesion.fin, ahora)
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=12))
        self.assertEqual(self.maquina.estado, "EN_USO")
        self.assertEqual(self.maquina.bodega, self.recepcion)
        self.assertEqual(arriendo.recibido_en, ahora)
        self.assertIsNone(arriendo.devuelto_en)
        self.client.post(f"/arriendos/{arriendo.pk}/recibir/", {"bodega": self.recepcion.pk, "observaciones": "Repetido", "confirmar": "on"})
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=12))
        self.assertEqual(arriendo.recepciones.count(), 1)

    def test_devolucion_sana_libera_equipo_y_no_requiere_condiciones_nuevas(self):
        arriendo = self.entregar()
        solicitud = self.recibir(arriendo)
        TerminosCondiciones.objects.create(version="arriendos-2", contenido="Nueva versión posterior al arriendo")
        self.empresa.bloqueada = True
        self.empresa.save()
        self.assertRedirects(self.devolver(solicitud), f"/arriendos/{arriendo.pk}/")
        arriendo.refresh_from_db()
        self.maquina.refresh_from_db()
        self.assertIsNotNone(arriendo.devuelto_en)
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertTrue(arriendo.firma_devolucion.name)
        self.assertEqual(self.maquina.movimientos.filter(tipo="DEVOLUCION").count(), 1)
        self.devolver(solicitud)
        self.assertEqual(self.maquina.movimientos.filter(tipo="DEVOLUCION").count(), 1)

    def test_danos_o_250_horas_dejan_mantenimiento_programado(self):
        arriendo = self.entregar()
        self.maquina.tiempo_uso_acumulado = timedelta(hours=250)
        self.maquina.save(update_fields=["tiempo_uso_acumulado"])
        solicitud = self.recibir(arriendo, revision=True)
        self.devolver(solicitud)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")
        self.assertTrue(self.maquina.revision_pendiente)
        self.assertEqual(self.maquina.mantenimientos.count(), 1)
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=250))

    def test_cancelar_recepcion_no_reabre_timer_y_permite_corregir_observaciones(self):
        arriendo = self.entregar()
        sesion = SesionUso.objects.create(arriendo=arriendo, inicio=timezone.now() - timedelta(minutes=10))
        primera = self.recibir(arriendo, revision=True)
        self.client.post(f"/arriendos/solicitudes/devolucion/{primera.pk}/cancelar/", {"motivo": "Se corrigieron las observaciones", "confirmar": "on"})
        arriendo.refresh_from_db()
        recibido = arriendo.recibido_en
        sesion.refresh_from_db()
        self.assertIsNotNone(sesion.fin)
        self.maquina.refresh_from_db()
        horas = self.maquina.tiempo_uso_acumulado
        segunda = self.recibir(arriendo)
        self.devolver(segunda)
        self.maquina.refresh_from_db()
        arriendo.refresh_from_db()
        primera.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, horas)
        self.assertEqual(arriendo.recibido_en, recibido)
        self.assertIsNotNone(primera.cancelada_en)
        self.assertTrue(primera.requiere_revision)
        self.assertEqual(arriendo.recepciones.count(), 2)

    def test_recepcion_vencida_se_reemplaza_sin_perder_antecedentes(self):
        arriendo = self.entregar()
        primera = self.recibir(arriendo)
        primera.vence_en = timezone.now() - timedelta(seconds=1)
        primera.save()
        self.assertContains(self.devolver(primera), "cancelada o venció")
        segunda = self.recibir(arriendo)
        primera.refresh_from_db()
        self.assertIsNotNone(primera.cancelada_en)
        self.assertNotEqual(primera.pk, segunda.pk)

    def test_firmas_privadas_y_listados_no_exponen_arriendos_ajenos(self):
        arriendo = self.entregar()
        self.assertContains(self.client.get("/arriendos/"), "ARR-001")
        respuesta = self.client.get(f"/arriendos/{arriendo.pk}/firma/entrega/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertIn("no-store", respuesta["Cache-Control"])
        # Consumir el streaming deja que el cliente de pruebas cierre la
        # respuesta sin disparar el cierre de la conexión de su transacción.
        self.assertTrue(b"".join(respuesta.streaming_content).startswith(b"\x89PNG"))
        self.client.force_login(self.otro)
        self.assertNotContains(self.client.get("/arriendos/"), "ARR-001")
        self.assertEqual(self.client.get(f"/arriendos/{arriendo.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/arriendos/{arriendo.pk}/firma/entrega/").status_code, 404)

    def test_firma_vacia_y_falta_confirmacion_no_crean_arriendo(self):
        solicitud = self.preparar()
        self.client.force_login(self.usuario)
        ruta = f"/arriendos/solicitudes/entrega/{solicitud.pk}/"
        self.assertContains(self.client.post(ruta, {"confirmar": "on", "firma": self.png(blanco=True)}), "Dibuja tu firma")
        self.client.post(ruta, {"firma": self.png()})
        self.assertFalse(Arriendo.objects.exists())

    def test_cancelacion_entrega_exige_motivo_y_no_reserva_equipo(self):
        solicitud = self.preparar()
        ruta = f"/arriendos/solicitudes/entrega/{solicitud.pk}/cancelar/"
        self.assertEqual(self.client.post(ruta, {"confirmar": "on", "motivo": "   "}).status_code, 200)
        self.client.post(ruta, {"confirmar": "on", "motivo": "Error al preparar"})
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.cancelada_por, self.admin)
        self.client.force_login(self.usuario)
        self.assertContains(self.client.post(f"/arriendos/solicitudes/entrega/{solicitud.pk}/", {"confirmar": "on", "firma": self.png()}), "cancelada o venció")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")

    def test_personal_sin_permiso_no_prepara_entregas_y_post_exige_csrf(self):
        from django.test import Client
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get("/arriendos/entrega/nueva/").status_code, 403)
        self.assertEqual(self.client.post("/arriendos/entrega/nueva/", {}).status_code, 403)
        solicitud = self.preparar()
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.usuario)
        self.assertEqual(estricto.post(f"/arriendos/solicitudes/entrega/{solicitud.pk}/", {"confirmar": "on", "firma": self.png()}).status_code, 403)

    def test_fallo_historial_revierte_entrega_y_elimina_solo_su_archivo(self):
        from django.core.files.storage import default_storage
        solicitud = self.preparar()
        try:
            antes = set(default_storage.listdir("firmas/entregas")[1])
        except FileNotFoundError:
            antes = set()
        self.client.force_login(self.usuario)
        with patch("maquinaria.servicios_arriendos.registrar_evento", side_effect=RuntimeError("Fallo de historial")):
            with self.assertRaises(RuntimeError):
                self.client.post(f"/arriendos/solicitudes/entrega/{solicitud.pk}/", {"confirmar": "on", "firma": self.png()})
        self.assertFalse(Arriendo.objects.exists())
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertEqual(set(default_storage.listdir("firmas/entregas")[1]), antes)

    def test_recepcion_sin_confirmacion_no_mueve_maquina(self):
        arriendo = self.entregar()
        self.client.force_login(self.admin)
        self.client.post(f"/arriendos/{arriendo.pk}/recibir/", {"bodega": self.recepcion.pk, "observaciones": "Prueba"})
        arriendo.refresh_from_db()
        self.maquina.refresh_from_db()
        self.assertIsNone(arriendo.recibido_en)
        self.assertEqual(self.maquina.bodega, self.bodega)



class ContadorUsoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_timer", rut="12345678-5", password="ClaveAdmin!4820")
        cls.empresa = Empresa.objects.create(rut="76123456-0", razon_social="Empresa timer")
        cls.usuario = Usuario.objects.create_user(username="responsable_timer", rut="11111111-1", empresa=cls.empresa, estado_aprobacion="APROBADO")
        cls.otro = Usuario.objects.create_user(username="otro_timer", rut="22222222-2", empresa=cls.empresa, estado_aprobacion="APROBADO")
        cls.obra = Obra.objects.create(nombre="Obra timer", direccion="Calle Obra 100")
        cls.bodega = Bodega.objects.create(nombre="Bodega timer", direccion="Calle Bodega 200")
        cls.maquina = Maquinaria.objects.create(codigo="TIMER-001", nombre="Equipo timer", bodega=cls.bodega,
            estado="EN_USO", revision_pendiente=False, ultima_mantencion_conocida=True,
            tiempo_uso_acumulado=timedelta(hours=240))
        terminos = TerminosCondiciones.objects.create(version="timer-1", contenido="Prueba de contador")
        ahora = timezone.now()
        aceptacion = AceptacionTerminos.objects.create(usuario=cls.usuario, terminos=terminos, aceptado_en=ahora, firmado_en=ahora, firma="prueba.png")
        cls.arriendo = Arriendo.objects.create(maquinaria=cls.maquina, empresa=cls.empresa, responsable=cls.usuario,
            obra_destino=cls.obra, aceptacion=aceptacion, entregado_en=ahora - timedelta(days=1),
            devolucion_prevista=ahora + timedelta(days=2), tarifa_diaria=100, firma_entrega="prueba.png")

    def setUp(self):
        self.client.force_login(self.usuario)

    def operar(self, accion):
        return self.client.post(f"/arriendos/{self.arriendo.pk}/uso/{accion}/")

    def estado(self):
        return self.client.post(f"/arriendos/{self.arriendo.pk}/uso/estado/")

    def test_iniciar_registra_autor_y_rechaza_segundo_inicio(self):
        self.assertRedirects(self.operar("iniciar"), f"/arriendos/{self.arriendo.pk}/")
        sesion = SesionUso.objects.get()
        self.assertEqual(sesion.iniciada_por, self.usuario)
        self.assertIsNone(sesion.fin)
        self.operar("iniciar")
        self.assertEqual(SesionUso.objects.count(), 1)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=240))

    def test_pausa_suma_una_vez_y_guarda_motivo(self):
        inicio = timezone.now()
        with patch("maquinaria.servicios_uso.timezone.now", return_value=inicio):
            self.operar("iniciar")
        with patch("maquinaria.servicios_uso.timezone.now", return_value=inicio + timedelta(hours=2)):
            self.operar("pausar")
        sesion = SesionUso.objects.get()
        self.assertEqual(sesion.fin - sesion.inicio, timedelta(hours=2))
        self.assertEqual(sesion.cerrada_por, self.usuario)
        self.assertEqual(sesion.motivo_cierre, "Pausa del responsable")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=242))
        self.operar("pausar")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=242))
        self.operar("iniciar")
        self.assertEqual(SesionUso.objects.count(), 2)

    def test_sincronizar_muestra_tiempo_sin_escribir_horas_acumuladas(self):
        inicio = timezone.now()
        SesionUso.objects.create(arriendo=self.arriendo, inicio=inicio, iniciada_por=self.usuario)
        with patch("maquinaria.servicios_uso.timezone.now", return_value=inicio + timedelta(minutes=5)):
            datos = self.estado().json()
        self.assertTrue(datos["sesion_activa"])
        self.assertEqual(datos["segundos_sesion"], 300)
        self.assertEqual(datos["segundos_arriendo"], 300)
        self.assertEqual(datos["segundos_totales"], 240 * 3600 + 300)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=240))

    def test_250_horas_alerta_sin_detener_sesion_y_no_duplica_revision(self):
        inicio = timezone.now()
        sesion = SesionUso.objects.create(arriendo=self.arriendo, inicio=inicio, iniciada_por=self.usuario)
        with patch("maquinaria.servicios_uso.timezone.now", return_value=inicio + timedelta(hours=10)):
            self.assertTrue(self.estado().json()["revision_pendiente"])
            self.estado()
        sesion.refresh_from_db()
        self.maquina.refresh_from_db()
        self.assertIsNone(sesion.fin)
        self.assertTrue(self.maquina.revision_pendiente)
        self.assertEqual(self.maquina.estado, "EN_USO")
        self.assertEqual(self.maquina.mantenimientos.count(), 1)
        self.assertEqual(self.maquina.movimientos.filter(tipo="ALERTA_USO").count(), 1)
        with patch("maquinaria.servicios_uso.timezone.now", return_value=inicio + timedelta(hours=10)):
            self.operar("pausar")
            self.operar("iniciar")
        self.assertEqual(SesionUso.objects.count(), 1)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=250))
        self.assertEqual(self.maquina.mantenimientos.count(), 1)

    def test_inicio_denegado_por_250_horas_conserva_orden_y_alerta(self):
        self.maquina.tiempo_uso_acumulado = timedelta(hours=250)
        self.maquina.save()
        self.operar("iniciar")
        self.maquina.refresh_from_db()
        self.assertFalse(SesionUso.objects.exists())
        self.assertTrue(self.maquina.revision_pendiente)
        self.assertEqual(self.maquina.mantenimientos.count(), 1)

    def test_recepcion_fisica_cierra_sesion_y_no_permite_reinicio(self):
        inicio = timezone.now()
        SesionUso.objects.create(arriendo=self.arriendo, inicio=inicio, iniciada_por=self.usuario)
        self.client.force_login(self.admin)
        with patch("maquinaria.servicios_arriendos.timezone.now", return_value=inicio + timedelta(hours=1)):
            self.client.post(f"/arriendos/{self.arriendo.pk}/recibir/", {"bodega": self.bodega.pk,
                "observaciones": "Recibido en bodega", "confirmar": "on"})
        sesion = SesionUso.objects.get()
        self.assertEqual(sesion.cerrada_por, self.admin)
        self.assertEqual(sesion.motivo_cierre, "Recepción física del equipo")
        self.client.force_login(self.usuario)
        self.operar("iniciar")
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=241))
        self.assertEqual(SesionUso.objects.count(), 1)
        datos = self.estado().json()
        self.assertTrue(datos["recibido"])
        self.assertFalse(datos["puede_iniciar"])

    def test_recepcion_que_cruza_intervalo_asegura_revision_sin_firma_final(self):
        inicio = timezone.now()
        SesionUso.objects.create(arriendo=self.arriendo, inicio=inicio)
        self.client.force_login(self.admin)
        with patch("maquinaria.servicios_arriendos.timezone.now", return_value=inicio + timedelta(hours=10)):
            self.client.post(f"/arriendos/{self.arriendo.pk}/recibir/", {"bodega": self.bodega.pk,
                "observaciones": "Recibido al cumplir intervalo", "confirmar": "on"})
        self.maquina.refresh_from_db()
        self.arriendo.refresh_from_db()
        self.assertTrue(self.maquina.revision_pendiente)
        self.assertEqual(self.maquina.mantenimientos.count(), 1)
        self.assertIsNone(self.arriendo.devuelto_en)

    def test_personal_puede_detener_pero_no_iniciar_por_el_responsable(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.operar("iniciar").status_code, 403)
        SesionUso.objects.create(arriendo=self.arriendo, inicio=timezone.now() - timedelta(minutes=5), iniciada_por=self.usuario)
        self.assertRedirects(self.operar("pausar"), f"/arriendos/{self.arriendo.pk}/")
        sesion = SesionUso.objects.get()
        self.assertEqual(sesion.cerrada_por, self.admin)
        self.assertEqual(sesion.motivo_cierre, "Detención por personal autorizado")

    def test_otro_contratista_no_ve_ni_opera_contador_ajeno(self):
        self.client.force_login(self.otro)
        self.assertEqual(self.operar("iniciar").status_code, 404)
        self.assertEqual(self.operar("pausar").status_code, 404)
        self.assertEqual(self.estado().status_code, 404)

    def test_empresa_bloqueada_no_impide_trabajo_de_arriendo_existente(self):
        self.empresa.bloqueada = True
        self.empresa.save()
        self.operar("iniciar")
        self.assertEqual(SesionUso.objects.count(), 1)

    def test_revisiones_por_fecha_y_estado_incompatible_impiden_iniciar(self):
        from .models import Mantenimiento
        Mantenimiento.objects.create(maquinaria=self.maquina, fecha_programada=timezone.localdate(), descripcion="Revisión exigible")
        self.operar("iniciar")
        self.assertFalse(SesionUso.objects.exists())
        self.maquina.estado = "BAJA"
        self.maquina.save()
        self.operar("iniciar")
        self.assertFalse(SesionUso.objects.exists())

    def test_fechas_invalidas_no_generan_horas_negativas(self):
        futuro = timezone.now() + timedelta(hours=1)
        SesionUso.objects.create(arriendo=self.arriendo, inicio=futuro)
        self.operar("pausar")
        sesion = SesionUso.objects.get()
        self.assertIsNone(sesion.fin)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=240))
        self.assertEqual(self.estado().status_code, 400)

    def test_pausa_y_recepcion_comparten_cierre_sin_contabilizar_dos_veces(self):
        inicio = timezone.now()
        SesionUso.objects.create(arriendo=self.arriendo, inicio=inicio)
        with patch("maquinaria.servicios_uso.timezone.now", return_value=inicio + timedelta(hours=1)):
            self.operar("pausar")
        self.client.force_login(self.admin)
        with patch("maquinaria.servicios_arriendos.timezone.now", return_value=inicio + timedelta(hours=2)):
            self.client.post(f"/arriendos/{self.arriendo.pk}/recibir/", {"bodega": self.bodega.pk,
                "observaciones": "Recepción posterior a pausa", "confirmar": "on"})
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=241))

    def test_fallo_revision_revierte_pausa_y_acumulacion(self):
        sesion = SesionUso.objects.create(arriendo=self.arriendo, inicio=timezone.now() - timedelta(minutes=5))
        with patch("maquinaria.servicios_uso.asegurar_revision_por_uso", side_effect=RuntimeError("Fallo simulado")):
            with self.assertRaises(RuntimeError):
                self.operar("pausar")
        sesion.refresh_from_db()
        self.maquina.refresh_from_db()
        self.assertIsNone(sesion.fin)
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=240))

    def test_interfaz_contador_historial_cache_y_csrf(self):
        from django.test import Client
        self.assertContains(self.client.get(f"/arriendos/{self.arriendo.pk}/"), "Horas de trabajo")
        self.operar("iniciar")
        self.assertContains(self.client.get(f"/arriendos/{self.arriendo.pk}/"), "Historial de sesiones")
        respuesta = self.estado()
        self.assertIn("no-store", respuesta["Cache-Control"])
        self.assertEqual(self.client.get(f"/arriendos/{self.arriendo.pk}/uso/iniciar/").status_code, 405)
        self.assertEqual(self.client.get(f"/arriendos/{self.arriendo.pk}/uso/estado/").status_code, 405)
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.usuario)
        self.assertEqual(estricto.post(f"/arriendos/{self.arriendo.pk}/uso/pausar/").status_code, 403)
        self.assertEqual(estricto.post(f"/arriendos/{self.arriendo.pk}/uso/estado/").status_code, 403)



class BloqueosAtrasosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_bloqueos", rut="12345678-5", password="ClaveAdmin!4820")
        cls.empresa = Empresa.objects.create(rut="76123456-0", razon_social="Empresa con atrasos")
        cls.otra_empresa = Empresa.objects.create(rut="11111111-1", razon_social="Empresa ajena")
        cls.usuario = Usuario.objects.create_user(username="usuario_bloqueos", rut="22222222-2", empresa=cls.empresa, estado_aprobacion="APROBADO")
        cls.companero = Usuario.objects.create_user(username="companero_bloqueos", rut="33333333-3", empresa=cls.empresa, estado_aprobacion="APROBADO")
        cls.ajeno = Usuario.objects.create_user(username="ajeno_bloqueos", rut="44444444-4", empresa=cls.otra_empresa, estado_aprobacion="APROBADO")
        cls.bodega = Bodega.objects.create(nombre="Bodega atrasos", direccion="Calle Bodega 100")
        cls.obra = Obra.objects.create(nombre="Obra atrasos", direccion="Calle Obra 200")
        cls.terminos = TerminosCondiciones.objects.create(version="bloqueos-1", contenido="Prueba de bloqueos")
        ahora = timezone.now()
        cls.aceptacion = AceptacionTerminos.objects.create(usuario=cls.usuario, terminos=cls.terminos, aceptado_en=ahora - timedelta(days=4), firmado_en=ahora - timedelta(days=4), firma="prueba.png")
        cls.maquina = Maquinaria.objects.create(codigo="ATR-001", nombre="Equipo atrasado", bodega=cls.bodega, estado="EN_USO", revision_pendiente=False)
        cls.arriendo = Arriendo.objects.create(maquinaria=cls.maquina, empresa=cls.empresa, responsable=cls.usuario,
            obra_destino=cls.obra, aceptacion=cls.aceptacion, entregado_en=ahora - timedelta(days=3),
            devolucion_prevista=ahora - timedelta(days=1), tarifa_diaria=100, firma_entrega="prueba.png")

    def setUp(self):
        self.client.force_login(self.admin)

    def actualizar(self):
        from .servicios_bloqueos import actualizar_bloqueo_por_atraso
        return actualizar_bloqueo_por_atraso(self.empresa.pk)

    def nueva_maquina(self):
        return Maquinaria.objects.create(codigo="ATR-002", nombre="Equipo disponible", bodega=self.bodega,
                                        revision_pendiente=False, ultima_mantencion_conocida=True)

    def datos_entrega(self, maquina):
        from decimal import Decimal
        return {"maquinaria": maquina, "empresa": self.empresa, "responsable": self.usuario,
                "direccion_uso": "Calle Obra 100", "comuna_uso": "Santiago", "devolucion_prevista": timezone.now() + timedelta(days=1),
                "tarifa_diaria": Decimal("100"), "observaciones": "Prueba"}

    def test_detecta_atraso_y_revisiones_repetidas_no_duplican_eventos(self):
        from .models import HistorialBloqueoEmpresa
        self.assertTrue(self.actualizar().bloqueada_por_atraso)
        self.actualizar()
        self.actualizar()
        self.assertEqual(HistorialBloqueoEmpresa.objects.count(), 1)
        evento = HistorialBloqueoEmpresa.objects.get()
        self.assertEqual(evento.origen, "AUTOMATICO")
        self.assertEqual(evento.accion, "BLOQUEO")
        self.assertIsNone(evento.responsable)
        self.assertFalse(self.otra_empresa.bloqueada_por_atraso)

    def test_recepcion_fisica_quita_atraso_sin_necesitar_firma_de_devolucion(self):
        self.actualizar()
        respuesta = self.client.post(f"/arriendos/{self.arriendo.pk}/recibir/", {"bodega": self.bodega.pk,
            "observaciones": "Recibido fuera de plazo", "confirmar": "on"})
        self.assertEqual(respuesta.status_code, 302)
        self.arriendo.refresh_from_db()
        self.empresa.refresh_from_db()
        self.assertIsNotNone(self.arriendo.recibido_en)
        self.assertIsNone(self.arriendo.devuelto_en)
        self.assertFalse(self.empresa.bloqueada_por_atraso)
        self.assertEqual(self.empresa.historial_bloqueos.count(), 2)

    def test_con_varios_atrasos_se_desbloquea_solo_tras_ultima_recepcion(self):
        segunda_maquina = Maquinaria.objects.create(codigo="ATR-003", nombre="Segundo atrasado", bodega=self.bodega, estado="EN_USO")
        segundo = Arriendo.objects.create(maquinaria=segunda_maquina, empresa=self.empresa, responsable=self.companero,
            obra_destino=self.obra, aceptacion=self.aceptacion, entregado_en=self.arriendo.entregado_en,
            devolucion_prevista=self.arriendo.devolucion_prevista, tarifa_diaria=100, firma_entrega="prueba.png")
        self.actualizar()
        self.client.post(f"/arriendos/{self.arriendo.pk}/recibir/", {"bodega": self.bodega.pk, "observaciones": "Primer equipo", "confirmar": "on"})
        self.empresa.refresh_from_db()
        self.assertTrue(self.empresa.bloqueada_por_atraso)
        self.client.post(f"/arriendos/{segundo.pk}/recibir/", {"bodega": self.bodega.pk, "observaciones": "Segundo equipo", "confirmar": "on"})
        self.empresa.refresh_from_db()
        self.assertFalse(self.empresa.bloqueada_por_atraso)
        self.assertEqual(self.empresa.historial_bloqueos.count(), 2)

    def test_desbloqueo_automatico_conserva_bloqueo_manual_anterior(self):
        self.empresa.bloqueada = True
        self.empresa.motivo_bloqueo = "Incidente independiente del atraso"
        self.empresa.save()
        self.actualizar()
        self.arriendo.recibido_en = timezone.now()
        self.arriendo.save()
        empresa = self.actualizar()
        self.assertFalse(empresa.bloqueada_por_atraso)
        self.assertTrue(empresa.bloqueada)
        self.assertTrue(empresa.tiene_bloqueo)
        self.assertEqual(empresa.motivo_bloqueo, "Incidente independiente del atraso")

    def test_retirar_manual_no_quita_automatico_y_registra_actor(self):
        from .servicios_bloqueos import cambiar_bloqueo_manual
        self.actualizar()
        cambiar_bloqueo_manual(empresa_id=self.empresa.pk, bloquear=True, motivo="Incidente", responsable=self.admin)
        empresa = cambiar_bloqueo_manual(empresa_id=self.empresa.pk, bloquear=False, motivo="Incidente resuelto", responsable=self.admin)
        self.assertFalse(empresa.bloqueada)
        self.assertTrue(empresa.bloqueada_por_atraso)
        self.assertTrue(empresa.tiene_bloqueo)
        eventos = empresa.historial_bloqueos.filter(origen="MANUAL")
        self.assertEqual(eventos.count(), 2)
        self.assertTrue(all(evento.responsable == self.admin for evento in eventos))

    def test_preparar_entrega_detecta_atraso_sin_tarea_periodica_y_conserva_bloqueo(self):
        from django.core.exceptions import ValidationError
        from .servicios_arriendos import preparar_entrega
        maquina = self.nueva_maquina()
        with self.assertRaises(ValidationError):
            preparar_entrega(datos=self.datos_entrega(maquina), responsable=self.admin)
        self.empresa.refresh_from_db()
        self.assertTrue(self.empresa.bloqueada_por_atraso)
        self.assertEqual(self.empresa.historial_bloqueos.count(), 1)

    def test_firma_entrega_detecta_atraso_aunque_solicitud_se_preparo_antes(self):
        from django.core.exceptions import ValidationError
        from .models import SolicitudEntrega
        from .servicios_arriendos import confirmar_entrega
        maquina = self.nueva_maquina()
        solicitud = SolicitudEntrega.objects.create(**self.datos_entrega(maquina), terminos=self.terminos, preparada_por=self.admin)
        with self.assertRaises(ValidationError):
            confirmar_entrega(solicitud_id=solicitud.pk, usuario=self.usuario, firma=None)
        self.empresa.refresh_from_db()
        maquina.refresh_from_db()
        self.assertTrue(self.empresa.bloqueada_por_atraso)
        self.assertEqual(maquina.estado, "DISPONIBLE")
        self.assertFalse(Arriendo.objects.filter(maquinaria=maquina).exists())

    def test_plazo_no_vencido_o_cerrado_no_genera_atraso(self):
        from .servicios_bloqueos import arriendos_atrasados
        ahora = timezone.now()
        self.arriendo.devolucion_prevista = ahora
        self.arriendo.save()
        with patch("maquinaria.servicios_bloqueos.timezone.now", return_value=ahora):
            self.assertFalse(arriendos_atrasados(self.empresa.pk).exists())
        self.arriendo.devolucion_prevista = ahora - timedelta(hours=1)
        self.arriendo.devuelto_en = ahora
        self.arriendo.save()
        self.assertFalse(self.actualizar().bloqueada_por_atraso)

    def test_comando_es_idempotente_y_permite_empresa_especifica(self):
        from io import StringIO
        from django.core.management import call_command
        salida = StringIO()
        call_command("revisar_atrasos", stdout=salida)
        self.assertIn("Cambios de bloqueo automático: 1", salida.getvalue())
        call_command("revisar_atrasos", empresa=self.empresa.pk, stdout=StringIO())
        self.assertEqual(self.empresa.historial_bloqueos.count(), 1)
        self.arriendo.recibido_en = timezone.now()
        self.arriendo.save()
        call_command("revisar_atrasos", stdout=StringIO())
        self.empresa.refresh_from_db()
        self.assertFalse(self.empresa.bloqueada_por_atraso)

    def test_privacidad_por_empresa_y_por_responsable_en_alertas(self):
        self.client.force_login(self.companero)
        respuesta = self.client.get("/alertas/atrasos/")
        self.assertEqual(respuesta.context["total_atrasos"], 1)
        self.assertNotContains(respuesta, "ATR-001")
        self.assertContains(respuesta, "solo se muestran tus propios arriendos")
        self.assertEqual(self.client.get(f"/empresas/{self.otra_empresa.pk}/bloqueos/").status_code, 404)
        self.assertEqual(self.client.get(f"/empresas/{self.empresa.pk}/bloqueos/").status_code, 200)
        self.client.force_login(self.ajeno)
        self.assertNotContains(self.client.get("/alertas/atrasos/"), "Empresa con atrasos")

    def test_contratista_ve_aviso_sin_perder_acceso_a_cuenta_o_arriendo(self):
        self.client.force_login(self.usuario)
        for ruta in ["/", "/perfil/", "/arriendos/"]:
            self.assertContains(self.client.get(ruta), "Tu empresa está bloqueada para nuevos arriendos")
        self.assertEqual(self.client.get(f"/arriendos/{self.arriendo.pk}/").status_code, 200)

    def test_bloqueo_manual_exige_permiso_motivo_y_confirmacion(self):
        ruta = f"/empresas/{self.empresa.pk}/bloqueo/bloquear/"
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(ruta, {"motivo": "Prueba", "confirmar": "on"}).status_code, 403)
        self.client.force_login(self.admin)
        for datos in [{"motivo": "   ", "confirmar": "on"}, {"motivo": "Prueba"}]:
            respuesta = self.client.post(ruta, datos)
            self.assertTrue(respuesta.context["form"].errors)
        self.empresa.refresh_from_db()
        self.assertFalse(self.empresa.bloqueada)
        self.assertFalse(self.empresa.historial_bloqueos.filter(origen="MANUAL").exists())

    def test_formulario_manual_registra_cambios_y_rechaza_repeticion(self):
        ruta = f"/empresas/{self.empresa.pk}/bloqueo/bloquear/"
        self.assertRedirects(self.client.post(ruta, {"motivo": "Incidente de prueba", "confirmar": "on"}), f"/empresas/{self.empresa.pk}/bloqueos/")
        self.assertContains(self.client.post(ruta, {"motivo": "Repetido", "confirmar": "on"}), "ya tiene ese estado")
        self.assertEqual(self.empresa.historial_bloqueos.filter(origen="MANUAL").count(), 1)

    def test_fallo_historial_revierte_cambio_automatico_y_manual(self):
        from .servicios_bloqueos import cambiar_bloqueo_manual
        with patch("maquinaria.servicios_bloqueos.HistorialBloqueoEmpresa.objects.create", side_effect=RuntimeError("Fallo simulado")):
            with self.assertRaises(RuntimeError):
                self.actualizar()
            with self.assertRaises(RuntimeError):
                cambiar_bloqueo_manual(empresa_id=self.empresa.pk, bloquear=True, motivo="Prueba", responsable=self.admin)
        self.empresa.refresh_from_db()
        self.assertFalse(self.empresa.bloqueada_por_atraso)
        self.assertFalse(self.empresa.bloqueada)

    def test_panel_personal_muestra_atrasos_y_empresas(self):
        respuesta = self.client.get("/alertas/atrasos/")
        self.assertContains(respuesta, "ATR-001")
        self.assertContains(respuesta, "Empresa ajena")
        self.assertContains(self.client.get(f"/empresas/{self.empresa.pk}/bloqueos/"), "Automático por atraso")

    def test_csrf_y_consulta_no_aplican_bloqueo_manual(self):
        from django.test import Client
        ruta = f"/empresas/{self.empresa.pk}/bloqueo/bloquear/"
        self.assertEqual(self.client.get(ruta).status_code, 200)
        self.empresa.refresh_from_db()
        self.assertFalse(self.empresa.bloqueada)
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.admin)
        self.assertEqual(estricto.post(ruta, {"motivo": "Prueba", "confirmar": "on"}).status_code, 403)

    def test_permiso_bloqueos_no_concede_acceso_a_contratos_ajenos(self):
        from django.contrib.auth.models import Permission
        interno = Usuario.objects.create_user(username="gestor_solo_bloqueos", rut="55555555-5", rol="ADMINISTRADOR")
        interno.user_permissions.add(Permission.objects.get(codename="gestionar_bloqueos_empresa"))
        self.client.force_login(interno)
        respuesta = self.client.get("/alertas/atrasos/")
        self.assertContains(respuesta, "Empresa con atrasos")
        self.assertNotContains(respuesta, "ATR-001")
        self.assertEqual(self.client.get(f"/empresas/{self.empresa.pk}/bloqueos/").status_code, 200)
        self.assertEqual(self.client.get(f"/arriendos/{self.arriendo.pk}/").status_code, 404)


class AdministracionUsuariosTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import Permission
        cls.super = Usuario.objects.create_superuser(username="super_cuentas", rut="11111111-1", password="ClaveSegura!4820")
        cls.otro_super = Usuario.objects.create_superuser(username="otro_super_cuentas", rut="22222222-2", password="ClaveSegura!4820")
        cls.admin = Usuario.objects.create_user(username="admin_cuentas", rut="33333333-3", rol="ADMINISTRADOR", password="ClaveSegura!4820")
        cls.admin.user_permissions.add(*Permission.objects.filter(codename__in=["gestionar_usuarios", "add_maquinaria", "view_mantenimiento"]))
        cls.bodeguero = Usuario.objects.create_user(username="bodeguero_cuentas", rut="44444444-4", rol="BODEGUERO", password="ClaveSegura!4820")
        cls.empresa = Empresa.objects.create(rut="76123456-0", razon_social="Empresa cuentas")
        cls.cliente = Usuario.objects.create_user(username="cliente_cuentas", rut="55555555-5", empresa=cls.empresa, estado_aprobacion="APROBADO", password="ClaveSegura!4820")
        cls.pendiente = Usuario.objects.create_user(username="pendiente_cuentas", rut="66666666-6", empresa=cls.empresa, is_active=False, password="ClaveSegura!4820")

    def setUp(self):
        self.client.force_login(self.super)

    def datos_creacion(self, **cambios):
        datos = {"username": "nueva_cuenta", "first_name": "Ana", "last_name": "Soto",
                 "rut": "77.777.777-7", "email": "ana@example.com", "rol": "BODEGUERO",
                 "password1": "NuevaClave!4820", "password2": "NuevaClave!4820", "motivo": "Incorporación al equipo"}
        datos.update(cambios)
        return datos

    def test_crear_bodeguero_asigna_perfil_y_guarda_password_segura_sin_filtrarla_al_historial(self):
        respuesta = self.client.post("/usuarios/nuevo/", self.datos_creacion())
        nuevo = Usuario.objects.get(username="nueva_cuenta")
        self.assertRedirects(respuesta, f"/usuarios/{nuevo.pk}/")
        self.assertEqual(nuevo.rut, "77777777-7")
        self.assertTrue(nuevo.is_active)
        self.assertFalse(nuevo.is_superuser)
        self.assertFalse(nuevo.suspendida)
        self.assertTrue(nuevo.check_password("NuevaClave!4820"))
        self.assertNotEqual(nuevo.password, "NuevaClave!4820")
        self.assertIn("maquinaria.gestionar_arriendos", nuevo.get_all_permissions())
        self.assertNotIn("maquinaria.gestionar_usuarios", nuevo.get_all_permissions())
        evento = nuevo.historial_administracion.get()
        self.assertEqual(evento.responsable, self.super)
        self.assertNotIn("password", evento.datos_nuevos)
        self.assertNotIn("NuevaClave!4820", str(evento.datos_nuevos))

    def test_superusuario_puede_crear_otro_desde_template(self):
        self.client.post("/usuarios/nuevo/", self.datos_creacion(rol="ADMINISTRADOR", crear_superusuario="on"))
        nuevo = Usuario.objects.get(username="nueva_cuenta")
        self.assertTrue(nuevo.is_superuser)
        self.assertTrue(nuevo.is_staff)
        self.assertEqual(nuevo.rol, "ADMINISTRADOR")
        self.assertTrue(nuevo.has_perm("maquinaria.gestionar_usuarios"))

    def test_admin_comun_no_crea_superusuarios_ni_otorga_mas_de_sus_permisos(self):
        self.client.force_login(self.admin)
        self.assertNotContains(self.client.get("/usuarios/nuevo/"), 'name="crear_superusuario"')
        self.client.post("/usuarios/nuevo/", self.datos_creacion(rol="ADMINISTRADOR", crear_superusuario="on", is_superuser="true"))
        nuevo = Usuario.objects.get(username="nueva_cuenta")
        self.assertFalse(nuevo.is_superuser)
        self.assertTrue(nuevo.get_all_permissions().issubset(self.admin.get_all_permissions()))

    def test_no_crea_contratistas_internos_ni_rut_duplicado_o_invalido(self):
        for cambios in [{"rol": "CONTRATISTA"}, {"rut": "44.444.444-4"}, {"rut": "12345678-9"}]:
            respuesta = self.client.post("/usuarios/nuevo/", self.datos_creacion(**cambios))
            self.assertEqual(respuesta.status_code, 200)
            self.assertTrue(respuesta.context["form"].errors)
            self.assertFalse(Usuario.objects.filter(username="nueva_cuenta").exists())

    def test_cuentas_sin_permiso_o_rol_administrativo_no_entran(self):
        from django.contrib.auth.models import Permission
        self.bodeguero.user_permissions.add(Permission.objects.get(codename="gestionar_usuarios"))
        for cuenta in [self.bodeguero, self.cliente]:
            self.client.force_login(cuenta)
            self.assertEqual(self.client.get("/usuarios/").status_code, 403)
            self.assertEqual(self.client.post("/usuarios/nuevo/", self.datos_creacion()).status_code, 403)

    def test_no_puede_modificar_su_propia_cuenta(self):
        from .models import HistorialAdministracionUsuario
        self.assertContains(self.client.get(f"/usuarios/{self.super.pk}/"), "solo consulta")
        self.assertRedirects(self.client.post(f"/usuarios/{self.super.pk}/desactivar/", {"motivo": "Prueba", "confirmar": "on"}), f"/usuarios/{self.super.pk}/")
        self.super.refresh_from_db()
        self.assertTrue(self.super.is_active)
        self.assertFalse(HistorialAdministracionUsuario.objects.exists())

    def test_admin_comun_no_modifica_superusuarios(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(f"/usuarios/{self.super.pk}/desactivar/", {"motivo": "Prueba", "confirmar": "on"}).status_code, 403)
        self.assertEqual(self.client.get(f"/usuarios/{self.super.pk}/permisos/").status_code, 403)

    def test_no_oculta_privilegios_de_una_cuenta_inactiva(self):
        from django.contrib.auth.models import Permission
        self.bodeguero.user_permissions.add(Permission.objects.get(codename="finalizar_mantenimiento"))
        self.bodeguero.is_active = False
        self.bodeguero.save()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(f"/usuarios/{self.bodeguero.pk}/activar/", {"motivo": "Prueba", "confirmar": "on"}).status_code, 403)

    def test_validacion_servidor_rechaza_permisos_superiores_y_superusuario_falsificado(self):
        from django.contrib.auth.models import Permission
        from django.core.exceptions import PermissionDenied
        from .servicios_usuarios import cambiar_permisos_usuario
        permiso = Permission.objects.get(codename="gestionar_arriendos")
        self.client.force_login(self.admin)
        respuesta = self.client.post(f"/usuarios/{self.bodeguero.pk}/permisos/", {"rol": "BODEGUERO", "permisos": [permiso.pk], "motivo": "Prueba"})
        self.assertTrue(respuesta.context["form"].errors)
        with self.assertRaises(PermissionDenied):
            cambiar_permisos_usuario(usuario_id=self.bodeguero.pk, datos={"rol": "BODEGUERO", "permisos": [permiso], "motivo": "Prueba"}, actor=self.admin)
        with self.assertRaises(PermissionDenied):
            cambiar_permisos_usuario(usuario_id=self.bodeguero.pk, datos={"rol": "ADMINISTRADOR", "superusuario": True, "permisos": [], "motivo": "Prueba"}, actor=self.admin)

    def test_cambio_roles_y_permisos_guarda_comparacion_en_historial(self):
        from django.contrib.auth.models import Permission
        permiso = Permission.objects.get(codename="gestionar_arriendos")
        respuesta = self.client.post(f"/usuarios/{self.bodeguero.pk}/permisos/", {"rol": "ADMINISTRADOR", "permisos": [permiso.pk], "motivo": "Nuevo responsable de entregas"})
        self.assertRedirects(respuesta, f"/usuarios/{self.bodeguero.pk}/")
        self.bodeguero.refresh_from_db()
        self.assertEqual(self.bodeguero.rol, "ADMINISTRADOR")
        self.assertFalse(self.bodeguero.is_superuser)
        self.assertEqual(self.bodeguero.get_all_permissions(), {"maquinaria.gestionar_arriendos"})
        evento = self.bodeguero.historial_administracion.get()
        self.assertEqual(evento.datos_anteriores["rol"], "BODEGUERO")
        self.assertEqual(evento.datos_nuevos["rol"], "ADMINISTRADOR")

    def test_permisos_de_grupos_se_conservan_sin_grants_externos_nuevos(self):
        from django.contrib.auth.models import Group, Permission
        grupo = Group.objects.create(name="Grupo previo")
        operativo = Permission.objects.get(codename="view_mantenimiento")
        externo = Permission.objects.get(codename="view_group", content_type__app_label="auth")
        grupo.permissions.add(operativo, externo)
        self.bodeguero.groups.add(grupo)
        self.client.post(f"/usuarios/{self.bodeguero.pk}/permisos/", {"rol": "BODEGUERO", "permisos": [operativo.pk], "motivo": "Revisión de permisos"})
        self.bodeguero.refresh_from_db()
        self.assertTrue(self.bodeguero.has_perm("auth.view_group"))
        self.assertTrue(self.bodeguero.has_perm("maquinaria.view_mantenimiento"))
        self.assertFalse(self.bodeguero.groups.exists())
        self.assertEqual(self.bodeguero.historial_administracion.get().datos_anteriores["grupos"], ["Grupo previo"])

    def test_ultimo_superusuario_no_puede_quedar_inhabilitado(self):
        from django.core.exceptions import ValidationError
        from .servicios_usuarios import proteger_ultimo_superusuario
        self.otro_super.is_active = False
        self.otro_super.save()
        with self.assertRaises(ValidationError):
            proteger_ultimo_superusuario(self.super, superusuario=False, activo=True, suspendida=False)
        with self.assertRaises(ValidationError):
            proteger_ultimo_superusuario(self.super, superusuario=True, activo=False, suspendida=True)

    def test_relectura_del_actor_bloquea_permisos_de_sesion_obsoletos(self):
        from django.core.exceptions import PermissionDenied
        from .servicios_usuarios import cambiar_estado_usuario
        Usuario.objects.filter(pk=self.admin.pk).update(is_active=False, suspendida=True)
        with self.assertRaises(PermissionDenied):
            cambiar_estado_usuario(usuario_id=self.bodeguero.pk, activar=False, motivo="Prueba", actor=self.admin)
        self.bodeguero.refresh_from_db()
        self.assertTrue(self.bodeguero.is_active)

    def test_suspender_cuenta_invalida_sesion_existente(self):
        from django.test import Client
        usuario = Client()
        usuario.force_login(self.cliente)
        self.assertEqual(usuario.get("/").status_code, 200)
        self.client.post(f"/usuarios/{self.cliente.pk}/desactivar/", {"motivo": "Suspensión administrativa", "confirmar": "on"})
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.suspendida)
        self.assertFalse(self.cliente.is_active)
        self.assertRedirects(usuario.get("/"), "/ingresar/?next=/")

    def test_activar_contratista_no_aprueba_solicitud(self):
        from django.test import Client
        self.client.post(f"/usuarios/{self.pendiente.pk}/activar/", {"motivo": "Permitir consulta", "confirmar": "on"})
        self.pendiente.refresh_from_db()
        self.assertEqual(self.pendiente.estado_aprobacion, "PENDIENTE")
        self.assertTrue(self.pendiente.is_active)
        usuario = Client()
        self.assertRedirects(usuario.post("/ingresar/", {"username": self.pendiente.username, "password": "ClaveSegura!4820"}), "/solicitud/")
        self.assertNotIn("_auth_user_id", usuario.session)

    def test_suspension_bloquea_consulta_limitada_y_aprobacion_no_la_elimina(self):
        from django.test import Client
        usuario = Client()
        usuario.post("/ingresar/", {"username": self.pendiente.username, "password": "ClaveSegura!4820"})
        self.assertIn("consulta_solicitud", usuario.session)
        self.client.post(f"/usuarios/{self.pendiente.pk}/desactivar/", {"motivo": "Revisión administrativa", "confirmar": "on"})
        self.assertRedirects(usuario.get("/solicitud/"), "/ingresar/")
        self.client.post(f"/cuentas/{self.pendiente.pk}/revisar/", {"accion": "aprobar"})
        self.pendiente.refresh_from_db()
        self.assertEqual(self.pendiente.estado_aprobacion, "APROBADO")
        self.assertTrue(self.pendiente.suspendida)
        self.assertFalse(self.pendiente.is_active)
        self.assertFalse(usuario.login(username=self.pendiente.username, password="ClaveSegura!4820"))

    def test_editar_datos_no_cambia_rut_empresa_rol_ni_privilegios(self):
        self.client.post(f"/usuarios/{self.cliente.pk}/datos/", {"first_name": "Nuevo nombre", "last_name": "Apellido", "email": "cliente@example.com", "motivo": "Corrección", "rol": "ADMINISTRADOR", "is_superuser": "true", "rut": "77777777-7", "empresa": ""})
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.first_name, "Nuevo nombre")
        self.assertEqual(self.cliente.rut, "55555555-5")
        self.assertEqual(self.cliente.empresa_id, self.empresa.pk)
        self.assertEqual(self.cliente.rol, "CONTRATISTA")
        self.assertFalse(self.cliente.is_superuser)

    def test_falla_historial_revierte_creacion_y_cambio_de_estado(self):
        with patch("maquinaria.servicios_usuarios.HistorialAdministracionUsuario.objects.create", side_effect=RuntimeError("Fallo simulado")):
            with self.assertRaises(RuntimeError):
                self.client.post("/usuarios/nuevo/", self.datos_creacion())
            with self.assertRaises(RuntimeError):
                self.client.post(f"/usuarios/{self.bodeguero.pk}/desactivar/", {"motivo": "Prueba", "confirmar": "on"})
        self.assertFalse(Usuario.objects.filter(username="nueva_cuenta").exists())
        self.bodeguero.refresh_from_db()
        self.assertTrue(self.bodeguero.is_active)

    def test_listado_filtros_bootstrap_y_csrf(self):
        from django.test import Client
        from django.contrib.staticfiles import finders
        respuesta = self.client.get("/usuarios/?q=bodeguero&rol=BODEGUERO")
        self.assertEqual(respuesta.context["pagina"].paginator.count, 1)
        self.assertContains(respuesta, "table-responsive")
        self.assertContains(respuesta, "/static/vendor/bootstrap/bootstrap.min.css")
        self.assertContains(self.client.get("/usuarios/nuevo/"), "form-control")
        self.assertTrue(finders.find("vendor/bootstrap/bootstrap.bundle.min.js"))
        self.assertTrue(self.client.get("/usuarios/?rol=INVALIDO").context["form"].errors)
        estricto = Client(enforce_csrf_checks=True)
        estricto.force_login(self.super)
        self.assertEqual(estricto.post("/usuarios/nuevo/", self.datos_creacion()).status_code, 403)

    def test_superusuario_inicial_con_rol_heredado_puede_ser_editado_por_otro_super(self):
        self.client.post(f"/usuarios/{self.otro_super.pk}/permisos/", {"rol": "ADMINISTRADOR", "superusuario": "on", "permisos": [], "motivo": "Ajuste de rol de cuenta inicial"})
        self.otro_super.refresh_from_db()
        self.assertEqual(self.otro_super.rol, "ADMINISTRADOR")
        self.assertTrue(self.otro_super.is_superuser)
