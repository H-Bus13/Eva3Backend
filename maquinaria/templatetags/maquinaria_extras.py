from django import template
from django.utils.formats import number_format

register = template.Library()


@register.filter
def horas(duracion):
    if duracion is None:
        return "Sin registro"
    return number_format(duracion.total_seconds() / 3600, decimal_pos=2)


@register.filter
def hms(segundos):
    segundos = max(0, int(segundos or 0))
    return f"{segundos // 3600:02}:{segundos // 60 % 60:02}:{segundos % 60:02}"


@register.filter
def nombre_permiso(permiso):
    from maquinaria.politica_usuarios import etiqueta_permiso
    return etiqueta_permiso(permiso)
