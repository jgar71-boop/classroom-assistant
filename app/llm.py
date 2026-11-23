"""Interfaz del modelo de lenguaje y modelo simulado determinista."""

import json
import re
from typing import Protocol

from app.completion import Completion
from app.gateway import GatewayModel
from app.repository import normalize

__all__ = ["Completion", "FakeModel", "LanguageModel", "build_model"]

TOOL_RESULT_PREFIX = "Resultado de la herramienta: "
ANSWER_PREFIX = "Según el registro: "
HELP_ANSWER = (
    "Pregúntame por un alumno (STU-0001), un salón (salón 101) o una materia."
)
STUDENT_ID_PATTERN = re.compile(r"STU-\d{4}", re.IGNORECASE)
CLASSROOM_PATTERN = re.compile(r"\bsalon\s*(\d+)")


class LanguageModel(Protocol):
    """Interfaz que cumple cualquier modelo que use el agente."""

    def complete(self, messages):
        """Responde a una conversación.

        :param messages: Mensajes con ``role`` y ``content``
        :type messages: list[dict]
        :return: Respuesta del modelo
        :rtype: Completion
        """


def count_words(text):
    """Cuenta las palabras de un texto (aproximación de tokens).

    :param text: Texto a contar
    :type text: str
    :return: Número de palabras separadas por espacios
    :rtype: int
    """
    return len(str(text).split())


class FakeModel:
    """Modelo simulado: decide con reglas sobre el último mensaje.

    Las materias se leen del repositorio en cada llamada.

    :param repository: Repositorio de alumnos (solo lectura)
    :type repository: app.repository.StudentRepository
    """

    def __init__(self, repository):
        self._repository = repository

    def complete(self, messages):
        """Responde un único objeto JSON según las cinco reglas.

        :param messages: Mensajes con ``role`` y ``content``
        :type messages: list[dict]
        :return: Respuesta con el texto JSON y el conteo de tokens
        :rtype: Completion
        """
        last = str(messages[-1].get("content", "")) if messages else ""
        reply = self._decide(last)
        text = json.dumps(reply, ensure_ascii=False)
        input_tokens = sum(count_words(m.get("content", "")) for m in messages)
        return Completion(
            text=text, input_tokens=input_tokens, output_tokens=count_words(text)
        )

    def _decide(self, last):
        """Aplica las reglas en orden sobre el último mensaje.

        :param last: Contenido del último mensaje
        :type last: str
        :return: Objeto con ``answer`` o con ``tool`` y ``args``
        :rtype: dict
        """
        if last.startswith(TOOL_RESULT_PREFIX):
            result = last[len(TOOL_RESULT_PREFIX):]
            return {"answer": f"{ANSWER_PREFIX}{result}"}
        id_match = STUDENT_ID_PATTERN.search(last)
        if id_match:
            student_id = id_match.group(0).upper()
            return {"tool": "get_student", "args": {"student_id": student_id}}
        normalized = normalize(last)
        room_match = CLASSROOM_PATTERN.search(normalized)
        if room_match:
            classroom = int(room_match.group(1))
            return {"tool": "search_by_classroom", "args": {"classroom": classroom}}
        subject = self._find_subject(normalized)
        if subject is not None:
            return {"tool": "search_by_subject", "args": {"subject": subject}}
        return {"answer": HELP_ANSWER}

    def _find_subject(self, normalized):
        """Busca en el texto una materia que exista en los datos.

        :param normalized: Texto ya normalizado
        :type normalized: str
        :return: La materia encontrada, o ``None``
        :rtype: str or None
        """
        for subject in self._repository.subjects():
            key = normalize(subject).strip()
            if not key:
                continue
            pattern = r"(?<!\w)" + re.escape(key) + r"(?!\w)"
            if re.search(pattern, normalized):
                return subject
        return None


def build_model(settings, repository, model_name=None, client=None):
    """Construye el modelo indicado en la configuración.

    Con ``fake`` los dos nombres de modelo responden igual; el nombre solo
    decide el precio. Con ``gateway`` se usa el cliente HTTP inyectado.

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param repository: Repositorio de alumnos
    :type repository: app.repository.StudentRepository
    :param model_name: Nombre del modelo; por omisión ``MODEL_SMALL``
    :type model_name: str or None
    :param client: Cliente HTTP para ``gateway``
    :type client: httpx.Client or None
    :return: Modelo listo para usar
    :rtype: LanguageModel
    :raises ValueError: Si el proveedor no está soportado o falta el cliente
    """
    if settings.model_provider == "fake":
        return FakeModel(repository)
    if settings.model_provider == "gateway":
        if client is None:
            raise ValueError("MODEL_PROVIDER=gateway needs an HTTP client")
        name = model_name or settings.costs.model_small
        return GatewayModel(settings.costs, name, client)
    raise ValueError(f"Unsupported MODEL_PROVIDER: {settings.model_provider}")
