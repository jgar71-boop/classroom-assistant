"""Pruebas de lo que se publica: página con clave, contenedor, CI y Render."""

import re
from pathlib import Path

import yaml

from conftest import OFFICE_API_KEY, TEST_API_KEY

PRODUCT = Path(__file__).resolve().parents[1]
SECRETS = {"API_KEYS", "CF_ACCOUNT_ID", "CF_API_TOKEN"}
FIXED_VARIABLES = {
    "ENVIRONMENT": "production",
    "MODEL_PROVIDER": "gateway",
    "HIDE_INPUTS": "true",
    "HIDE_OUTPUTS": "true",
}


def _text(relative):
    """Contenido de un archivo del producto."""
    return (PRODUCT / relative).read_text(encoding="utf-8")


def _needs(job):
    """Trabajos de los que depende ``job``, siempre como lista."""
    needs = job.get("needs", [])
    return [needs] if isinstance(needs, str) else list(needs)


def test_home_page_asks_for_the_key_and_keeps_it_in_session_storage(
    sample_path, make_client
):
    page = make_client(sample_path, api_key=None).get("/")
    assert page.status_code == 200
    html = page.text

    (key_input,) = re.findall(r"<input[^>]*data-testid=\"api-key\"[^>]*>", html)
    assert 'type="password"' in key_input
    assert "sessionStorage" in html and "localStorage" not in html
    assert "X-API-Key" in html
    assert "Clave inválida" in html
    assert "Demasiadas peticiones" in html
    assert TEST_API_KEY not in html and OFFICE_API_KEY not in html
    assert "innerHTML" not in html


def test_render_blueprint_deploys_only_when_checks_pass_and_keeps_secrets_out():
    blueprint = yaml.safe_load(_text("render.yaml"))
    (service,) = blueprint["services"]
    assert service["type"] == "web"
    assert isinstance(service["name"], str) and service["name"]
    assert service["runtime"] == "docker"
    assert service["plan"] == "free"
    assert service["healthCheckPath"] == "/health"
    assert service["autoDeployTrigger"] == "checksPass"

    variables = {item["key"]: item for item in service["envVars"]}
    for name, value in FIXED_VARIABLES.items():
        assert str(variables[name]["value"]).lower() == value, name
    for name in SECRETS:
        assert variables[name]["sync"] is False, name
        assert "value" not in variables[name], name
    for name, item in variables.items():
        if "value" in item:
            assert "KEY" not in name and "TOKEN" not in name, name
    assert "LANGSMITH_API_KEY" not in _text("render.yaml")


def test_ci_pipeline_chains_style_unit_e2e_and_docker_on_every_push():
    workflow = yaml.safe_load(_text(".github/workflows/ci.yml"))
    # YAML 1.1 lee la clave ``on`` como ``True``.
    triggers = workflow.get("on", workflow.get(True))
    assert {"push", "pull_request"} <= set(triggers)

    jobs = workflow["jobs"]
    assert set(jobs) >= {"style", "unit", "e2e", "docker"}
    assert _needs(jobs["unit"]) == ["style"]
    assert _needs(jobs["e2e"]) == ["unit"]
    assert _needs(jobs["docker"]) == ["e2e"]

    text = _text(".github/workflows/ci.yml")
    assert "--max-line-length=88" in text
    assert "--cov-fail-under=80" in text
    assert "playwright" in text.lower()
    assert "docker build" in text


def test_container_runs_as_a_non_root_user_on_the_render_port():
    dockerfile = _text("Dockerfile")
    assert re.search(r"^FROM python:3\.12-slim", dockerfile, re.MULTILINE)
    users = re.findall(r"^USER\s+(\S+)", dockerfile, re.MULTILINE)
    assert users and users[-1] not in {"root", "0"}
    assert "chown" in dockerfile and "data" in dockerfile
    assert "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}" in dockerfile

    ignored = {
        line.strip().rstrip("/")
        for line in _text(".dockerignore").splitlines()
        if line.strip()
    }
    assert {".env", "tests", "e2e"} <= ignored
