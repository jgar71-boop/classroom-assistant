"""Contexto de cada petición: su id, su cliente y los encabezados que los traen."""

import re
import uuid
from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"
API_KEY_HEADER = "X-API-Key"
SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

current_request_id = ContextVar("current_request_id", default=None)
# Nombre del cliente autenticado; ``None`` en las rutas libres. Nunca la clave.
current_client = ContextVar("current_client", default=None)


def resolve_request_id(header_value):
    """Decide el id de la petición a partir del encabezado del cliente.

    Se conserva el valor del cliente solo si tiene de 1 a 128 letras, dígitos,
    ``.``, ``_`` o ``-``; en cualquier otro caso se genera un UUID.

    :param header_value: Valor del encabezado ``X-Request-ID``, o ``None``
    :type header_value: str or None
    :return: Id seguro para el log y la respuesta
    :rtype: str
    """
    if isinstance(header_value, str) and SAFE_REQUEST_ID.fullmatch(header_value):
        return header_value
    return str(uuid.uuid4())
