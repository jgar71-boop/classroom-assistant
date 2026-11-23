"""Trazas opcionales en LangSmith, apagadas salvo que haya clave y se pidan.

La clave ``LANGSMITH_API_KEY`` la lee ``langsmith.Client`` del entorno: este
módulo nunca la toca ni la escribe.
"""

import threading

from langsmith import Client, get_current_run_tree, tracing_context
from langsmith import traceable as langsmith_traceable
from langsmith.utils import tracing_is_enabled

_clients = {}
_clients_lock = threading.Lock()


def traceable(name, run_type):
    """Decora una función para que deje una traza en LangSmith si están encendidas.

    :param name: Nombre de la traza
    :type name: str
    :param run_type: Tipo de traza (``chain``, ``llm`` o ``tool``)
    :type run_type: str
    :return: Decorador
    :rtype: collections.abc.Callable
    """
    return langsmith_traceable(name=name, run_type=run_type)


def _hide_everything(_data):
    """Reemplaza las entradas o salidas de una traza por un objeto vacío.

    :param _data: Entradas o salidas originales (se descartan)
    :type _data: dict
    :return: Objeto vacío
    :rtype: dict
    """
    return {}


def _client_for(settings):
    """Devuelve el cliente de LangSmith de esta configuración, creado una sola vez.

    :param settings: Configuración con ``hide_inputs`` y ``hide_outputs``
    :type settings: app.config.Settings
    :return: Cliente de LangSmith
    :rtype: langsmith.Client
    """
    key = (settings.hide_inputs, settings.hide_outputs)
    with _clients_lock:
        if key not in _clients:
            _clients[key] = Client(
                hide_inputs=_hide_everything if settings.hide_inputs else None,
                hide_outputs=_hide_everything if settings.hide_outputs else None,
            )
        return _clients[key]


def trace_context(settings, request_id, model=None, route=None, client=None):
    """Abre el contexto de trazas de una petición.

    Si las trazas están apagadas no crea cliente ni abre conexiones. Los metadatos
    llevan el nombre del cliente, nunca su clave.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param request_id: Id de la petición, que va en los metadatos
    :type request_id: str
    :param model: Modelo elegido por el enrutador, que va en los metadatos
    :type model: str or None
    :param route: Motivo del enrutador, que va en los metadatos
    :type route: str or None
    :param client: Nombre del cliente autenticado, que va en los metadatos
    :type client: str or None
    :return: Administrador de contexto de ``langsmith.tracing_context``
    :rtype: contextlib.AbstractContextManager
    """
    if not settings.tracing_enabled:
        return tracing_context(enabled=False)
    metadata = {"request_id": request_id}
    if model is not None:
        metadata["model"] = model
    if route is not None:
        metadata["route"] = route
    if client is not None:
        metadata["client"] = client
    return tracing_context(
        enabled=True,
        client=_client_for(settings),
        metadata=metadata,
    )


def annotate_run(**fields):
    """Agrega campos a la metadata de la traza actual.

    No hace nada si las trazas están apagadas o no hay traza en curso.

    :param fields: Campos a agregar, por ejemplo ``cost_usd``
    :type fields: dict
    """
    if not tracing_is_enabled():
        return
    run = get_current_run_tree()
    if run is None:
        return
    run.add_metadata(dict(fields))
