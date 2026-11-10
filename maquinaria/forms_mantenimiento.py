from django import forms
from django.db.models import Q

from .models import Maquinaria, Mantenimiento


class ProgramarMantenimientoForm(forms.ModelForm):
    class Meta:
        model = Mantenimiento
        fields = ("maquinaria", "fecha_programada", "descripcion")
        labels = {"descripcion": "Motivo y trabajo previsto"}
        widgets = {
            "fecha_programada": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "descripcion": forms.Textarea,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["maquinaria"].queryset = (Maquinaria.objects.exclude(estado=Maquinaria.Estado.BAJA)
            .filter(bodega__activa=True).filter(Q(bodega__obra__isnull=True) | Q(bodega__obra__activa=True)).order_by("codigo"))


class IniciarMantenimientoForm(forms.Form):
    confirmar = forms.BooleanField(label="Confirmo el inicio del trabajo en esta máquina")


class FinalizarMantenimientoForm(forms.Form):
    resultado = forms.CharField(label="Trabajo realizado y resultado", max_length=3000, widget=forms.Textarea)
    apta_para_servicio = forms.TypedChoiceField(
        label="¿La máquina quedó apta para servicio?",
        choices=[("si", "Sí, revisión satisfactoria"), ("no", "No, necesita otra intervención")],
        coerce=lambda valor: valor == "si", widget=forms.RadioSelect,
    )
    confirmar = forms.BooleanField(label="Confirmo el resultado de la revisión")


class FiltroMantenimientoForm(forms.Form):
    estado = forms.ChoiceField(required=False, choices=[("", "Todos los estados"), ("pendiente", "Pendientes"), ("curso", "En curso"), ("finalizada", "Finalizadas")])
    maquinaria = forms.ModelChoiceField(queryset=Maquinaria.objects.order_by("codigo"), required=False, empty_label="Todos los equipos")
