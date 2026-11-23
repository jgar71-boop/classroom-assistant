"""Pasos de los escenarios de observabilidad (``features/observability.feature``)."""

import json
import uuid

from pytest_bdd import given, parsers, scenarios, then, when

from conftest import FakeClock, read_log

from app.repository import StudentRepository

scenarios("features/observability.feature")


class FailingRepository(StudentRepository):
    """Repositorio cuyo almacenamiento truena con un mensaje dado."""

    def __init__(self, path, message):
        super().__init__(path)
        self._message = message

    def list_all(self):
        """Simula una falla interna del almacenamiento."""
        raise RuntimeError(self._message)


def _log_text(log_stream):
    """Todo el log, con cada evento serializado sin escapar acentos."""
    return "\n".join(
        json.dumps(event, ensure_ascii=False) for event in read_log(log_stream)
    )


def _events(log_stream, name):
    """Eventos del log con el nombre ``name``."""
    return [event for event in read_log(log_stream) if event["event"] == name]


@given("an observed registry with the ten sample students", target_fixture="client")
def observed_registry(sample_path, make_observed_client):
    """Cliente con log en memoria sobre los alumnos de ejemplo."""
    return make_observed_client(sample_path)


@given(
    parsers.parse('an observed registry whose storage fails with "{message}"'),
    target_fixture="client",
)
def failing_registry(sample_path, make_observed_client, message):
    """Cliente cuyo repositorio lanza ``RuntimeError(message)``."""
    repository = FailingRepository(sample_path, message)
    return make_observed_client(sample_path, repository=repository)


@given(
    parsers.parse("an observed registry where every request takes {millis:d} ms"),
    target_fixture="client",
)
def slow_registry(sample_path, make_observed_client, millis):
    """Cliente cuyo reloj falso avanza ``millis`` en cada lectura."""
    clock = FakeClock(step_seconds=millis / 1000)
    return make_observed_client(sample_path, clock=clock)


@when("I check the service health", target_fixture="response")
def check_health(client):
    """Consulta ``GET /health`` sin encabezado de id."""
    return client.get("/health")


@when(
    parsers.parse('I check the service health with request id "{sent}"'),
    target_fixture="response",
)
def check_health_with_id(client, sent):
    """Consulta ``GET /health`` mandando ``X-Request-ID``."""
    return client.get("/health", headers={"X-Request-ID": sent})


@when(
    parsers.parse('I ask "{question}" with request id "{request_id}"'),
    target_fixture="response",
)
def ask_with_id(client, question, request_id):
    """Pregunta al asistente mandando ``X-Request-ID``."""
    return client.post(
        "/ask", json={"question": question}, headers={"X-Request-ID": request_id}
    )


@when("I list the students", target_fixture="response")
def list_students(client):
    """Consulta ``GET /students``."""
    return client.get("/students")


@when("I read the metrics", target_fixture="metrics")
def read_metrics(client):
    """Consulta ``GET /metrics`` y devuelve el cuerpo."""
    response = client.get("/metrics")
    assert response.status_code == 200, response.text
    return response.json()


@then(parsers.parse("the response request id is {outcome}"))
def request_id_outcome(response, outcome):
    """Comprueba si el id del cliente se conservó o se reemplazó por un UUID."""
    received = response.headers["X-Request-ID"]
    sent = response.request.headers.get("X-Request-ID")
    if outcome == "kept":
        assert received == sent
    else:
        assert received != sent
        assert str(uuid.UUID(received)) == received.lower()


@then(
    parsers.parse('the answer body carries request_id "{request_id}" like the header')
)
def answer_carries_request_id(response, request_id):
    """El cuerpo de ``/ask`` y el encabezado llevan el mismo id."""
    assert response.json()["request_id"] == request_id
    assert response.headers["X-Request-ID"] == request_id


@then(
    parsers.parse(
        'the log has a tool_call audit for "{tool}" with student_id "{student_id}"'
    )
)
def tool_call_audit(log_stream, tool, student_id):
    """Hay un ``audit`` ``tool_call`` solo con el argumento esperado."""
    audits = [e for e in _events(log_stream, "audit") if e["action"] == "tool_call"]
    assert [(e["tool"], e["args"]) for e in audits] == [
        (tool, {"student_id": student_id})
    ]


