"""Agente con bucle con tope y tres herramientas de solo lectura."""

import json
from dataclasses import dataclass, field
from typing import Optional

from app.llm import TOOL_RESULT_PREFIX
from app.tracing import annotate_run, traceable

GIVE_UP_ANSWER = (
    "No pude completar la respuesta. Intenta con una pregunta más concreta."
)
STOPPED_ANSWER = "answer"
STOPPED_MAX_STEPS = "max_steps"
EXPECTED_ARGUMENTS = {
    "get_student": "student_id",
    "search_by_classroom": "classroom",
    "search_by_subject": "subject",
}


@dataclass
class AgentResult:  # pylint: disable=too-many-instance-attributes
    """Resultado de una pregunta al agente.

    :param answer: Respuesta final en español
    :type answer: str
    :param steps: Vueltas del bucle que se usaron
    :type steps: int
    :param tools_used: Nombres de las herramientas ejecutadas, en orden
    :type tools_used: list[str]
    :param input_tokens: Suma de tokens de entrada
    :type input_tokens: int
    :param output_tokens: Suma de tokens de salida
    :type output_tokens: int
    :param stopped: Por qué terminó: ``answer`` o ``max_steps``
    :type stopped: str
    :param model: Nombre del modelo que respondió, si se conoce
    :type model: str or None
    :param cached_calls: Llamadas que vinieron de la caché (no cuestan)
    :type cached_calls: int
    :param cost_usd: Costo de la corrida en USD
    :type cost_usd: float
    """

    answer: str
    steps: int = 0
    tools_used: list = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    stopped: str = STOPPED_MAX_STEPS
    model: Optional[str] = None
    cached_calls: int = 0
    cost_usd: float = 0.0


class ToolError(Exception):
    """Error al ejecutar una herramienta; se devuelve al modelo como resultado."""


