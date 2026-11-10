from datetime import timedelta

from django.contrib.auth.models import Permission
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from .models import (AceptacionTerminos, Arriendo, Bodega, Empresa, Maquinaria,
                     Mantenimiento, Obra, TerminosCondiciones, Usuario)


class APIMantenimientoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_mant_api", rut="11111111-1", password="Clave!4820")
        cls.lector = Usuario.objects.create_user(username="lector_mant_api", rut="22222222-2", rol="BODEGUERO")
        cls.lector.user_permissions.add(Permission.objects.get(codename="view_mantenimiento", content_type__app_label="maquinaria"))
        cls.contratista = Usuario.objects.create_user(username="cliente_mant_api", rut="33333333-3", estado_aprobacion="APROBADO")
        cls.bodega = Bodega.objects.create(nombre="Central API", direccion="Direccion central")
        cls.maquina = Maquinaria.objects.create(codigo="MANT-API", nombre="Equipo API", marca="Marca", modelo="Modelo",
            bodega=cls.bodega, tiempo_uso_acumulado=timedelta(hours=260), tiempo_uso_inicial=timedelta(hours=260),
            ultima_mantencion_conocida=True, revision_pendiente=True, estado="MANTENIMIENTO")

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.admin)

    def programar(self, **cambios):
        datos = {"maquinaria": self.maquina.pk, "fecha_programada": timezone.localdate().isoformat(),
                 "descripcion": "Revision de aceite y componentes"}
        datos.update(cambios)
        return self.api.post("/api/v1/mantenimientos/", datos, format="json")

    def accion(self, pk, accion, **datos):
        return self.api.post(f"/api/v1/mantenimientos/{pk}/{accion}/", datos, format="json")

    def orden(self):
        respuesta = self.programar()
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        return respuesta.data["id"]

    def arriendo_abierto(self):
        empresa = Empresa.objects.create(rut="77777777-7", razon_social="Empresa API")
        obra = Obra.objects.create(nombre="Obra API", direccion="Direccion obra")
        terminos = TerminosCondiciones.objects.create(version="MANT-API", contenido="Condiciones")
        ahora = timezone.now()
        aceptacion = AceptacionTerminos.objects.create(usuario=self.contratista, terminos=terminos,
            aceptado_en=ahora, firmado_en=ahora, firma="perfil.png")
        return Arriendo.objects.create(maquinaria=self.maquina, empresa=empresa, responsable=self.contratista,
            obra_destino=obra, aceptacion=aceptacion, devolucion_prevista=ahora + timedelta(days=3),
            tarifa_diaria=0, firma_entrega="entrega.png")

    def test_flujo_completo_preserva_horas_y_registra_autores_e_historial(self):
        pk = self.orden()
        self.assertEqual(self.accion(pk, "iniciar", confirmar=True).status_code, 200)
        final = self.accion(pk, "finalizar", resultado="Revision satisfactoria", apta_para_servicio=True, confirmar=True)
        self.assertEqual(final.status_code, 200, final.data)
        self.assertEqual(final.data["estado"], "Finalizada")
        for campo in ("programado_por", "responsable", "finalizado_por"):
            self.assertEqual(final.data[campo], self.admin.pk)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=260))
        self.assertEqual(self.maquina.tiempo_uso_ultima_mantencion, timedelta(hours=260))
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertFalse(self.maquina.revision_pendiente)
        self.assertEqual(set(self.maquina.movimientos.values_list("tipo", flat=True)), {"PROG_MANT", "INICIO_MANT", "FIN_MANT"})

    def test_no_apta_conserva_referencia_y_crea_seguimiento(self):
        pk = self.orden()
        self.accion(pk, "iniciar", confirmar=True)
        respuesta = self.accion(pk, "finalizar", resultado="Falla persiste", apta_para_servicio=False, confirmar=True)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")
        self.assertTrue(self.maquina.revision_pendiente)
        self.assertEqual(self.maquina.tiempo_uso_ultima_mantencion, timedelta())
        self.assertEqual(self.maquina.mantenimientos.filter(finalizado_en__isnull=True).count(), 1)
        self.assertIn("Seguimiento", self.maquina.mantenimientos.exclude(pk=pk).get().descripcion)

    def test_otras_ordenes_exigibles_impiden_liberar_maquina(self):
        pk = self.orden()
        self.programar(descripcion="Otra revision pendiente")
        self.accion(pk, "iniciar", confirmar=True)
        self.assertEqual(self.accion(pk, "finalizar", resultado="Correcto", apta_para_servicio=True, confirmar=True).status_code, 200)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")
        self.assertTrue(self.maquina.revision_pendiente)

    def test_solo_lectura_no_puede_operar(self):
        pk = self.orden()
        self.api.force_login(self.lector)
        self.assertEqual(self.api.get("/api/v1/mantenimientos/").status_code, 200)
        self.assertEqual(self.api.get(f"/api/v1/mantenimientos/{pk}/").status_code, 200)
        self.assertEqual(self.programar().status_code, 403)
        self.assertEqual(self.accion(pk, "iniciar", confirmar=True).status_code, 403)
        self.assertEqual(self.accion(pk, "finalizar", confirmar=True).status_code, 403)

    def test_permisos_independientes_para_inicio_y_finalizacion(self):
        pk = self.orden()
        self.lector.user_permissions.add(Permission.objects.get(codename="iniciar_mantenimiento", content_type__app_label="maquinaria"))
        self.api.force_login(self.lector)
        self.assertEqual(self.accion(pk, "iniciar", confirmar=True).status_code, 200)
        self.assertEqual(self.accion(pk, "finalizar", resultado="Correcto", apta_para_servicio=True, confirmar=True).status_code, 403)

    def test_anonimo_contratista_y_suspendido_no_acceden(self):
        self.api.logout()
        self.assertEqual(self.api.get("/api/v1/mantenimientos/").status_code, 403)
        self.api.force_login(self.contratista)
        self.assertEqual(self.api.get("/api/v1/mantenimientos/").status_code, 403)
        self.admin.suspendida = True
        self.api.force_authenticate(user=self.admin)
        self.assertEqual(self.api.get("/api/v1/mantenimientos/").status_code, 403)

    def test_campos_protegidos_y_datos_invalidos_no_crean_orden(self):
        for datos in [{"descripcion": " "}, {"fecha_programada": "incorrecta"}, {"maquinaria": 999999},
                      {"lectura_uso": "0"}, {"programado_por": self.contratista.pk}, {"estado": "Finalizada"}]:
            self.assertEqual(self.programar(**datos).status_code, 400)
        self.assertFalse(Mantenimiento.objects.exists())

    def test_confirmacion_y_resultado_son_obligatorios(self):
        pk = self.orden()
        for datos in [{}, {"confirmar": False}, {"confirmar": True, "iniciado_en": timezone.now().isoformat()}]:
            self.assertEqual(self.accion(pk, "iniciar", **datos).status_code, 400)
        self.accion(pk, "iniciar", confirmar=True)
        for datos in [{"resultado": " "}, {"apta_para_servicio": None}, {"confirmar": False}, {"lectura_uso": "0"}]:
            entrada = {"resultado": "Correcto", "apta_para_servicio": True, "confirmar": True}
            entrada.update(datos)
            self.assertEqual(self.accion(pk, "finalizar", **entrada).status_code, 400)
        self.assertIsNone(Mantenimiento.objects.get(pk=pk).finalizado_en)

    def test_no_admite_finalizar_sin_inicio_ni_repetir_operaciones(self):
        pk = self.orden()
        datos = {"resultado": "Correcto", "apta_para_servicio": True, "confirmar": True}
        self.assertEqual(self.accion(pk, "finalizar", **datos).status_code, 400)
        self.assertEqual(self.accion(pk, "iniciar", confirmar=True).status_code, 200)
        self.assertEqual(self.accion(pk, "iniciar", confirmar=True).status_code, 400)
        self.assertEqual(self.accion(pk, "finalizar", **datos).status_code, 200)
        self.assertEqual(self.accion(pk, "finalizar", **datos).status_code, 400)
        self.assertEqual(self.maquina.movimientos.filter(tipo="FIN_MANT").count(), 1)

    def test_programacion_futura_permite_arriendo_pero_inicio_no(self):
        self.arriendo_abierto()
        Maquinaria.objects.filter(pk=self.maquina.pk).update(estado="EN_USO")
        respuesta = self.programar(fecha_programada=(timezone.localdate() + timedelta(days=2)).isoformat())
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(self.accion(respuesta.data["id"], "iniciar", confirmar=True).status_code, 400)
        self.assertEqual(self.programar().status_code, 400)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "EN_USO")

    def test_baja_o_bodega_inactiva_no_permiten_programar(self):
        Maquinaria.objects.filter(pk=self.maquina.pk).update(estado="BAJA")
        self.assertEqual(self.programar().status_code, 400)
        Maquinaria.objects.filter(pk=self.maquina.pk).update(estado="MANTENIMIENTO")
        Bodega.objects.filter(pk=self.bodega.pk).update(activa=False)
        self.assertEqual(self.programar().status_code, 400)

    def test_duplicado_y_segunda_intervencion_se_rechazan(self):
        pk = self.orden()
        self.assertEqual(self.programar().status_code, 400)
        segunda = self.programar(descripcion="Segunda tarea").data["id"]
        self.accion(pk, "iniciar", confirmar=True)
        self.assertEqual(self.accion(segunda, "iniciar", confirmar=True).status_code, 400)

    def test_filtros_paginacion_y_sufijo_json(self):
        pk = self.orden()
        self.assertEqual(self.api.get("/api/v1/mantenimientos/?estado=pendiente").data["count"], 1)
        self.accion(pk, "iniciar", confirmar=True)
        self.assertEqual(self.api.get("/api/v1/mantenimientos/?estado=pendiente").data["count"], 0)
        self.assertEqual(self.api.get(f"/api/v1/mantenimientos/?estado=curso&maquinaria={self.maquina.pk}").data["count"], 1)
        self.assertEqual(self.api.get(f"/api/v1/mantenimientos/{pk}.json").status_code, 200)
        for query in ("estado=otro", "page=0", "campo=1", "maquinaria=999999"):
            self.assertEqual(self.api.get("/api/v1/mantenimientos/?" + query).status_code, 400)
        self.assertEqual(self.api.get("/api/v1/mantenimientos/?page=2").status_code, 404)

    def test_sin_edicion_eliminacion_y_errores_json(self):
        pk = self.orden()
        for metodo in (self.api.patch, self.api.put, self.api.delete):
            respuesta = metodo(f"/api/v1/mantenimientos/{pk}/", {}, format="json")
            self.assertEqual(respuesta.status_code, 405)
            self.assertTrue(respuesta["Content-Type"].startswith("application/json"))
        self.assertEqual(self.api.get("/api/v1/mantenimientos/999999/").status_code, 404)
        self.assertEqual(self.accion(999999, "iniciar", confirmar=True).status_code, 404)

    def test_csrf_real_se_exige_y_permite_operacion_con_token(self):
        cliente = APIClient(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        pk = self.orden()
        ruta = f"/api/v1/mantenimientos/{pk}/iniciar/"
        self.assertEqual(cliente.post(ruta, {"confirmar": True}, format="json").status_code, 403)
        cliente.get("/perfil/")
        respuesta = cliente.post(ruta, {"confirmar": True}, format="json",
            HTTP_X_CSRFTOKEN=cliente.cookies["csrftoken"].value)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
