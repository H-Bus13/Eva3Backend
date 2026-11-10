"""Destino firmado, independiente del catálogo de obras históricas."""
from django.core.exceptions import ValidationError

CAMPOS_DESTINO = ("direccion_uso", "comuna_uso", "indicaciones_acceso")


def validar_destino(datos):
    resultado = {}
    limites = {"direccion_uso": 255, "comuna_uso": 100, "indicaciones_acceso": 3000}
    errores = {}
    for campo in CAMPOS_DESTINO:
        valor = datos.get(campo, "")
        if not isinstance(valor, str):
            errores[campo] = "Debe ser un texto."
            continue
        valor = valor.strip()
        if campo != "indicaciones_acceso" and not valor:
            errores[campo] = "Este dato es obligatorio."
        elif len(valor) > limites[campo]:
            errores[campo] = f"Máximo {limites[campo]} caracteres."
        resultado[campo] = valor
    if errores:
        raise ValidationError(errores)
    return resultado


def copiar_destino(documento):
    # No se consulta la dirección actual de la obra: se conserva la fotografía
    # migrada o firmada, sin modificarla al preparar/confirmar una entrega.
    datos = {campo: getattr(documento, campo) for campo in CAMPOS_DESTINO}
    if not documento.destino_legacy:
        datos = validar_destino(datos)
    return {**datos, "destino_legacy": documento.destino_legacy}
