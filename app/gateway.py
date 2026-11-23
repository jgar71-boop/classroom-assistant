"""Modelo real: Cloudflare Workers AI a través de AI Gateway, con ``httpx``.

El cliente HTTP se inyecta para que las pruebas nunca salgan a la red. Los
mensajes de error nunca llevan la URL (que tiene la cuenta) ni el token.
"""

import re

import httpx

from app.completion import Completion

GATEWAY_URL_TEMPLATE = (
    "https://gateway.ai.cloudflare.com/v1/{account_id}/{gateway_id}"
    "/workers-ai/v1/chat/completions"
)
CACHE_TTL_HEADER = "cf-aig-cache-ttl"
CACHE_STATUS_HEADER = "cf-aig-cache-status"
CACHE_HIT = "hit"
FENCE_PATTERN = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)
SYSTEM_PROMPT = (
    "Eres el asistente de un registro de alumnos (nombre, materia, grado y "
    "número de salón). Responde SIEMPRE con un único objeto JSON, sin texto "
    "antes ni después y sin cercas de código.\n"
    "Para usar una herramienta responde "
    '{"tool": "<nombre>", "args": {...}}. Herramientas:\n'
    '- get_student: {"student_id": "STU-0001"} devuelve un alumno por id.\n'
    '- search_by_classroom: {"classroom": 101} devuelve los alumnos de un '
    "salón (entero).\n"
    '- search_by_subject: {"subject": "Historia"} devuelve los alumnos de '
    "una materia.\n"
    "El resultado llega en un mensaje que empieza con "
    '"Resultado de la herramienta: ". Cuando tengas la información responde '
    '{"answer": "<respuesta breve en español>"}. Usa solo datos del registro.'
)


class ModelUnavailable(Exception):
    """El modelo real falló, tardó demasiado o respondió algo inesperado."""


def _strip_fences(text):
    """Quita las cercas de código Markdown que envuelven un JSON.

    :param text: Contenido devuelto por el modelo
    :type text: str
    :return: Contenido sin cercas
    :rtype: str
    """
    match = FENCE_PATTERN.match(text)
    return match.group(1) if match else text.strip()


def _read_completion(data):
    """Extrae el contenido y los tokens del cuerpo de la respuesta.

    :param data: Cuerpo JSON de la respuesta
    :type data: object
    :return: Contenido, tokens de entrada y tokens de salida
    :rtype: tuple[str, int, int]
    :raises ModelUnavailable: Si faltan ``choices`` o ``usage``
    """
    try:
        content = data["choices"][0]["message"]["content"]
        usage = data["usage"]
        input_tokens = int(usage["prompt_tokens"])
        output_tokens = int(usage["completion_tokens"])
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise ModelUnavailable("model response is malformed") from error
    if not isinstance(content, str):
        raise ModelUnavailable("model response is malformed")
    return content, input_tokens, output_tokens


class GatewayModel:
    """Modelo de Workers AI por AI Gateway; cumple ``LanguageModel``.

    :param costs: Configuración de costos (cuenta, token, topes, caché)
    :type costs: app.config.CostSettings
    :param model_name: Nombre del modelo de Workers AI
    :type model_name: str
    :param client: Cliente HTTP inyectado
    :type client: httpx.Client
    """

    def __init__(self, costs, model_name, client):
        self._costs = costs
        self._model_name = model_name
        self._client = client
        self._url = GATEWAY_URL_TEMPLATE.format(
            account_id=costs.cf_account_id, gateway_id=costs.cf_gateway_id
        )

    @property
    def model_name(self):
        """Nombre del modelo.

        :rtype: str
        """
        return self._model_name

    def _headers(self):
        """Arma los encabezados de la llamada.

        :return: Encabezados con el token y, si aplica, el TTL de caché
        :rtype: dict
        """
        headers = {"Authorization": f"Bearer {self._costs.cf_api_token}"}
        if self._costs.cache_ttl_seconds > 0:
            headers[CACHE_TTL_HEADER] = str(self._costs.cache_ttl_seconds)
        return headers

    def _body(self, messages):
        """Arma el cuerpo con el prompt de sistema primero.

        :param messages: Mensajes con ``role`` y ``content``
        :type messages: list[dict]
        :return: Cuerpo de la petición
        :rtype: dict
        """
        conversation = [{"role": "system", "content": SYSTEM_PROMPT}]
        conversation.extend(
            {"role": m["role"], "content": m["content"]} for m in messages
        )
        return {
            "model": self._model_name,
            "messages": conversation,
            "max_tokens": self._costs.model_max_tokens,
            "temperature": self._costs.model_temperature,
        }

    def complete(self, messages):
        """Llama al gateway y devuelve la respuesta del modelo.

        :param messages: Mensajes con ``role`` y ``content``
        :type messages: list[dict]
        :return: Respuesta con texto, tokens y si vino de la caché
        :rtype: app.llm.Completion
        :raises ModelUnavailable: Si la llamada falla, tarda demasiado, responde
            un estado que no es 2xx o un cuerpo inesperado
        """
        try:
            response = self._client.post(
                self._url,
                headers=self._headers(),
                json=self._body(messages),
                timeout=self._costs.model_timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise ModelUnavailable("model call timed out") from error
        except httpx.HTTPError as error:
            raise ModelUnavailable(
                f"model call failed: {type(error).__name__}"
            ) from error
        if not response.is_success:
            raise ModelUnavailable(f"model answered status {response.status_code}")
        try:
            data = response.json()
        except ValueError as error:
            raise ModelUnavailable("model response is not JSON") from error
        content, input_tokens, output_tokens = _read_completion(data)
        status = response.headers.get(CACHE_STATUS_HEADER, "")
        return Completion(
            text=_strip_fences(content),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached=status.strip().lower() == CACHE_HIT,
        )
