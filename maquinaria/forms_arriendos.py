from decimal import Decimal
from datetime import timedelta

from django import forms
from django.utils import timezone

from .forms import FirmaPerfilForm
from .models import Empresa, Maquinaria, Obra, SolicitudEntrega, Usuario
from .servicios_ubicaciones import bodegas_habilitadas


class PrepararEntregaForm(forms.ModelForm):
    direccion_uso = forms.CharField(label="Dirección de uso de la maquinaria", max_length=255)
    comuna_uso = forms.CharField(label="Comuna", max_length=100)
    indicaciones_acceso = forms.CharField(label="Indicaciones de acceso", required=False, max_length=3000, widget=forms.Textarea)
    tarifa_diaria = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"), label="Tarifa diaria CLP")
    class Meta:
        model = SolicitudEntrega
        fields = ("maquinaria", "empresa", "responsable", "direccion_uso", "comuna_uso", "indicaciones_acceso", "devolucion_prevista", "tarifa_diaria", "observaciones")
        widgets = {"devolucion_prevista": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"), "observaciones": forms.Textarea}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["maquinaria"].queryset = Maquinaria.objects.filter(estado="DISPONIBLE", bodega__in=bodegas_habilitadas()).order_by("codigo")
        self.fields["empresa"].queryset = Empresa.objects.filter(bloqueada=False, bloqueada_por_atraso=False).order_by("razon_social")
        self.fields["responsable"].queryset = Usuario.objects.filter(rol="CONTRATISTA", estado_aprobacion="APROBADO", is_active=True, is_staff=False, is_superuser=False).order_by("username")
        # datetime-local trabaja sin zona horaria y con precisión de minutos.
        # Se usa la hora local del proyecto y el siguiente minuto completo
        # para que el mínimo seleccionable también sea válido en el servidor.
        minimo = timezone.localtime().replace(second=0, microsecond=0) + timedelta(minutes=1)
        self.fields["devolucion_prevista"].widget.attrs["min"] = minimo.strftime("%Y-%m-%dT%H:%M")
        self.fields["devolucion_prevista"].help_text = "Selecciona una fecha y hora posteriores al momento actual."

    def clean(self):
        datos = super().clean()
        usuario, empresa = datos.get("responsable"), datos.get("empresa")
        if usuario and empresa and usuario.empresa_id != empresa.pk:
            self.add_error("responsable", "El responsable no pertenece a la empresa seleccionada.")
        fecha = datos.get("devolucion_prevista")
        if fecha and fecha <= timezone.now():
            self.add_error("devolucion_prevista", "La devolución prevista debe ser futura.")
        return datos


class PrepararDevolucionForm(forms.Form):
    bodega = forms.ModelChoiceField(queryset=bodegas_habilitadas(), label="Bodega que recibe físicamente el equipo")
    observaciones = forms.CharField(label="Estado y observaciones de recepción", max_length=3000, widget=forms.Textarea)
    requiere_revision = forms.BooleanField(label="Presenta daños o requiere revisión", required=False)
    confirmar = forms.BooleanField(label="Confirmo que recibí físicamente esta máquina")


class FirmaArriendoForm(FirmaPerfilForm):
    confirmar = forms.BooleanField(label="Revisé el resumen y confirmo esta operación con mi firma")


class CancelarSolicitudForm(forms.Form):
    motivo = forms.CharField(label="Motivo de cancelación", max_length=1000, widget=forms.Textarea)
    confirmar = forms.BooleanField(label="Confirmo la cancelación de esta solicitud")


class FiltroArriendoForm(forms.Form):
    estado = forms.ChoiceField(required=False, choices=[("", "Todos"), ("abierto", "Abiertos"), ("firma", "Recibidos pendientes de firma"), ("cerrado", "Cerrados")])

