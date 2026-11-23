"""Pruebas del bucle del agente con un modelo guionizado."""

import json

from app.agent import Agent
from app.llm import Completion
from app.repository import StudentRepository

GIVE_UP = "No pude completar la respuesta. Intenta con una pregunta más concreta."
TOOL_RESULT = "Resultado de la herramienta: "


class ScriptedModel:
    """Modelo de prueba que devuelve respuestas fijas y guarda lo que vio.

    Repite la última respuesta cuando se le acaba el guion.

    :param replies: Textos que devuelve, en orden
    :type replies: list[str]
    """

    def __init__(self, replies):
        self.replies = list(replies)
        self.seen = []

    def complete(self, messages):
        """Devuelve la siguiente respuesta con 5 tokens de entrada y 2 de salida."""
        self.seen.append([dict(message) for message in messages])
        text = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        return Completion(text=text, input_tokens=5, output_tokens=2)


def test_agent_gives_up_at_the_step_limit_and_adds_tokens(sample_path):
    asks_forever = json.dumps(
        {"tool": "search_by_classroom", "args": {"classroom": 101}}
    )
    agent = Agent(ScriptedModel([asks_forever]), StudentRepository(sample_path), 2)

    result = agent.run("¿Quiénes están en el salón 101?", [])

    assert result.answer == GIVE_UP
    assert result.steps == 2
    assert (result.input_tokens, result.output_tokens) == (10, 4)


def test_invalid_model_output_is_reported_back_without_raising(sample_path):
    repository = StudentRepository(sample_path)
    model = ScriptedModel(
        [
            "this is not json",
            json.dumps({"tool": "add", "args": {"name": "Intruso"}}),
            json.dumps({"tool": "search_by_classroom", "args": {"classroom": "x"}}),
            json.dumps({"tool": "get_student", "args": {"student_id": "STU-0099"}}),
            json.dumps({"answer": "Listo"}),
        ]
    )

    result = Agent(model, repository, 5).run("Registra a un alumno nuevo", [])

    assert result.answer == "Listo"
    assert result.steps == 5
    for messages in model.seen[1:]:
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"].startswith(TOOL_RESULT)
    assert len(repository.list_all()) == 10
