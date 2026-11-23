"""Pasos de los escenarios del asistente (``features/assistant.feature``)."""

from pytest_bdd import given, parsers, scenarios, then, when

scenarios("features/assistant.feature")

PREVIOUS_EXCHANGE = [
    {"role": "user", "content": "Hola"},
    {"role": "assistant", "content": "Hola, ¿en qué te ayudo?"},
]


@given(
    parsers.parse("the registry allows questions of up to {limit:d} characters"),
    target_fixture="client",
)
def registry_with_question_limit(sample_path, make_client, limit):
    """Cliente con un largo máximo de pregunta pequeño."""
    return make_client(sample_path, MAX_QUESTION_CHARS=limit)


@when(parsers.parse('I ask "{question}" after a previous exchange'),
      target_fixture="response")
def ask_with_history(client, question):
    """Pregunta mandando el historial que guarda el navegador."""
    return client.post(
        "/ask", json={"question": question, "history": PREVIOUS_EXCHANGE}
    )


@when(parsers.parse('I ask "{question}"'), target_fixture="response")
def ask(client, question):
    """Pregunta sin historial."""
    return client.post("/ask", json={"question": question})


@then(parsers.parse('the answer starts with "{prefix}"'))
def answer_starts_with(response, prefix):
    """Comprueba el inicio de la respuesta del asistente."""
    assert response.json()["answer"].startswith(prefix)


@then(parsers.parse('the answer is "{answer}"'))
def answer_is(response, answer):
    """Comprueba la respuesta exacta del asistente."""
    assert response.json()["answer"] == answer


@then(parsers.parse('the assistant took {steps:d} steps using only the tool "{tool}"'))
def took_steps_with_tool(response, steps, tool):
    """Comprueba las vueltas del bucle y la herramienta usada."""
    body = response.json()
    assert body["steps"] == steps
    assert body["tools_used"] == [tool]


@then(parsers.parse("the assistant answered in {steps:d} step without tools"))
def answered_without_tools(response, steps):
    """Comprueba que el modelo respondió sin pedir herramientas."""
    body = response.json()
    assert body["steps"] == steps
    assert body["tools_used"] == []


@then(parsers.parse("the assistant counted {tokens:d} input tokens"))
def counted_input_tokens(response, tokens):
    """Comprueba el conteo de tokens por palabras del modelo simulado."""
    body = response.json()
    assert body["input_tokens"] == tokens
    assert body["output_tokens"] > 0
