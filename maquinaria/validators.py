import re

from django.core.exceptions import ValidationError


def normalizar_rut(valor):
    # Se conserva un formato único, sin puntos y con guion. El módulo 11
    # compara el dígito calculado con el que escribió la persona.
    limpio = valor.strip().upper().replace(".", "")
    if not re.fullmatch(r"[1-9][0-9]{6,7}-?[0-9K]", limpio):
        raise ValidationError("Ingresa un RUT válido, por ejemplo 12.345.678-5.")
    cuerpo, digito = limpio.replace("-", "")[:-1], limpio[-1]
    suma = sum(int(numero) * (2 + posicion % 6)
               for posicion, numero in enumerate(reversed(cuerpo)))
    resultado = 11 - suma % 11
    esperado = "0" if resultado == 11 else "K" if resultado == 10 else str(resultado)
    if digito != esperado:
        raise ValidationError("El dígito verificador del RUT es incorrecto.")
    return f"{cuerpo}-{digito}"
