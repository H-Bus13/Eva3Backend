from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.db.models.functions import Replace, Upper
from django.db.models import Value

from .models import Empresa, Usuario, TerminosCondiciones
from .validators import normalizar_rut


def buscar_por_rut(modelo, rut):
    # También reconoce registros antiguos que contienen puntos o minúsculas.
    return modelo.objects.annotate(
        rut_comparable=Upper(Replace(Replace("rut", Value("."), Value("")), Value("-"), Value("")))
    ).filter(rut_comparable=rut.replace("-", ""))


class RegistroContratistaForm(UserCreationForm):
    rut_empresa = forms.CharField(label="RUT de la empresa", max_length=15)
    razon_social = forms.CharField(label="Razón social", max_length=150)
    rut = forms.CharField(label="Tu RUT", max_length=15)
    email = forms.EmailField(label="Correo electrónico", max_length=254,
        help_text="Ejemplo: nombre@empresa.cl",
        error_messages={"required": "Ingresa tu correo electrónico.",
                        "invalid": "Ingresa un correo válido, por ejemplo nombre@empresa.cl."},
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "nombre@empresa.cl"}))

    class Meta(UserCreationForm.Meta):
        model = Usuario
        fields = ("username", "first_name", "last_name", "email", "rut")
        labels = {"first_name": "Nombre", "last_name": "Apellido"}

    def clean_rut(self):
        rut = normalizar_rut(self.cleaned_data["rut"])
        if buscar_por_rut(Usuario, rut).exists():
            raise forms.ValidationError("Ya existe una cuenta con ese RUT.")
        return rut

    def clean_rut_empresa(self):
        return normalizar_rut(self.cleaned_data["rut_empresa"])

    def save(self, commit=True):
        if not commit:
            raise ValueError("El registro debe guardarse junto con su empresa.")
        # La vista envuelve esta operación en una transacción: si falla crear
        # el usuario, tampoco queda una empresa creada a medias.
        empresa = buscar_por_rut(Empresa, self.cleaned_data["rut_empresa"]).first()
        if empresa is None:
            empresa, _ = Empresa.objects.get_or_create(
                rut=self.cleaned_data["rut_empresa"],
                defaults={"razon_social": self.cleaned_data["razon_social"]},
            )
        usuario = super().save(commit=False)
        usuario.empresa = empresa
        # Estos campos se fijan en el servidor. Un POST manipulado no puede
        # convertir el registro público en una cuenta administrativa.
        usuario.rol = Usuario.Rol.CONTRATISTA
        usuario.estado_aprobacion = Usuario.EstadoAprobacion.PENDIENTE
        usuario.is_active = False
        usuario.is_staff = False
        usuario.is_superuser = False
        usuario.save()
        return usuario


class RevisionCuentaForm(forms.Form):
    accion = forms.ChoiceField(choices=[("aprobar", "Aprobar"), ("rechazar", "Rechazar")])
    motivo = forms.CharField(widget=forms.Textarea, max_length=1000, required=False)

    def clean(self):
        datos = super().clean()
        if datos.get("accion") == "rechazar" and not datos.get("motivo"):
            self.add_error("motivo", "Indica el motivo del rechazo.")
        return datos


class PublicarTerminosForm(forms.ModelForm):
    class Meta:
        model = TerminosCondiciones
        fields = ("version", "contenido")
        labels = {"version": "Identificador de versión", "contenido": "Texto completo de las condiciones"}
        widgets = {"contenido": forms.Textarea(attrs={"rows": 16})}


class FirmaPerfilForm(forms.Form):
    firma = forms.FileField(label="Firma")

    def clean_firma(self):
        import warnings
        from io import BytesIO
        from django.core.files.base import ContentFile
        from PIL import Image, ImageOps, UnidentifiedImageError

        archivo = self.cleaned_data["firma"]
        if archivo.size > 500 * 1024:
            raise forms.ValidationError("La firma no puede superar los 500 KB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(archivo) as imagen:
                    if imagen.format != "PNG":
                        raise forms.ValidationError("La firma debe enviarse como una imagen PNG.")
                    ancho, alto = imagen.size
                    # Se limita el área antes de descomprimir toda la imagen.
                    if not (200 <= ancho <= 1200 and 80 <= alto <= 600):
                        raise forms.ValidationError("Las dimensiones de la firma no son válidas.")
                    if getattr(imagen, "n_frames", 1) != 1:
                        raise forms.ValidationError("La firma no puede ser una imagen animada.")
                    imagen.load()
                    imagen = imagen.convert("RGBA")
        except (UnidentifiedImageError, OSError, ValueError,
                Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise forms.ValidationError("No se pudo leer la imagen de la firma.")

        # La transparencia se coloca sobre blanco para no confundir un
        # recuadro transparente con un trazo. No verifica la identidad.
        fondo = Image.new("RGBA", imagen.size, "white")
        fondo.alpha_composite(imagen)
        resultado = fondo.convert("RGB")
        if sum(ImageOps.grayscale(resultado).histogram()[:220]) < 100:
            raise forms.ValidationError("Dibuja tu firma antes de guardarla.")

        # Se vuelve a generar el archivo, descartando nombre y metadatos.
        salida = BytesIO()
        resultado.save(salida, format="PNG")
        return ContentFile(salida.getvalue(), name="firma.png")



class AccesoConSolicitudForm(AuthenticationForm):
    acceso_limitado = False

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")
        if username and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                # El backend normal sigue rechazando cuentas pendientes o
                # rechazadas. Solo este formulario permite consultar su estado.
                usuario = Usuario.objects.filter(username=username).first()
                if (usuario is not None
                        and usuario.rol == Usuario.Rol.CONTRATISTA
                        and not usuario.is_staff and not usuario.is_superuser and not usuario.suspendida
                        and usuario.estado_aprobacion in (
                            Usuario.EstadoAprobacion.PENDIENTE,
                            Usuario.EstadoAprobacion.RECHAZADO,
                        ) and usuario.check_password(password)):
                    self.user_cache = usuario
                    self.acceso_limitado = True
                else:
                    # Mensaje genérico: no revela si existe la cuenta.
                    raise self.get_invalid_login_error()
            else:
                self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class ReenviarSolicitudForm(forms.Form):
    rut_empresa = forms.CharField(label="RUT de la empresa", max_length=15)
    razon_social = forms.CharField(label="Razón social", max_length=150)
    comentario = forms.CharField(
        label="Explica qué corregiste o cómo acreditas tu vínculo con la empresa",
        max_length=1000, widget=forms.Textarea,
    )

    def clean_rut_empresa(self):
        return normalizar_rut(self.cleaned_data["rut_empresa"])

    def obtener_empresa(self):
        # Solo se llama dentro de la transacción del reenvío. No permite
        # cambiar el nombre ni levantar el bloqueo de una empresa existente.
        empresa = buscar_por_rut(Empresa, self.cleaned_data["rut_empresa"]).first()
        if empresa is None:
            empresa, _ = Empresa.objects.get_or_create(
                rut=self.cleaned_data["rut_empresa"],
                defaults={"razon_social": self.cleaned_data["razon_social"]},
            )
        return empresa


