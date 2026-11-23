"""Pruebas de la configuración de seguridad y del ``client`` en el log y la traza."""

import contextlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import FakeClock, read_env_file

from app import tracing
from app.config import DEFAULTS, load_settings
from app.events import EventLog
from app.request_context import API_KEY_HEADER, current_client

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"


@pytest.fixture
def base_env(students_path, prices_path):
    """Variables mínimas: alumnos y precios en ``tmp_path``."""
    return {"STUDENTS_PATH": str(students_path), "PRICES_PATH": str(prices_path)}


def test_security_settings_use_the_documented_defaults(base_env):
    assert DEFAULTS["ENVIRONMENT"] == "development"
    assert DEFAULTS["API_KEYS"] == ""
    assert DEFAULTS["RATE_LIMIT_PER_MINUTE"] == "30"
    assert API_KEY_HEADER == "X-API-Key"

    security = load_settings(base_env).security
    assert security.environment == "development"
    assert security.rate_limit_per_minute == 30
    assert security.api_keys.identify("any-key-0123456789") is None

    example = read_env_file(ENV_EXAMPLE)
    assert example["ENVIRONMENT"] == "development"
    assert example["API_KEYS"] == ""
    assert example["RATE_LIMIT_PER_MINUTE"] == "30"


def test_invalid_security_settings_stop_the_app(base_env):
    invalid = (
        {"ENVIRONMENT": "prod"},
        {"RATE_LIMIT_PER_MINUTE": "0"},
        {"RATE_LIMIT_PER_MINUTE": "rapido"},
        {"API_KEYS": "teacher-key-without-client"},
    )
    for extra in invalid:
        with pytest.raises(ValueError) as error:
            load_settings({**base_env, **extra})
        assert "teacher-key-without-client" not in str(error.value)


def test_client_name_reaches_every_event_and_the_trace_metadata(
    base_env, monkeypatch
):
    stream = io.StringIO()
    log = EventLog("svc-test", FakeClock(), stream=stream)
    result = SimpleNamespace(
        steps=1, tools_used=[], input_tokens=3, output_tokens=2, stopped="answer"
    )
    token = current_client.set("teacher")
    try:
        log.request("POST", "/ask", 200, 1.0)
        log.agent_run(5, 0, result, "short")
        log.tool_call("get_student", {"student_id": "STU-0003"})
        log.student_created({"id": "STU-0011", "grade": 2, "classroom": 112})
        log.error(RuntimeError("boom"))
    finally:
        current_client.reset(token)
    log.request("GET", "/health", 200, 1.0)

    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert [event["client"] for event in events] == ["teacher"] * 5 + [None]

    captured = {}

    def fake_tracing_context(**kwargs):
        captured.update(kwargs)
        return contextlib.nullcontext()

    monkeypatch.setattr(tracing, "tracing_context", fake_tracing_context)
    monkeypatch.setattr(tracing, "_client_for", lambda settings: object())
    settings = load_settings(
        {**base_env, "LANGSMITH_TRACING": "true", "LANGSMITH_API_KEY": "lsv2-x"}
    )
    with tracing.trace_context(settings, "req-1", "m", "short", client="teacher"):
        pass
    assert captured["metadata"]["client"] == "teacher"
    assert captured["metadata"]["request_id"] == "req-1"
