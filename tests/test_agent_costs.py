"""Pruebas del costo por respuesta en el agente y en las métricas."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from conftest import MODEL_LARGE, expected_cost

from app.agent import Agent
from app.llm import Completion
from app.metrics import Metrics
from app.pricing import PriceTable
from app.repository import StudentRepository


class ScriptedModel:
    """Modelo que devuelve las ``Completion`` dadas y anota lo que recibe."""

    def __init__(self, *completions):
        self._completions = list(completions)
        self.seen = []

    def complete(self, messages):
        """Devuelve la siguiente respuesta; repite la última al agotarse."""
        self.seen.append(len(messages))
        if len(self._completions) > 1:
            return self._completions.pop(0)
        return self._completions[0]


def answer(text="listo", **tokens):
    """Respuesta final del modelo con los tokens indicados."""
    return Completion(text=json.dumps({"answer": text}), **tokens)


def test_agent_adds_the_cost_of_each_call_and_cached_calls_are_free(
    sample_path, prices_path
):
    tool_call = Completion(
        text=json.dumps({"tool": "get_student", "args": {"student_id": "STU-0003"}}),
        input_tokens=1000,
        output_tokens=100,
    )
    cached_answer = answer(input_tokens=2000, output_tokens=50, cached=True)
    agent = Agent(
        ScriptedModel(tool_call, cached_answer),
        StudentRepository(sample_path),
        3,
        model_name=MODEL_LARGE,
        prices=PriceTable.load(prices_path),
    )

    result = agent.run("¿Quién es STU-0003?", [])

    assert result.answer == "listo"
    assert result.model == MODEL_LARGE
    assert result.cached_calls == 1
    assert (result.input_tokens, result.output_tokens) == (3000, 150)
    assert result.cost_usd == pytest.approx(expected_cost(MODEL_LARGE, 1000, 100))


def test_history_window_none_or_larger_than_history_sends_everything(
    sample_path, prices_path
):
    history = [{"role": "user", "content": f"mensaje {n}"} for n in range(4)]
    for window in (None, 10, 3):
        model = ScriptedModel(answer(input_tokens=1, output_tokens=1))
        agent = Agent(
            model,
            StudentRepository(sample_path),
            3,
            model_name=MODEL_LARGE,
            prices=PriceTable.load(prices_path),
            history_window=window,
        )
        agent.run("hola", history)
        expected = 4 if window is None else min(window, 4)
        assert model.seen == [expected + 1], window


def test_metrics_start_without_cost_and_add_it_from_many_threads():
    metrics = Metrics()
    assert metrics.snapshot(2000)["cost_usd"] == 0.0

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: metrics.record_cost(0.25), range(40)))

    assert metrics.snapshot(2000)["cost_usd"] == pytest.approx(10.0)
