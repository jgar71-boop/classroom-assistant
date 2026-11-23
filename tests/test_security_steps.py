"""Pasos de los escenarios de seguridad (``features/security.feature``)."""

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, scenarios, then, when

from conftest import (
    API_KEY_HEADER,
    OFFICE_API_KEY,
    OFFICE_CLIENT,
    SAMPLE_STUDENTS,
    TEST_API_KEY,
    TEST_CLIENT,
    read_log,
)

from app.gateway import ModelUnavailable
from app.security import RateLimiter

scenarios("features/security.feature")

UNAUTHORIZED = "invalid or missing API key"
QUESTION = {"question": "¿Quién es STU-0003?"}
NEW_STUDENT = {"name": "Ana Paz", "subject": "Arte", "grade": 2, "classroom": 112}
PROTECTED_CALLS = (
    ("POST", "/ask", QUESTION),
    ("GET", "/metrics", None),
    ("POST", "/students", NEW_STUDENT),
    ("GET", "/students", None),
    ("GET", "/students/STU-0003", None),
)
PUBLIC_PAGES = ("/", "/health", "/docs", "/openapi.json")


class UnavailableModel:
    """Modelo que siempre falla como un gateway caído."""

    def complete(self, messages):
        """Lanza ``ModelUnavailable`` sin mirar los mensajes."""
        del messages
        raise ModelUnavailable("gateway down")


def _anonymous(client):
    """Otro ``TestClient`` sobre la misma aplicación, sin clave."""
    return TestClient(client.app, raise_server_exceptions=False)


def _with_key(client, api_key):
    """Otro ``TestClient`` sobre la misma aplicación, con la clave ``api_key``."""
    return TestClient(
        client.app,
        headers={API_KEY_HEADER: api_key},
        raise_server_exceptions=False,
    )


def _events(log_stream, name):
    """Eventos del log con el nombre ``name``."""
    return [event for event in read_log(log_stream) if event["event"] == name]


@pytest.fixture
def answers():
    """Respuestas de un escenario, en orden."""
    return []


@given("a secured registry with the ten sample students", target_fixture="client")
def secured_registry(sample_path, make_observed_client):
    """Cliente con la clave de ``teacher`` sobre los alumnos de prueba."""
    return make_observed_client(sample_path)


@given(
    "a secured registry limited to 1 request per minute whose model is down",
    target_fixture="client",
)
def limited_registry_with_model_down(sample_path, make_observed_client, capsys):
    """Cliente con límite de 1 por minuto y un modelo que siempre falla.

    Pide ``capsys`` desde el inicio para capturar toda la salida de error.
    """
    del capsys
    return make_observed_client(
        sample_path, model=UnavailableModel(), RATE_LIMIT_PER_MINUTE=1
    )


@given(
    "a secured registry limited to 2 requests per minute on a manual clock",
    target_fixture="client",
)
def limited_registry(sample_path, make_observed_client, manual_clock):
    """Cliente con un limitador inyectado de 2 por minuto sobre el reloj manual."""
    return make_observed_client(
        sample_path, rate_limiter=RateLimiter(2, manual_clock)
    )


@when("a visitor without a key calls every protected route")
def call_protected_routes(client, answers):
    """Llama sin clave a cada ruta protegida, incluida un alta válida."""
    anonymous = _anonymous(client)
    for method, path, body in PROTECTED_CALLS:
        answers.append(anonymous.request(method, path, json=body))


@when("a visitor without a key opens the public pages")
def open_public_pages(client, answers):
    """Abre sin clave las páginas libres."""
    anonymous = _anonymous(client)
    for path in PUBLIC_PAGES:
        answers.append(anonymous.get(path))


@when("a visitor without a key checks the service health")
def anonymous_health(client):
    """Consulta ``GET /health`` sin clave."""
    assert _anonymous(client).get("/health").status_code == 200


@when(parsers.parse('I ask "{question}" with my key'), target_fixture="response")
def ask_with_my_key(client, answers, question):
    """Pregunta con la clave de ``teacher``."""
    response = client.post("/ask", json={"question": question})
    answers.append(response)
    return response


@when(
    parsers.parse('I ask "{question}" with the key "{api_key}"'),
    target_fixture="response",
)
def ask_with_key(client, answers, question, api_key):
    """Pregunta con una clave dada."""
    response = _with_key(client, api_key).post("/ask", json={"question": question})
    answers.append(response)
    return response


@when(parsers.parse('I ask "{question}" without a key'), target_fixture="response")
def ask_without_key(client, question):
    """Pregunta sin mandar ``X-API-Key``."""
    return _anonymous(client).post("/ask", json={"question": question})


