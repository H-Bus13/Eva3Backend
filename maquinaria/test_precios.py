from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from .models import Usuario, Bodega, Maquinaria
from .forms_maquinaria import CrearMaquinariaForm, EditarMaquinariaForm


class PrecioMaquinariaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = Usuario.objects.create_superuser(username="admin_precio", rut="11111111-1", password="Seguro!4820")
        cls.bodega = Bodega.objects.create(nombre="Central", direccion="Direccion central")
        cls.maquina = Maquinaria.objects.create(codigo="PREC-001", nombre="Equipo antiguo", bodega=cls.bodega)

    def setUp(self):
        self.api = APIClient()
        self.api.force_login(self.admin)

    def datos_alta(self):
        return {"codigo": "PREC-002", "nombre": "Equipo nuevo", "marca": "Marca", "modelo": "Modelo",
            "bodega": self.bodega.pk, "precio_diario": "25000.50", "horas_iniciales": "0", "horas_ultima_mantencion": "0"}

    def test_precio_obligatorio_y_minimo_en_ambos_formularios(self):
        for valor in (None, "", "0", "-1"):
            datos = {"nombre": "Equipo", "marca": "", "modelo": ""}
            if valor is not None:
                datos["precio_diario"] = valor
            form = EditarMaquinariaForm(datos, instance=self.maquina)
            self.assertFalse(form.is_valid())
            self.assertIn("precio_diario", form.errors)
        campo = CrearMaquinariaForm().fields["precio_diario"]
        self.assertTrue(campo.required)
        self.assertEqual(str(campo.widget.attrs["min"]), "0.01")

    def test_registro_html_guarda_precio_y_lo_muestra(self):
        self.client.force_login(self.admin)
        respuesta = self.client.post("/maquinaria/nueva/", self.datos_alta())
        self.assertEqual(respuesta.status_code, 302)
        maquina = Maquinaria.objects.get(codigo="PREC-002")
        self.assertEqual(maquina.precio_diario, Decimal("25000.50"))
        self.assertContains(self.client.get(f"/maquinaria/{maquina.pk}/"), "Precio diario:")
        self.assertContains(self.client.get("/maquinaria/"), "CLP")

    def test_editar_antigua_completa_tarifa_y_registra_historial(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(f"/maquinaria/{self.maquina.pk}/"), "Precio pendiente de definir.")
        respuesta = self.client.post(f"/maquinaria/{self.maquina.pk}/editar/", {
            "nombre": "Equipo antiguo", "marca": "", "modelo": "", "precio_diario": "18000.00"})
        self.assertEqual(respuesta.status_code, 302)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.precio_diario, Decimal("18000.00"))
        self.assertIn("precio_diario: None → 18000.00", self.maquina.movimientos.get().motivo)

    def test_api_alta_exige_tarifa_y_devuelve_moneda(self):
        datos = self.datos_alta()
        for precio in (None, "0", "-1", ""):
            datos["precio_diario"] = precio
            respuesta = self.api.post("/api/v1/maquinaria/", datos, format="json")
            self.assertEqual(respuesta.status_code, 400)
            self.assertIn("precio_diario", respuesta.data)
        datos.pop("precio_diario")
        self.assertEqual(self.api.post("/api/v1/maquinaria/", datos, format="json").status_code, 400)
        datos["precio_diario"] = "25000.50"
        respuesta = self.api.post("/api/v1/maquinaria/", datos, format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(respuesta.data["precio_diario"], "25000.50")
        self.assertEqual(respuesta.data["moneda"], "CLP")

    def test_patch_no_borra_tarifa_omitida_y_rechaza_vacia(self):
        ruta = f"/api/v1/maquinaria/{self.maquina.pk}/"
        self.assertEqual(self.api.patch(ruta, {"precio_diario": "12000.00"}, format="json").status_code, 200)
        self.assertEqual(self.api.patch(ruta, {"marca": "Nueva"}, format="json").status_code, 200)
        for precio in (None, "0", "-1", ""):
            self.assertEqual(self.api.patch(ruta, {"precio_diario": precio}, format="json").status_code, 400)
        self.maquina.refresh_from_db()
        self.assertEqual(self.maquina.precio_diario, Decimal("12000.00"))
        self.assertEqual(self.maquina.marca, "Nueva")

