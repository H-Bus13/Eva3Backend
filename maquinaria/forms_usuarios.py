from django import forms
from django.contrib.auth.forms import UserCreationForm

from .forms import buscar_por_rut
from .models import Empresa, Usuario
from .politica_usuarios import permisos_efectivos, permisos_otorgables
from .validators import normalizar_rut


ROLES_INTERNOS = [(Usuario.Rol.BODEGUERO, "Bodeguero"), (Usuario.Rol.ADMINISTRADOR, "Administrador")]


class CrearUsuarioInternoForm(UserCreationForm):
    rut = forms.CharField(label="RUT", max_length=15)
    email = forms.EmailField(label="Correo electrónico")
    motivo = forms.CharField(label="Motivo de creación", max_length=1000, widget=forms.Textarea)

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("username", "first_name", "last_name", "email", "rut", "rol")

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rol"].choices = ROLES_INTERNOS
        if actor.is_superuser:
            self.fields["crear_superusuario"] = forms.BooleanField(label="Crear como superusuario", required=False)

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data["rut"])
        if buscar_por_rut(Usuario, rut).exists():
            raise forms.ValidationError("Ya existe una cuenta con este RUT.")
        return rut

    def clean(self):
        datos = super().clean()
        if datos.get("crear_superusuario") and datos.get("rol") != Usuario.Rol.ADMINISTRADOR:
            self.add_error("rol", "Selecciona Administrador para crear un superusuario.")
        return datos


class EditarDatosUsuarioForm(forms.ModelForm):
    motivo = forms.CharField(label="Motivo del cambio", max_length=1000, widget=forms.Textarea)

    class Meta:
        model = Usuario
        fields = ("first_name", "last_name", "email")


class PermisosUsuarioForm(forms.Form):
    rol = forms.ChoiceField(label="Rol interno", choices=ROLES_INTERNOS)
    motivo = forms.CharField(label="Motivo del cambio", max_length=1000, widget=forms.Textarea)

    def __init__(self, *args, actor, destino, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["permisos"] = forms.ModelMultipleChoiceField(
            label="Permisos funcionales", queryset=permisos_otorgables(actor),
            required=False, widget=forms.CheckboxSelectMultiple,
        )
        if actor.is_superuser:
            self.fields["superusuario"] = forms.BooleanField(label="Privilegios de superusuario", required=False)
        if not self.is_bound:
            self.initial.update(rol=Usuario.Rol.ADMINISTRADOR if destino.is_superuser else destino.rol,
                permisos=list(permisos_efectivos(destino).values_list("pk", flat=True)), superusuario=destino.is_superuser)
        self.order_fields(["rol", "superusuario", "permisos", "motivo"])


class EstadoUsuarioForm(forms.Form):
    motivo = forms.CharField(label="Motivo", max_length=1000, widget=forms.Textarea)
    confirmar = forms.BooleanField(label="Confirmo este cambio de estado de la cuenta")


class FiltroUsuariosForm(forms.Form):
    q = forms.CharField(label="Nombre, usuario, RUT o correo", max_length=100, required=False)
    rol = forms.ChoiceField(label="Rol", choices=[("", "Todos los roles"), *Usuario.Rol.choices], required=False)
    estado = forms.ChoiceField(label="Estado", required=False, choices=[("", "Todos"), ("habilitada", "Habilitada para el sistema"), ("suspendida", "Suspendida por administración"), ("pendiente", "Solicitud pendiente"), ("rechazada", "Solicitud rechazada")])
    empresa = forms.ModelChoiceField(label="Empresa", queryset=Empresa.objects.order_by("razon_social"), required=False, empty_label="Todas las empresas")
