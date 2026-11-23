"""Pruebas unitarias de la fase 2: id de petición, log, métricas, configuración,
agente y trazas."""

import io
import json
import os
import uuid
from datetime import datetime

import pytest

from conftest import FIXED_NOW, FakeClock

from app.agent import Agent
from app.config import load_settings
from app.events import EventLog
from app.llm import Completion
from app.metrics import Metrics
from app.repository import StudentRepository
from app.request_context import current_request_id, resolve_request_id


class ScriptedModel:
    """Modelo que devuelve, en orden, las respuestas JSON que se le den."""

    def __init__(self, *replies):
        self._replies = list(replies)

    def complete(self, messages):
        """Devuelve la siguiente respuesta; repite la última al agotarse."""
        del messages
        reply = self._replies.pop(0) if len(self._replies) > 1 else self._replies[0]
        return Completion(text=json.dumps(reply), input_tokens=3, output_tokens=2)


def _is_uuid(value):
    """Indica si ``value`` es un UUID en su forma canónica."""
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (TypeError, ValueError):
        return False


# --- Id de petición ---------------------------------------------------------


def test_request_id_length_and_characters_are_enforced():
    assert resolve_request_id("a" * 128) == "a" * 128
    assert resolve_request_id("x") == "x"
    assert resolve_request_id("a.b_c-1") == "a.b_c-1"
    for unsafe in ("", "a" * 129, "has space", "a{b", "a\nb", None):
        assert _is_uuid(resolve_request_id(unsafe)), unsafe


def test_generated_request_ids_are_unique():
    generated = {resolve_request_id(None) for _ in range(50)}
    assert len(generated) == 50


# --- Log de eventos ---------------------------------------------------------


def test_each_event_is_one_json_line_with_the_common_fields():
    stream = io.StringIO()
    log = EventLog("svc-test", FakeClock(), stream=stream)
    token = current_request_id.set("req-42")
    try:
        log.emit("request", method="GET", path="/health", status=200, latency_ms=1.5)
    finally:
        current_request_id.reset(token)
    output = stream.getvalue()
    assert output.endswith("\n") and output.count("\n") == 1
    event = json.loads(output)
    assert event["service"] == "svc-test"
    assert event["event"] == "request"
    assert event["request_id"] == "req-42"
    assert event["status"] == 200
    timestamp = datetime.fromisoformat(event["ts"])
    assert timestamp == FIXED_NOW and timestamp.utcoffset().total_seconds() == 0


# --- Métricas ---------------------------------------------------------------


def test_metrics_without_requests_report_zeros():
    snapshot = Metrics().snapshot(2000)
    assert snapshot["pid"] == os.getpid()
    assert snapshot["requests"] == 0
    assert snapshot["error_rate"] == 0.0
    assert snapshot["latency_ms"] == {"p50": 0.0, "p95": 0.0}
    assert snapshot["tokens"] == {"input": 0, "output": 0}
    assert snapshot["students_created"] == 0


def test_percentiles_use_the_nearest_rank_of_known_latencies():
    metrics = Metrics()
    for latency in range(1, 101):
        metrics.record_request(float(latency), 200)
    snapshot = metrics.snapshot(2000)
    assert snapshot["latency_ms"] == {"p50": 50.0, "p95": 95.0}
    assert snapshot["slo"] == {"p95_ms_target": 2000, "met": True}


def test_error_rate_counts_only_server_errors():
    metrics = Metrics()
    for status in (200, 404, 422, 500, 503):
        metrics.record_request(10.0, status)
    snapshot = metrics.snapshot(2000)
    assert snapshot["requests"] == 5
    assert snapshot["error_rate"] == pytest.approx(0.4)


def test_slo_is_not_met_when_p95_equals_the_target():
    metrics = Metrics()
    for _ in range(20):
        metrics.record_request(2000.0, 200)
    assert metrics.snapshot(2000)["slo"]["met"] is False
    assert metrics.snapshot(2001)["slo"]["met"] is True


