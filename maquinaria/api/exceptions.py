from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from rest_framework import exceptions
from rest_framework.views import exception_handler


class Conflicto(exceptions.APIException):
    status_code = 409
    default_detail = "La operación entra en conflicto con otro registro. Actualiza los datos e inténtalo de nuevo."
    default_code = "conflicto"


def errores_api(error, context):
    # Se traduce después de salir de la transacción del servicio. Nunca se
    # entrega al cliente el texto SQL ni detalles internos de IntegrityError.
    if isinstance(error, DjangoValidationError):
        error = exceptions.ValidationError(error.message_dict if hasattr(error, "message_dict") else {"non_field_errors": error.messages})
    elif isinstance(error, IntegrityError):
        error = Conflicto()
    elif isinstance(error, ObjectDoesNotExist):
        error = exceptions.NotFound("El registro ya no existe.")
    return exception_handler(error, context)
