from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Bodega, Maquinaria, Obra, Usuario


class APIInventarioTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_api", rut="11111111-1", password="ClaveAdmin!4820")
        cls.cliente = Usuario.objects.create_user(username="cliente_api", rut="22222222-2", estado_aprobacion="APROBADO", password="ClaveCliente!4820")
        cls.bodeguero = Usuario.objects.create_user(username="bodeguero_api", rut="33333333-3", rol="BODEGUERO")
        cls.bodeguero.user_permissions.add(*Permission.objects.filter(content_type__app_label="maquinaria", codename__in=[
            "add_maquinaria", "change_maquinaria", "trasladar_maquinaria", "dar_baja_maquinaria", "reactivar_maquinaria",
            "add_obra", "change_obra", "add_bodega", "change_bodega", "desactivar_bodega", "reactivar_bodega",
        ]))
        cls.obra = Obra.objects.create(nombre="Obra API", direccion="Dirección de obra API")
        cls.obra_vacia = Obra.objects.create(nombre="Obra vacía API", direccion="Dirección de obra vacía")
        cls.bodega = Bodega.objects.create(nombre="Central API", direccion="Dirección central API")
        cls.destino = Bodega.objects.create(nombre="Destino API", direccion="Dirección destino API", obra=cls.obra)
        cls.maquina = Maquinaria.objects.create(codigo="API-001", nombre="Generador API", marca="Marca API", modelo="Modelo API",
            bodega=cls.bodega, tiempo_uso_acumulado=timedelta(hours=10), tiempo_uso_inicial=timedelta(hours=10),
            revision_pendiente=False, ultima_mantencion_conocida=True)

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.admin)

    def alta(self, **cambios):
        datos = {"codigo": " api-002 ", "nombre": "Equipo API nuevo", "marca": "Marca nueva", "modelo": "Modelo nuevo",
                 "bodega": self.bodega.pk, "precio_diario": "25000.00", "horas_iniciales": "100.25", "horas_ultima_mantencion": "50.25"}
        datos.update(cambios)
        return self.api.post("/api/v1/maquinaria/", datos, format="json")

    def accion(self, accion, **cambios):
        datos = {"motivo": "Operación desde API"}
        datos.update(cambios)
        return self.api.post(f"/api/v1/maquinaria/{self.maquina.pk}/{accion}/", datos, format="json")

    def test_api_requiere_sesion_y_devuelve_json_sin_redireccion_a_html(self):
        anonimo = APIClient()
        for ruta in ["/api/v1/", "/api/v1/maquinaria/", "/api/v1/obras/", "/api/v1/bodegas/"]:
            respuesta = anonimo.get(ruta)
            self.assertEqual(respuesta.status_code, 403)
            self.assertTrue(respuesta["Content-Type"].startswith("application/json"))

    def test_raiz_lista_recursos_y_lectura_de_maquina(self):
        respuesta = self.api.get("/api/v1/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(set(respuesta.json()), {"maquinaria", "obras", "bodegas", "arriendos", "entregas", "devoluciones", "mantenimientos", "empresas", "usuarios", "solicitudes", "condiciones", "comprobantes", "solicitudes-arriendo"})
        detalle = self.api.get(f"/api/v1/maquinaria/{self.maquina.pk}/").json()
        self.assertEqual(detalle["bodega_nombre"], "Central API")
        self.assertEqual(detalle["segundos_uso_total"], 36000)
        self.assertNotIn("password", detalle)

    def test_contratista_aprobado_consulta_pero_no_modifica(self):
        self.api.force_login(self.cliente)
        self.assertEqual(self.api.get("/api/v1/maquinaria/").status_code, 200)
        self.assertEqual(self.alta().status_code, 403)
        self.assertEqual(self.api.patch(f"/api/v1/maquinaria/{self.maquina.pk}/", {"nombre": "Intento"}, format="json").status_code, 403)
        self.assertEqual(self.accion("baja").status_code, 403)

    def test_cuenta_pendiente_o_suspendida_no_accede_aunque_se_fuercen_credenciales(self):
        for cambios in [{"estado_aprobacion": "PENDIENTE"}, {"suspendida": True}, {"is_active": False}]:
            cuenta = Usuario.objects.get(pk=self.cliente.pk)
            for campo, valor in cambios.items():
                setattr(cuenta, campo, valor)
            cliente = APIClient()
            cliente.force_authenticate(user=cuenta)
            self.assertEqual(cliente.get("/api/v1/maquinaria/").status_code, 403)

    def test_creacion_usa_servicio_estado_y_registro_inicial(self):
        respuesta = self.alta()
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        maquina = Maquinaria.objects.get(pk=respuesta.json()["id"])
        self.assertEqual(maquina.codigo, "API-002")
        self.assertEqual(maquina.estado, "DISPONIBLE")
        self.assertEqual(maquina.registrado_por, self.admin)
        self.assertEqual(maquina.tiempo_uso_acumulado, timedelta(hours=100, minutes=15))
        self.assertEqual(maquina.movimientos.get().tipo, "ALTA")

    def test_creacion_sin_ultima_mantencion_deja_revision_pendiente(self):
        respuesta = self.alta(horas_ultima_mantencion=None)
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        maquina = Maquinaria.objects.get(pk=respuesta.json()["id"])
        self.assertEqual(maquina.estado, "MANTENIMIENTO")
        self.assertEqual(maquina.mantenimientos.count(), 1)

    def test_creacion_rechaza_lecturas_invalidas_y_codigos_duplicados(self):
        for datos in [{"horas_iniciales": "-1"}, {"horas_ultima_mantencion": "200"}, {"codigo": "api-001"}]:
            respuesta = self.alta(**datos)
            self.assertEqual(respuesta.status_code, 400)
            self.assertTrue(respuesta["Content-Type"].startswith("application/json"))
        self.assertEqual(Maquinaria.objects.count(), 1)

    def test_campos_sensibles_desconocidos_se_rechazan_sin_guardar(self):
        for datos in [{"estado": "DISPONIBLE"}, {"is_superuser": True}, {"tiempo_uso_acumulado": "0"}]:
            respuesta = self.alta(**datos)
            self.assertEqual(respuesta.status_code, 400)
            self.assertIn(next(iter(datos)), respuesta.json())
        self.assertEqual(Maquinaria.objects.count(), 1)

    def test_patch_preserva_campos_no_enviados_y_registra_edicion(self):
        ruta = f"/api/v1/maquinaria/{self.maquina.pk}/"
        self.assertEqual(self.api.patch(ruta, {"marca": "Marca corregida"}, format="json").status_code, 200)
        self.assertEqual(self.api.patch(ruta, {"nombre": "Nombre corregido"}, format="json").status_code, 200)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.nombre, "Nombre corregido")
        self.assertEqual(self.maquina.marca, "Marca corregida")
        self.assertEqual(self.maquina.modelo, "Modelo API")
        self.assertEqual(self.maquina.movimientos.filter(tipo="EDICION").count(), 2)

    def test_patch_no_cambia_codigo_bodega_estado_ni_horas(self):
        ruta = f"/api/v1/maquinaria/{self.maquina.pk}/"
        for campo, valor in [("codigo", "OTRO"), ("bodega", self.destino.pk), ("estado", "BAJA"), ("horas_iniciales", "0")]:
            self.assertEqual(self.api.patch(ruta, {campo: valor}, format="json").status_code, 400)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")
        self.assertEqual(self.maquina.codigo, "API-001")
        self.assertEqual(self.maquina.tiempo_uso_acumulado, timedelta(hours=10))

    def test_traslado_registra_bodegas_y_no_acepta_destino_actual(self):
        self.assertEqual(self.accion("trasladar", destino=self.destino.pk).status_code, 200)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.bodega_id, self.destino.pk)
        evento = self.maquina.movimientos.get()
        self.assertEqual(evento.origen_id, self.bodega.pk)
        self.assertEqual(evento.destino_id, self.destino.pk)
        self.assertEqual(self.accion("trasladar", destino=self.destino.pk).status_code, 400)

    def test_baja_reactivacion_e_historial_reutilizan_reglas(self):
        self.assertEqual(self.accion("baja").status_code, 200)
        self.assertEqual(self.accion("reactivar").status_code, 200)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "MANTENIMIENTO")
        self.assertEqual(self.maquina.mantenimientos.count(), 1)
        historia = self.api.get(f"/api/v1/maquinaria/{self.maquina.pk}/historial/").json()
        self.assertEqual(historia["count"], 2)
        self.assertEqual({e["tipo"] for e in historia["results"]}, {"BAJA", "REACTIVACION"})

    def test_bodeguero_puede_operar_pero_no_reactivar_aunque_tenga_permiso(self):
        self.api.force_login(self.bodeguero)
        self.assertEqual(self.accion("baja").status_code, 200)
        self.assertEqual(self.accion("reactivar").status_code, 403)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "BAJA")

    def test_operaciones_exigen_motivo_y_estado_correcto(self):
        self.assertEqual(self.accion("baja", motivo="   ").status_code, 400)
        self.maquina.estado = "EN_USO"
        self.maquina.save()
        respuesta = self.accion("baja")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("non_field_errors", respuesta.json())
        self.assertFalse(self.maquina.movimientos.exists())

    def test_no_hay_delete_ni_put_y_get_no_ejecuta_baja(self):
        for recurso, pk in [("maquinaria", self.maquina.pk), ("obras", self.obra.pk), ("bodegas", self.bodega.pk)]:
            ruta = f"/api/v1/{recurso}/{pk}/"
            self.assertEqual(self.api.delete(ruta).status_code, 405)
            self.assertEqual(self.api.put(ruta, {}, format="json").status_code, 405)
        self.assertEqual(self.api.get(f"/api/v1/maquinaria/{self.maquina.pk}/baja/").status_code, 405)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.estado, "DISPONIBLE")

    def test_paginacion_busqueda_y_filtros_validan_parametros(self):
        Maquinaria.objects.bulk_create([Maquinaria(codigo=f"PAG-{i:03}", nombre="Equipo paginado", bodega=self.destino, estado="BAJA") for i in range(23)])
        respuesta = self.api.get(f"/api/v1/maquinaria/?q=Equipo&estado=BAJA&bodega={self.destino.pk}").json()
        self.assertEqual(respuesta["count"], 23)
        self.assertEqual(len(respuesta["results"]), 20)
        self.assertTrue(respuesta["next"])
        self.assertEqual(len(self.api.get("/api/v1/maquinaria/?q=Equipo&page=2").json()["results"]), 3)
        for query in ["estado=INVALIDO", "bodega=no-numero", "page=0", "page=texto", "campo_inexistente=1"]:
            self.assertEqual(self.api.get("/api/v1/maquinaria/?" + query).status_code, 400)

    def test_crear_y_editar_obra_y_bodega_central(self):
        obra = self.api.post("/api/v1/obras/", {"nombre": "Obra nueva", "direccion": "Dirección nueva"}, format="json")
        self.assertEqual(obra.status_code, 201)
        pk = obra.json()["id"]
        self.assertEqual(self.api.patch(f"/api/v1/obras/{pk}/", {"direccion": "Dirección corregida"}, format="json").status_code, 200)
        self.assertEqual(Obra.objects.get(pk=pk).nombre, "Obra nueva")
        bodega = self.api.post("/api/v1/bodegas/", {"nombre": "Central nueva", "direccion": "Calle Central"}, format="json")
        self.assertEqual(bodega.status_code, 201, bodega.data)
        self.assertIsNone(bodega.json()["obra"])
        self.assertIsNone(bodega.json()["obra_nombre"])
        self.assertEqual(self.api.patch(f"/api/v1/bodegas/{bodega.json()['id']}/", {"nombre": "Nombre corregido"}, format="json").status_code, 200)
        self.assertEqual(Bodega.objects.get(pk=bodega.json()["id"]).direccion, "Calle Central")

    def test_crear_bodega_vinculada_y_no_reasignarla_despues(self):
        respuesta = self.api.post("/api/v1/bodegas/", {"nombre": "De obra", "direccion": "Calle acceso", "obra": self.obra.pk}, format="json")
        self.assertEqual(respuesta.status_code, 201)
        pk = respuesta.json()["id"]
        self.assertEqual(respuesta.json()["obra_nombre"], self.obra.nombre)
        self.assertEqual(self.api.patch(f"/api/v1/bodegas/{pk}/", {"obra": None}, format="json").status_code, 400)
        self.assertEqual(Bodega.objects.get(pk=pk).obra_id, self.obra.pk)

    def test_desactivar_reactivar_ubicaciones_con_historial_y_filtro(self):
        ruta = f"/api/v1/obras/{self.obra_vacia.pk}/"
        self.assertEqual(self.api.post(ruta + "desactivar/", {"motivo": "Obra terminada"}, format="json").status_code, 200)
        activos = self.api.get("/api/v1/obras/").json()
        self.assertNotIn(self.obra_vacia.pk, [o["id"] for o in activos["results"]])
        inactivos = self.api.get("/api/v1/obras/?estado=inactivas").json()
        self.assertIn(self.obra_vacia.pk, [o["id"] for o in inactivos["results"]])
        self.assertEqual(self.api.get(ruta).status_code, 200)
        self.assertEqual(self.api.post(ruta + "reactivar/", {"motivo": "Reapertura"}, format="json").status_code, 200)
        self.assertEqual(self.api.get(ruta + "historial/").json()["count"], 2)
        self.assertEqual(self.api.get("/api/v1/obras/?estado=todas").json()["count"], 2)

    def test_bodega_inactiva_no_recibe_equipos_y_su_obra_debe_estar_activa(self):
        ruta = f"/api/v1/bodegas/{self.destino.pk}/"
        self.assertEqual(self.api.post(ruta + "desactivar/", {"motivo": "Cierre"}, format="json").status_code, 200)
        self.assertEqual(self.alta(bodega=self.destino.pk).status_code, 400)
        self.assertEqual(self.accion("trasladar", destino=self.destino.pk).status_code, 400)
        self.obra.activa = False
        self.obra.save()
        self.assertEqual(self.api.post(ruta + "reactivar/", {"motivo": "Intento"}, format="json").status_code, 400)
        self.assertEqual(self.api.post("/api/v1/bodegas/", {"nombre": "Inválida", "direccion": "Calle", "obra": self.obra.pk}, format="json").status_code, 400)

    def test_bodega_con_maquinaria_no_se_desactiva(self):
        respuesta = self.api.post(f"/api/v1/bodegas/{self.bodega.pk}/desactivar/", {"motivo": "Intento"}, format="json")
        self.assertEqual(respuesta.status_code, 400)
        self.bodega.refresh_from_db()
        self.assertTrue(self.bodega.activa)
        self.assertFalse(self.bodega.historial_actividad.exists())

    def test_csrf_real_de_sesion_para_escrituras(self):
        from django.conf import settings
        seguro = APIClient(enforce_csrf_checks=True)
        seguro.force_login(self.admin)
        self.assertEqual(seguro.get("/api/v1/obras/").status_code, 200)
        datos = {"nombre": "Con CSRF", "direccion": "Dirección de prueba"}
        self.assertEqual(seguro.post("/api/v1/obras/", datos, format="json").status_code, 403)
        seguro.get("/maquinaria/nueva/")
        token = seguro.cookies[settings.CSRF_COOKIE_NAME].value
        self.assertEqual(seguro.post("/api/v1/obras/", datos, format="json", HTTP_X_CSRFTOKEN=token).status_code, 201)

    def test_conflictos_no_exponen_sql_y_registro_que_desaparece_devuelve_404(self):
        with patch("maquinaria.api.views.crear_maquinaria", side_effect=IntegrityError("SQL privado")):
            respuesta = self.alta()
        self.assertEqual(respuesta.status_code, 409)
        self.assertNotIn("SQL privado", str(respuesta.json()))
        with patch("maquinaria.api.views.editar_maquinaria", side_effect=Maquinaria.DoesNotExist):
            respuesta = self.api.patch(f"/api/v1/maquinaria/{self.maquina.pk}/", {"nombre": "Cambio"}, format="json")
        self.assertEqual(respuesta.status_code, 404)
        self.assertEqual(self.api.get("/api/v1/maquinaria/999999/").status_code, 404)

    def test_json_malformado_y_cuerpo_no_objeto_devuelven_400(self):
        self.assertEqual(self.api.post("/api/v1/obras/", '{"nombre":', content_type="application/json").status_code, 400)
        self.assertEqual(self.api.post("/api/v1/obras/", ["incorrecto"], format="json").status_code, 400)
        self.assertEqual(self.api.post("/api/v1/obras/", "texto", content_type="text/plain").status_code, 415)

    def test_sufijos_json_y_negociacion_sin_interfaz_generada(self):
        self.assertEqual(self.api.get("/api/v1/maquinaria.json").status_code, 200)
        respuesta = self.api.post("/api/v1/bodegas.json", {"nombre": "Por sufijo", "direccion": "Calle"}, format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(self.api.get("/api/v1/maquinaria/", HTTP_ACCEPT="text/html").status_code, 406)

    def test_sesion_limitada_de_solicitud_no_autentica_api(self):
        pendiente = Usuario.objects.create_user(username="pendiente_api", rut="44444444-4", password="ClavePendiente!4820", is_active=False)
        cliente = APIClient()
        cliente.post("/ingresar/", {"username": pendiente.username, "password": "ClavePendiente!4820"})
        self.assertIn("consulta_solicitud", cliente.session)
        self.assertEqual(cliente.get("/api/v1/maquinaria/").status_code, 403)

    def test_api_no_afecta_templates_bootstrap(self):
        self.alta()
        respuesta = self.api.get("/maquinaria/")
        self.assertContains(respuesta, "Equipo API nuevo")
        self.assertContains(respuesta, "bootstrap.min.css")
        self.assertEqual(self.api.get("/admin/").status_code, 404)


