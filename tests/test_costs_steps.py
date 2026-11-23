"""Pasos de los escenarios de costos (``features/costs.feature``)."""

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import MODEL_LARGE, MODEL_SMALL, expected_cost, read_log

from app.llm import FakeModel
from app.repository import StudentRepository

scenarios("features/costs.feature")

MODELS_BY_SIZE = {"small": MODEL_SMALL, "large": MODEL_LARGE}


class SpyModel(FakeModel):
    """Modelo simulado que anota cuántos mensajes recibe en cada llamada."""

    def __init__(self, repository):
        super().__init__(repository)
        self.message_counts = []

    def complete(self, messages):
        """Anota el número de mensajes y responde como el modelo simulado."""
        self.message_counts.append(len(messages))
        return super().complete(messages)


class UnavailableModel:
    """Modelo que siempre falla como un gateway caído."""

    def complete(self, messages):
        """Lanza ``ModelUnavailable`` sin mirar los mensajes."""
        del messages
        # Importación tardía: el módulo es nuevo en la fase 3.
        from app.gateway import (  # pylint: disable=import-outside-toplevel
            ModelUnavailable,
        )

        raise ModelUnavailable("gateway down")


@pytest.fixture
def answers():
    """Respuestas de ``POST /ask`` de un escenario, en orden."""
    return []


@pytest.fixture
def spy(sample_path):
    """Modelo espía sobre los alumnos de prueba."""
    return SpyModel(StudentRepository(sample_path))


def _events(log_stream, name):
    """Eventos del log con el nombre ``name``."""
    return [event for event in read_log(log_stream) if event["event"] == name]


@given("a priced registry with the default settings", target_fixture="client")
def priced_registry(sample_path, make_observed_client):
    """Cliente con precios de prueba y la configuración por omisión."""
    return make_observed_client(sample_path)


@given(
    parsers.parse('a priced registry where {variable} is "{value}"'),
    target_fixture="client",
)
def priced_registry_with(sample_path, make_observed_client, variable, value):
    """Cliente con una variable de entorno cambiada."""
    return make_observed_client(sample_path, **{variable: value})


@given(
    parsers.parse('a spied registry where {variable} is "{value}"'),
    target_fixture="client",
)
def spied_registry(sample_path, make_observed_client, spy, variable, value):
    """Cliente cuyo modelo anota lo que recibe."""
    return make_observed_client(sample_path, model=spy, **{variable: value})


@given("a priced registry whose model is unavailable", target_fixture="client")
def unavailable_registry(sample_path, make_observed_client):
    """Cliente cuyo modelo siempre lanza ``ModelUnavailable``."""
    return make_observed_client(sample_path, model=UnavailableModel())


@when(parsers.parse('I ask "{question}" with {count:d} history messages'),
      target_fixture="response")
def ask_with_history(client, question, count):
    """Pregunta mandando ``count`` mensajes previos alternados."""
    history = [
        {"role": "user" if n % 2 == 0 else "assistant", "content": f"mensaje {n}"}
        for n in range(count)
    ]
    return client.post("/ask", json={"question": question, "history": history})


@when(parsers.parse("I ask a question of {length:d} characters"),
      target_fixture="response")
def ask_of_length(client, answers, length):
    """Pregunta con un texto de exactamente ``length`` caracteres."""
    response = client.post("/ask", json={"question": "x" * length})
    answers.append(response)
    return response


@when(parsers.parse('I ask "{question}"'), target_fixture="response")
def ask(client, answers, question):
    """Pregunta sin historial y guarda la respuesta."""
    response = client.post("/ask", json={"question": question})
    answers.append(response)
    return response


@then(parsers.parse('the answer used the {size} model with route "{route}"'))
def answer_used_model(response, size, route):
    """La respuesta dice qué modelo eligió el enrutador y por qué."""
    body = response.json()
    assert body["model"] == MODELS_BY_SIZE[size]
    assert body["route"] == route


@then(
    parsers.parse(
        "the answer cost matches the small model prices with {cached:d} cached calls"
    )
)
def cost_matches_small_prices(response, cached):
    """El costo sale de los tokens de la respuesta y el precio del modelo chico."""
    body = response.json()
    assert body["cached_calls"] == cached
    assert body["cost_usd"] > 0
    assert body["cost_usd"] == pytest.approx(
        expected_cost(MODEL_SMALL, body["input_tokens"], body["output_tokens"])
    )


@then(parsers.parse("the model received {count:d} messages on its first call"))
def model_received(spy, count):
    """El espía recibió el historial recortado más la pregunta."""
    assert spy.message_counts[0] == count


@then("the metrics cost_usd is the sum of the answer costs")
def metrics_cost_is_sum(client, answers):
    """``/metrics`` acumula solo el costo de las respuestas del asistente."""
    total = sum(answer.json()["cost_usd"] for answer in answers)
    metrics = client.get("/metrics").json()
    assert total > 0
    assert metrics["cost_usd"] == pytest.approx(total)


@then("the agent_run log has the model, route and cost of the answer")
def agent_run_has_costs(log_stream, response):
    """El evento ``agent_run`` repite modelo, ruta y costo de la respuesta."""
    body = response.json()
    (run,) = _events(log_stream, "agent_run")
    assert run["model"] == body["model"]
    assert run["route"] == body["route"]
    assert run["cost_usd"] == pytest.approx(body["cost_usd"])


@then(parsers.parse('the text "{text}" does not appear in the log'))
def text_not_in_log(log_stream, text):
    """El texto indicado no aparece en ninguna línea del log."""
    assert text not in log_stream.getvalue()


@then(parsers.parse('the body is "{detail}" with the header request id'))
def body_with_request_id(response, detail):
    """El error lleva el detalle fijo y el id de la petición."""
    assert response.json() == {
        "detail": detail,
        "request_id": response.headers["X-Request-ID"],
    }


@then(parsers.parse('the log has an error event of type "{error_type}"'))
def error_event(log_stream, error_type):
    """Hay un evento ``error`` con el tipo de la excepción, sin su mensaje."""
    (event,) = _events(log_stream, "error")
    assert event["error_type"] == error_type
    assert "gateway down" not in log_stream.getvalue()


@then("the metrics error rate is above 0")
def metrics_error_rate(client):
    """El ``502`` cuenta como error en las métricas."""
    assert client.get("/metrics").json()["error_rate"] > 0