@then(
    parsers.parse(
        'the log has an agent_run for "{question}" that stopped with "{stopped}"'
    )
)
def agent_run_event(log_stream, question, stopped):
    """Hay un ``agent_run`` con sus campos numéricos y la causa de parada."""
    (run,) = _events(log_stream, "agent_run")
    assert run["stopped"] == stopped
    assert run["question_chars"] == len(question)
    assert run["history_messages"] == 0
    assert run["steps"] == 2
    assert run["tools"] == ["get_student"]
    assert run["input_tokens"] > 0 and run["output_tokens"] > 0


@then(
    parsers.parse(
        'the log has a request event for "{method}" "{path}" with status {status:d}'
    )
)
def request_event(log_stream, method, path, status):
    """Hay un evento ``request`` con método, ruta, estado y latencia."""
    (event,) = _events(log_stream, "request")
    assert (event["method"], event["path"], event["status"]) == (method, path, status)
    assert event["latency_ms"] >= 0


@then(parsers.parse('every log line has request_id "{request_id}"'))
def every_line_has_request_id(log_stream, request_id):
    """Todas las líneas del log comparten el id de la petición."""
    events = read_log(log_stream)
    assert events
    assert {event["request_id"] for event in events} == {request_id}


@then(parsers.parse('neither "{question}" nor the answer appears in the log'))
def no_text_in_log(log_stream, response, question):
    """Ni la pregunta ni la respuesta quedan escritas en el log."""
    text = _log_text(log_stream)
    assert question not in text
    assert response.json()["answer"] not in text


@then("the response body is the student without request_id")
def student_body_without_request_id(response):
    """El alta devuelve el alumno como en la fase 1."""
    assert set(response.json()) == {"id", "name", "subject", "grade", "classroom"}


@then(
    parsers.parse(
        "the log has a student_created audit with grade {grade:d} "
        "and classroom {classroom:d}"
    )
)
def student_created_audit(log_stream, response, grade, classroom):
    """Hay un ``audit`` ``student_created`` con id, grado y salón."""
    audits = [
        e for e in _events(log_stream, "audit") if e["action"] == "student_created"
    ]
    assert [(e["student_id"], e["grade"], e["classroom"]) for e in audits] == [
        (response.json()["id"], grade, classroom)
    ]


@then(parsers.parse('the text "{text}" does not appear in the log'))
def text_not_in_log(log_stream, text):
    """El texto indicado no aparece en ninguna línea del log."""
    assert text not in log_stream.getvalue()
    assert text not in _log_text(log_stream)


@then(
    parsers.parse(
        "the response body is a list of {count:d} students without request_id"
    )
)
def list_without_request_id(response, count):
    """La lista conserva su forma de la fase 1."""
    body = response.json()
    assert isinstance(body, list) and len(body) == count
    assert all("request_id" not in student for student in body)


@then("the body is the generic internal error with the header request id")
def generic_internal_error(response):
    """El ``500`` no revela el error y lleva el id de la petición."""
    assert response.json() == {
        "detail": "internal error",
        "request_id": response.headers["X-Request-ID"],
    }


@then(parsers.parse('the log has an error event of type "{error_type}"'))
def error_event(log_stream, error_type):
    """Hay un evento ``error`` con el tipo de la excepción."""
    (event,) = _events(log_stream, "error")
    assert event["error_type"] == error_type


@then(parsers.parse("the metrics count at least {count:d} request"))
def metrics_count_requests(metrics, count):
    """Las métricas cuentan las peticiones de este proceso."""
    assert metrics["requests"] >= count
    assert set(metrics["latency_ms"]) == {"p50", "p95"}


@then("the metrics report input tokens above 0")
def metrics_report_tokens(metrics):
    """Las métricas suman los tokens del agente."""
    assert metrics["tokens"]["input"] > 0


@then(
    parsers.parse("the SLO target is {target:d} ms and its result is a boolean")
)
def slo_target_and_result(metrics, target):
    """La meta viene de ``SLO_P95_MS`` y el resultado es booleano."""
    assert metrics["slo"]["p95_ms_target"] == target
    assert isinstance(metrics["slo"]["met"], bool)


@then("the SLO is not met")
def slo_not_met(metrics):
    """Con latencias por encima de la meta, el SLO no se cumple."""
    assert metrics["latency_ms"]["p95"] >= 3000
    assert metrics["slo"]["met"] is False
