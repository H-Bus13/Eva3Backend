from django.http import Http404
from .models import Arriendo, SolicitudDevolucion, SolicitudEntrega


def consulta_arriendos(usuario):
    consulta = Arriendo.objects.select_related("maquinaria", "empresa", "responsable", "obra_destino", "bodega_origen", "bodega_recepcion", "aceptacion__terminos")
    return consulta if usuario.has_perm("maquinaria.gestionar_arriendos") else consulta.filter(responsable=usuario)


def consulta_solicitudes(usuario, tipo):
    if tipo == "entrega":
        consulta = SolicitudEntrega.objects.select_related("maquinaria", "empresa", "responsable", "obra_destino", "terminos", "preparada_por")
        return consulta if usuario.has_perm("maquinaria.gestionar_arriendos") else consulta.filter(responsable=usuario)
    if tipo == "devolucion":
        consulta = SolicitudDevolucion.objects.select_related("arriendo__maquinaria", "arriendo__empresa", "arriendo__responsable", "arriendo__obra_destino", "bodega", "preparada_por")
        return consulta if usuario.has_perm("maquinaria.gestionar_arriendos") else consulta.filter(arriendo__responsable=usuario)
    raise Http404



