from django import forms


class BloqueoManualEmpresaForm(forms.Form):
    motivo = forms.CharField(label="Motivo (visible para los integrantes de la empresa)", max_length=2000, widget=forms.Textarea)
    confirmar = forms.BooleanField(label="Confirmo este cambio del bloqueo manual")