@when(parsers.parse('the client "{name}" asks {count:d} questions'))
def client_asks(client, answers, name, count):
    """El cliente ``teacher`` hace ``count`` preguntas seguidas."""
    assert name == TEST_CLIENT
    for _ in range(count):
        answers.append(client.post("/ask", json=QUESTION))


@then(parsers.parse('every call answers 401 with "{detail}"'))
def every_call_unauthorized(answers, detail):
    """Todas las llamadas responden ``401`` con el detalle fijo."""
    assert len(answers) == len(PROTECTED_CALLS)
    for (method, path, _), response in zip(PROTECTED_CALLS, answers):
        assert response.status_code == 401, (method, path, response.text)
        assert response.json() == {"detail": detail}


@then("the registry still has the ten sample students")
def registry_unchanged(client):
    """El alta sin clave no registró a nadie."""
    assert client.get("/students").json() == SAMPLE_STUDENTS


@then(parsers.parse('the body detail is "{detail}"'))
def body_detail(response, detail):
    """El cuerpo trae solo el detalle indicado."""
    assert response.json() == {"detail": detail}


@then("every public page answers 200")
def public_pages_ok(answers):
    """Las páginas libres responden sin clave."""
    for path, response in zip(PUBLIC_PAGES, answers):
        assert response.status_code == 200, path


@then(
    parsers.parse("the question succeeded and the registry has {count:d} students")
)
def question_and_registration_succeeded(client, answers, count):
    """La pregunta respondió ``200`` y el alta con clave quedó guardada."""
    (ask_response,) = answers
    assert ask_response.status_code == 200, ask_response.text
    assert len(client.get("/students").json()) == count


@then(
    parsers.parse(
        'the log names the client "{name}" in request, agent_run and both audits'
    )
)
def log_names_client(log_stream, name):
    """``request``, ``agent_run`` y los dos ``audit`` llevan el cliente."""
    events = read_log(log_stream)
    protected = [
        e for e in events if e["event"] != "request" or e["path"] != "/health"
    ]
    kinds = {(e["event"], e.get("action")) for e in protected}
    assert ("audit", "student_created") in kinds
    assert ("audit", "tool_call") in kinds
    assert ("agent_run", None) in kinds
    assert ("request", None) in kinds
    assert {e["client"] for e in protected} == {name}


@then("the health request event has no client")
def health_has_no_client(log_stream):
    """Una ruta libre deja ``client`` en ``null``."""
    (health,) = [e for e in _events(log_stream, "request") if e["path"] == "/health"]
    assert "client" in health and health["client"] is None


@then("the answers had the statuses 502, 429 and 401")
def statuses_seen(answers):
    """El modelo cae, luego se rebasa el límite, luego la clave es mala."""
    assert [answer.status_code for answer in answers] == [502, 429, 401]


@then("no key appears in the log, the bodies or the error output")
def no_key_anywhere(log_stream, answers, capsys):
    """Ninguna clave, válida o no, queda escrita."""
    captured = capsys.readouterr()
    written = [log_stream.getvalue(), captured.out, captured.err]
    written += [answer.text for answer in answers]
    for secret in (TEST_API_KEY, OFFICE_API_KEY, "wrong-key-0000000000"):
        for text in written:
            assert secret not in text


@then(
    parsers.parse(
        'the last answer is 429 "{detail}" with a positive Retry-After'
    )
)
def last_answer_limited(answers, detail):
    """La tercera petición se rechaza y dice cuánto esperar."""
    assert [answer.status_code for answer in answers[:-1]] == [200, 200]
    last = answers[-1]
    assert last.status_code == 429
    assert last.json() == {"detail": detail}
    assert int(last.headers["Retry-After"]) > 0


@then(parsers.parse('the client "{name}" can still ask'))
def other_client_passes(client, name):
    """El límite de un cliente no afecta a otro."""
    assert name == OFFICE_CLIENT
    response = _with_key(client, OFFICE_API_KEY).post("/ask", json=QUESTION)
    assert response.status_code == 200, response.text


@then(parsers.parse('after {seconds:d} seconds the client "{name}" can ask again'))
def passes_after_window(client, manual_clock, seconds, name):
    """Al pasar el minuto, el cliente vuelve a pasar."""
    assert name == TEST_CLIENT
    manual_clock.advance(seconds)
    assert client.post("/ask", json=QUESTION).status_code == 200


@then("the response has an X-Request-ID header")
def has_request_id(response):
    """Un ``401`` también lleva el id de la petición."""
    assert response.headers.get("X-Request-ID")


@then(parsers.parse("the metrics count {count:d} request"))
def metrics_count(client, count):
    """El rechazo cuenta en las métricas del proceso."""
    assert client.get("/metrics").json()["requests"] == count