class Agent:
    """Agente que pregunta al modelo y ejecuta herramientas de solo lectura.

    :param model: Modelo con el método ``complete(messages)``
    :type model: app.llm.LanguageModel
    :param repository: Repositorio de alumnos (solo se usan lecturas)
    :type repository: app.repository.StudentRepository
    :param max_steps: Tope de vueltas del bucle
    :type max_steps: int
    :param on_tool_call: Función opcional ``(name, args)`` que se llama antes de
        cada herramienta conocida, solo con su argumento esperado
    :type on_tool_call: collections.abc.Callable or None
    :param model_name: Nombre del modelo, que decide el precio
    :type model_name: str or None
    :param prices: Tabla de precios; sin ella el costo es 0
    :type prices: app.pricing.PriceTable or None
    :param history_window: Mensajes de historial que se mandan (``None``: todos)
    :type history_window: int or None
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        model,
        repository,
        max_steps,
        on_tool_call=None,
        *,
        model_name=None,
        prices=None,
        history_window=None,
    ):
        self._model = model
        self._max_steps = max_steps
        self._on_tool_call = on_tool_call
        self._model_name = model_name
        self._prices = prices
        self._history_window = history_window
        tools = {
            "get_student": self._make_get_student(repository),
            "search_by_classroom": self._make_search_by_classroom(repository),
            "search_by_subject": self._make_search_by_subject(repository),
        }
        self._tools = {
            name: traceable(name, "tool")(tool) for name, tool in tools.items()
        }

    @property
    def tool_names(self):
        """Nombres de las herramientas disponibles.

        :return: Nombres de las herramientas
        :rtype: list[str]
        """
        return list(self._tools)

    @staticmethod
    def _make_get_student(repository):
        """Crea la herramienta ``get_student``.

        :param repository: Repositorio de alumnos
        :type repository: app.repository.StudentRepository
        :return: Función que recibe ``student_id``
        :rtype: collections.abc.Callable
        """

        def get_student(student_id):
            if not isinstance(student_id, str) or not student_id.strip():
                raise ToolError("student_id must be a non-empty string")
            student = repository.get(student_id)
            if student is None:
                return {"error": f"No existe el alumno {student_id}"}
            return student

        return get_student

    @staticmethod
    def _make_search_by_classroom(repository):
        """Crea la herramienta ``search_by_classroom``.

        :param repository: Repositorio de alumnos
        :type repository: app.repository.StudentRepository
        :return: Función que recibe ``classroom``
        :rtype: collections.abc.Callable
        """

        def search_by_classroom(classroom):
            if isinstance(classroom, bool) or not isinstance(classroom, int):
                raise ToolError("classroom must be an integer")
            return repository.find_by_classroom(classroom)

        return search_by_classroom

    @staticmethod
    def _make_search_by_subject(repository):
        """Crea la herramienta ``search_by_subject``.

        :param repository: Repositorio de alumnos
        :type repository: app.repository.StudentRepository
        :return: Función que recibe ``subject``
        :rtype: collections.abc.Callable
        """

        def search_by_subject(subject):
            if not isinstance(subject, str) or not subject.strip():
                raise ToolError("subject must be a non-empty string")
            return repository.find_by_subject(subject)

        return search_by_subject

    def _execute(self, name, args):
        """Ejecuta una herramienta y devuelve su resultado o un error.

        :param name: Nombre de la herramienta
        :type name: object
        :param args: Argumentos de la herramienta
        :type args: object
        :return: Resultado serializable a JSON
        :rtype: object
        """
        tool = self._tools.get(name) if isinstance(name, str) else None
        if tool is None:
            return {"error": f"Unknown tool: {name}"}
        self._audit(name, args)
        if not isinstance(args, dict):
            return {"error": "args must be an object"}
        try:
            return tool(**args)
        except (ToolError, TypeError) as error:
            return {"error": f"Invalid arguments for {name}: {error}"}

    def _audit(self, name, args):
        """Avisa de una herramienta conocida, solo con su argumento esperado.

        :param name: Nombre de una herramienta conocida
        :type name: str
        :param args: Argumentos que pidió el modelo
        :type args: object
        """
        if self._on_tool_call is None:
            return
        expected = EXPECTED_ARGUMENTS[name]
        filtered = {}
        if isinstance(args, dict) and expected in args:
            filtered[expected] = args[expected]
        self._on_tool_call(name, filtered)

    @traceable("model", "llm")
    def _complete(self, messages):
        """Llama al modelo; aparte para que quede como traza ``llm``.

        :param messages: Mensajes con ``role`` y ``content``
        :type messages: list[dict]
        :return: Respuesta del modelo
        :rtype: app.llm.Completion
        """
        return self._model.complete(messages)

    @staticmethod
    def _parse(text):
        """Interpreta la respuesta del modelo como un único objeto JSON.

        :param text: Texto devuelto por el modelo
        :type text: str
        :return: Objeto interpretado, o ``None`` si no es un objeto JSON
        :rtype: dict or None
        """
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _window(self, history):
        """Recorta el historial a los últimos ``history_window`` mensajes.

        :param history: Conversación previa
        :type history: list[dict]
        :return: Mensajes que se mandan al modelo
        :rtype: list[dict]
        """
        if self._history_window is None:
            return list(history)
        if self._history_window <= 0:
            # history[-0:] devolvería todo: el 0 se trata aparte.
            return []
        return list(history[-self._history_window:])

    def _account(self, result, completion):
        """Suma tokens y costo de una llamada al resultado.

        :param result: Resultado en curso
        :type result: AgentResult
        :param completion: Respuesta del modelo
        :type completion: app.llm.Completion
        """
        result.steps += 1
        result.input_tokens += completion.input_tokens
        result.output_tokens += completion.output_tokens
        if getattr(completion, "cached", False):
            result.cached_calls += 1
        elif self._prices is not None and self._model_name is not None:
            result.cost_usd += self._prices.cost(
                self._model_name, completion.input_tokens, completion.output_tokens
            )

    @traceable("agent_run", "chain")
    def run(self, question, history=None):
        """Responde una pregunta con el bucle con tope.

        :param question: Pregunta de la persona
        :type question: str
        :param history: Conversación previa con ``role`` y ``content``
        :type history: list[dict] or None
        :return: Respuesta, vueltas, herramientas, tokens, modelo y costo
        :rtype: AgentResult
        """
        result = self._loop(question, history or [])
        annotate_run(cost_usd=result.cost_usd)
        return result

    def _loop(self, question, history):
        """Bucle con tope: pregunta al modelo y ejecuta herramientas.

        :param question: Pregunta de la persona
        :type question: str
        :param history: Conversación previa con ``role`` y ``content``
        :type history: list[dict]
        :return: Resultado de la corrida
        :rtype: AgentResult
        """
        messages = [
            {"role": item["role"], "content": item["content"]}
            for item in self._window(history)
        ]
        messages.append({"role": "user", "content": question})
        result = AgentResult(answer=GIVE_UP_ANSWER, model=self._model_name)
        for _ in range(self._max_steps):
            completion = self._complete(messages)
            self._account(result, completion)
            reply = self._parse(completion.text)
            if reply is not None and isinstance(reply.get("answer"), str):
                result.answer = reply["answer"]
                result.stopped = STOPPED_ANSWER
                return result
            if reply is None or "tool" not in reply:
                outcome = {"error": "Invalid model output: expected one JSON object"}
            else:
                outcome = self._execute(reply.get("tool"), reply.get("args", {}))
                if reply.get("tool") in self._tools:
                    result.tools_used.append(reply["tool"])
            messages.append({"role": "assistant", "content": str(completion.text)})
            content = TOOL_RESULT_PREFIX + json.dumps(outcome, ensure_ascii=False)
            messages.append({"role": "user", "content": content})
        result.answer = GIVE_UP_ANSWER
        result.stopped = STOPPED_MAX_STEPS
        return result
