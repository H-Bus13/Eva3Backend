from decimal import Decimal
from datetime import timedelta
from django import forms
from django.utils import timezone
from .forms import FirmaPerfilForm
from .models import Obra


class SolicitarArriendoForm(FirmaPerfilForm):
    direccion_uso = forms.CharField(label="Dirección de uso de la maquinaria", max_length=255)
    comuna_uso = forms.CharField(label="Comuna", max_length=100)
    indicaciones_acceso = forms.CharField(label="Indicaciones de acceso", required=False, max_length=3000, widget=forms.Textarea)
    devolucion_prevista = forms.DateTimeField(label="Fecha y hora de devolución",
        widget=forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"))
    observaciones = forms.CharField(required=False, max_length=3000, widget=forms.Textarea)
    version_id = forms.IntegerField(widget=forms.HiddenInput)
    precio_visto = forms.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"), widget=forms.HiddenInput)
    acepto = forms.BooleanField(label="Acepto las condiciones y el precio diario de esta solicitud")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        minimo = timezone.localtime().replace(second=0, microsecond=0) + timedelta(minutes=1)
        self.fields["devolucion_prevista"].widget.attrs["min"] = minimo.strftime("%Y-%m-%dT%H:%M")

    def clean_devolucion_prevista(self):
        fecha = self.cleaned_data["devolucion_prevista"]
        if fecha <= timezone.now():
            raise forms.ValidationError("La devolución debe ser futura.")
        return fecha


class MotivoPeticionForm(forms.Form):
    motivo = forms.CharField(max_length=1000, widget=forms.Textarea, label="Motivo")
    confirmar = forms.BooleanField(label="Confirmo esta operación")
