"""Pruebas de la prueba de humo ``scripts/smoke.py``, sin red (``httpx.MockTransport``).

Interfaz que se prueba: ``main(argv, transport=None) -> int``, donde ``argv`` es
``[url]`` y la clave sale de la variable ``SMOKE_API_KEY``.
"""

import importlib.util
from pathlib import Path

import httpx
import pytest

SMOKE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "smoke.py"
SMOKE_KEY = "smoke-key-0123456789"
URL = "https://classroom.example.test"


def _load_smoke():
    """Importa ``scripts/smoke.py`` como módulo."""
    spec = importlib.util.spec_from_file_location("smoke", SMOKE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeService:
    """Servicio simulado que exige la clave y anota cada petición."""

    def __init__(self, ask_without_key_status=401):
        self.ask_without_key_status = ask_without_key_status
        self.requests = []

    def handle(self, request):
        """Responde como el producto publicado."""
        self.requests.append(request)
        has_key = request.headers.get("X-API-Key") == SMOKE_KEY
        path = request.url.path
        if path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/ask":
            if has_key:
                return httpx.Response(200, json={"answer": "ok"})
            return httpx.Response(self.ask_without_key_status, json={"detail": "x"})
        if path == "/students" and not has_key:
            return httpx.Response(401, json={"detail": "invalid or missing API key"})
        return httpx.Response(201, json={"id": "STU-0099"})

    def transport(self):
        """Transporte de ``httpx`` que llama a ``handle``."""
        return httpx.MockTransport(self.handle)


@pytest.fixture
def smoke():
    """Módulo de la prueba de humo."""
    return _load_smoke()


def test_smoke_fails_without_the_environment_key_or_when_a_check_fails(
    smoke, monkeypatch, capsys
):
    service = FakeService()
    monkeypatch.delenv("SMOKE_API_KEY", raising=False)
    assert smoke.main([URL], transport=service.transport()) != 0
    assert "[FAIL]" in capsys.readouterr().out
    assert not service.requests

    open_service = FakeService(ask_without_key_status=200)
    monkeypatch.setenv("SMOKE_API_KEY", SMOKE_KEY)
    assert smoke.main([URL], transport=open_service.transport()) != 0
    output = capsys.readouterr().out
    assert "[FAIL]" in output and SMOKE_KEY not in output


def test_smoke_reports_four_checks_without_leaking_the_key_or_registering(
    smoke, monkeypatch, capsys
):
    service = FakeService()
    monkeypatch.setenv("SMOKE_API_KEY", SMOKE_KEY)

    assert smoke.main([URL], transport=service.transport()) == 0

    output = capsys.readouterr()
    assert output.out.count("[OK]") == 4
    assert "[FAIL]" not in output.out
    assert SMOKE_KEY not in output.out + output.err
    registrations = [
        r for r in service.requests if r.method == "POST" and r.url.path == "/students"
    ]
    assert registrations
    assert all("X-API-Key" not in r.headers for r in registrations)
