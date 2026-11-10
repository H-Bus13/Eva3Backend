from datetime import timedelta
from decimal import Decimal

from django import forms

from .models import Bodega, Maquinaria, Obra
from .servicios_ubicaciones import bodegas_habilitadas


def duracion_horas(valor):
    # Evita pasar por float al convertir decimales a la duración de la BD.
    return timedelta(microseconds=int(valor * Decimal("3600000000")))


class CrearMaquinariaForm(forms.ModelForm):
    precio_diario = forms.DecimalField(
        label="Precio diario de arriendo (CLP)", max_digits=12, decimal_places=2,
        min_value=Decimal("0.01"), required=True, help_text="Debe ser mayor que cero.",
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )
    horas_iniciales = forms.DecimalField(label="Horas totales al registrar", min_value=0, max_digits=10, decimal_places=2, initial=0)
    horas_ultima_mantencion = forms.DecimalField(
        label="Lectura de horas en la última mantención", min_value=0,
        max_digits=10, decimal_places=2, required=False,
        help_text="Si es nueva, ingresa 0. Si se desconoce, deja vacío: quedará en mantenimiento para revisión.",
    )

    class Meta:
        model = Maquinaria
        fields = ("codigo", "nombre", "marca", "modelo", "bodega", "precio_diario")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bodega"].queryset = bodegas_habilitadas()

    def clean_codigo(self):
        codigo = self.cleaned_data["codigo"].strip().upper()
        if Maquinaria.objects.filter(codigo__iexact=codigo).exists():
            raise forms.ValidationError("Ya existe una máquina con este código.")
        return codigo

    def clean(self):
        datos = super().clean()
        total = datos.get("horas_iniciales")
        ultima = datos.get("horas_ultima_mantencion")
        if total is not None and ultima is not None and ultima > total:
            self.add_error("horas_ultima_mantencion", "La lectura no puede superar las horas totales.")
        return datos


class EditarMaquinariaForm(forms.ModelForm):
    precio_diario = forms.DecimalField(
        label="Precio diario de arriendo (CLP)", max_digits=12, decimal_places=2,
        min_value=Decimal("0.01"), required=True, help_text="Debe ser mayor que cero.",
        widget=forms.NumberInput(attrs={"min": "0.01", "step": "0.01"}),
    )
    class Meta:
        model = Maquinaria
        fields = ("nombre", "marca", "modelo", "precio_diario")


class FiltroCatalogoForm(forms.Form):
    q = forms.CharField(label="Código o nombre", max_length=100, required=False)
    estado = forms.ChoiceField(label="Estado", choices=[("", "Todos los estados"), *Maquinaria.Estado.choices], required=False)
    bodega = forms.ModelChoiceField(label="Bodega", queryset=Bodega.objects.select_related("obra").order_by("nombre"), required=False, empty_label="Todas las bodegas")


class OperacionMaquinariaForm(forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=1000, widget=forms.Textarea)
    confirmar = forms.BooleanField(label="Confirmo la operación sobre la máquina indicada")


class TrasladarMaquinariaForm(OperacionMaquinariaForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["destino"].queryset = bodegas_habilitadas()

    destino = forms.ModelChoiceField(label="Bodega de destino", queryset=Bodega.objects.select_related("obra").order_by("nombre"))


class ObraForm(forms.ModelForm):
    class Meta:
        model = Obra
        fields = ("nombre", "direccion")
        labels = {"direccion": "Dirección"}


class BodegaForm(forms.ModelForm):
    class Meta:
        model = Bodega
        fields = ("nombre", "direccion", "obra")
        labels = {"direccion": "Dirección de la bodega", "obra": "Obra asociada (opcional)"}
        help_texts = {"obra": "Deja vacío si la maquinaria está en una bodega de tu empresa, sin relación con una obra."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Una bodega ya registrada no se reasigna a otra obra: eso alteraría
        # el significado de los movimientos históricos. Se crea otra bodega.
        if self.instance.pk:
            self.fields.pop("obra")
        else:
            self.fields["obra"].queryset = Obra.objects.filter(activa=True).order_by("nombre")



class FiltroUbicacionesForm(forms.Form):
    estado = forms.ChoiceField(
        label="Estado de las ubicaciones", required=False, initial="activas",
        choices=[("activas", "Activas"), ("inactivas", "Inactivas"), ("todas", "Todas")],
    )

    def clean_estado(self):
        return self.cleaned_data.get("estado") or "activas"


class ActividadUbicacionForm(forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=1000, widget=forms.Textarea)
    confirmar = forms.BooleanField(label="Confirmo la operación sobre esta ubicación")