def test_latency_window_keeps_only_the_last_thousand():
    metrics = Metrics()
    for _ in range(1000):
        metrics.record_request(5000.0, 200)
    for _ in range(1000):
        metrics.record_request(10.0, 200)
    snapshot = metrics.snapshot(2000)
    assert snapshot["requests"] == 2000
    assert snapshot["latency_ms"]["p95"] == 10.0


# --- Configuración ----------------------------------------------------------


@pytest.fixture
def base_env(students_path, prices_path):
    """Variables mínimas: alumnos y precios en ``tmp_path``."""
    return {"STUDENTS_PATH": str(students_path), "PRICES_PATH": str(prices_path)}


def test_observability_settings_have_safe_defaults(base_env):
    settings = load_settings(base_env)
    assert settings.service_name == "classroom-assistant"
    assert settings.slo_p95_ms == 2000
    assert settings.langsmith_tracing is False
    assert settings.hide_inputs is True
    assert settings.hide_outputs is True
    assert settings.tracing_enabled is False


def test_invalid_observability_settings_are_rejected(base_env):
    invalid = (
        {"SLO_P95_MS": "0"},
        {"SLO_P95_MS": "rapido"},
        {"HIDE_INPUTS": "quizas"},
        {"LANGSMITH_TRACING": "si"},
    )
    for extra in invalid:
        with pytest.raises(ValueError):
            load_settings({**base_env, **extra})


def test_tracing_needs_an_api_key_that_is_never_stored(base_env):
    base = {**base_env, "LANGSMITH_TRACING": "TRUE"}
    assert load_settings(base).tracing_enabled is False
    secret = "lsv2-test-secret-key"
    settings = load_settings({**base, "LANGSMITH_API_KEY": secret})
    assert settings.tracing_enabled is True
    assert secret not in repr(settings)


# --- Agente -----------------------------------------------------------------


def test_agent_reports_why_it_stopped(sample_path):
    repository = StudentRepository(sample_path)
    answered = Agent(ScriptedModel({"answer": "hola"}), repository, 3).run("hola")
    assert answered.stopped == "answer"
    looping = ScriptedModel(
        {"tool": "get_student", "args": {"student_id": "STU-0001"}}
    )
    exhausted = Agent(looping, repository, 2).run("STU-0001")
    assert exhausted.stopped == "max_steps"
    assert exhausted.steps == 2


def test_tool_audit_receives_only_the_expected_argument(sample_path):
    calls = []
    model = ScriptedModel(
        {"tool": "get_student", "args": {"student_id": "STU-0001", "extra": "x"}},
        {"tool": "delete_everything", "args": {"student_id": "STU-0001"}},
        {"answer": "listo"},
    )
    agent = Agent(
        model,
        StudentRepository(sample_path),
        3,
        on_tool_call=lambda name, args: calls.append((name, args)),
    )
    agent.run("STU-0001")
    assert calls == [("get_student", {"student_id": "STU-0001"})]


# --- Trazas y página --------------------------------------------------------


def test_tracing_off_never_creates_a_langsmith_client(base_env, monkeypatch):
    import langsmith  # pylint: disable=import-outside-toplevel

    from app import tracing  # pylint: disable=import-outside-toplevel

    def forbidden_client(*_args, **_kwargs):
        raise AssertionError("a LangSmith client must not be created")

    monkeypatch.setattr(langsmith, "Client", forbidden_client)
    monkeypatch.setattr(tracing, "Client", forbidden_client, raising=False)
    settings = load_settings(base_env)
    with tracing.trace_context(settings, "req-1"):
        pass


def test_home_page_shows_the_request_id_safely(sample_path, make_observed_client):
    page = make_observed_client(sample_path).get("/")
    assert page.status_code == 200
    assert "request_id" in page.text
    assert 'data-testid="request-id"' in page.text
    assert "innerHTML" not in page.text
