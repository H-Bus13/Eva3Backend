from datetime import timedelta
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class MigracionDestinoTests(TransactionTestCase):
    desde = ("maquinaria", "0014_solicitudentrega_solicitud_arriendo")
    hasta = ("maquinaria", "0015_arriendo_comuna_uso_arriendo_destino_legacy_and_more")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.desde])
        self.anteriores = executor.loader.project_state([self.desde]).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.hasta])
        super().tearDown()

    def test_copia_direccion_sin_inventar_comuna_ni_cambiar_firmas(self):
        apps = self.anteriores
        ahora = timezone.now()
        empresa = apps.get_model("maquinaria", "Empresa").objects.create(rut="77777777-7", razon_social="Empresa anterior")
        usuario = apps.get_model("maquinaria", "Usuario").objects.create(username="usuario_anterior", rut="11111111-1", empresa=empresa)
        obra = apps.get_model("maquinaria", "Obra").objects.create(nombre="Obra anterior", direccion="Dirección histórica 123")
        bodega = apps.get_model("maquinaria", "Bodega").objects.create(nombre="Central", direccion="Dirección central")
        maquina = apps.get_model("maquinaria", "Maquinaria").objects.create(codigo="MIG-DIR", nombre="Equipo anterior", bodega=bodega)
        terminos = apps.get_model("maquinaria", "TerminosCondiciones").objects.create(version="MIG-DIR", contenido="Condiciones originales")
        aceptacion = apps.get_model("maquinaria", "AceptacionTerminos").objects.create(usuario=usuario, terminos=terminos,
            aceptado_en=ahora, firmado_en=ahora, firma="perfil-original.png")
        arr = apps.get_model("maquinaria", "Arriendo").objects.create(maquinaria=maquina, empresa=empresa,
            responsable=usuario, obra_destino=obra, aceptacion=aceptacion,
            devolucion_prevista=ahora + timedelta(days=3), tarifa_diaria=25000, firma_entrega="entrega-original.png")
        ent = apps.get_model("maquinaria", "SolicitudEntrega").objects.create(maquinaria=maquina, empresa=empresa,
            responsable=usuario, obra_destino=obra, terminos=terminos, preparada_por=usuario,
            devolucion_prevista=ahora + timedelta(days=3), tarifa_diaria=25000)
        sol = apps.get_model("maquinaria", "SolicitudArriendo").objects.create(maquinaria=maquina, empresa=empresa,
            solicitante=usuario, obra_destino=obra, terminos=terminos, devolucion_prevista=ahora + timedelta(days=3),
            precio_diario_acordado=25000, aceptado_en=ahora, firmado_en=ahora, firma_solicitud="solicitud-original.png")
        executor = MigrationExecutor(connection)
        executor.migrate([self.hasta])
        actuales = executor.loader.project_state([self.hasta]).apps
        for nombre, pk in (("Arriendo", arr.pk), ("SolicitudEntrega", ent.pk), ("SolicitudArriendo", sol.pk)):
            documento = actuales.get_model("maquinaria", nombre).objects.get(pk=pk)
            self.assertEqual(documento.direccion_uso, "Dirección histórica 123")
            self.assertEqual(documento.comuna_uso, "")
            self.assertTrue(documento.destino_legacy)
            self.assertEqual(documento.obra_destino_id, obra.pk)
        self.assertEqual(actuales.get_model("maquinaria", "Arriendo").objects.get(pk=arr.pk).firma_entrega.name, "entrega-original.png")
        self.assertEqual(actuales.get_model("maquinaria", "SolicitudArriendo").objects.get(pk=sol.pk).firma_solicitud.name, "solicitud-original.png")
        actuales.get_model("maquinaria", "Obra").objects.filter(pk=obra.pk).update(direccion="Dirección modificada")
        self.assertEqual(actuales.get_model("maquinaria", "Arriendo").objects.get(pk=arr.pk).direccion_uso, "Dirección histórica 123")
