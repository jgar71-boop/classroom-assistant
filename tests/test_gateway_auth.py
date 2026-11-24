"""Pruebas del Authenticated Gateway: encabezado ``cf-aig-authorization``, sin red.

Un AI Gateway autenticado responde 401 (código 2009) si falta ese encabezado. El
token ``CF_AIG_TOKEN`` es opcional y secreto: nunca aparece en ``repr`` ni en los
errores.
"""

from pathlib import Path

import httpx
import pytest
import yaml

from conftest import read_env_file
from test_gateway import (
    QUESTION,
    SECRET_TOKEN,
    gateway_costs,
    gateway_model,
    model_reply,
)

from app.config import Settings
from app.gateway import ModelUnavailable

PRODUCT_DIR = Path(__file__).resolve().parents[1]
AIG_TOKEN = "cf-aig-test-secret-token"
AIG_HEADER = "cf-aig-authorization"
UNAUTHORIZED = {"code": 2009, "message": "Unauthorized", "name": "AiGatewayError"}


def recording_handler(seen):
    """Manejador que guarda cada petición en ``seen`` y responde con éxito."""

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=model_reply('{"answer": "Camila"}'))

    return handler


def test_aig_token_is_optional_trimmed_and_hidden_from_repr(
    students_path, prices_path
):
    assert gateway_costs(students_path, prices_path).cf_aig_token == ""

    costs = gateway_costs(students_path, prices_path, CF_AIG_TOKEN=f"  {AIG_TOKEN} ")
    settings = Settings(
        model_provider="gateway",
        agent_max_steps=3,
        max_question_chars=2000,
        students_path=students_path,
        costs=costs,
    )

    assert costs.cf_aig_token == AIG_TOKEN
    assert AIG_TOKEN not in repr(costs)
    assert AIG_TOKEN not in repr(settings)


def test_gateway_sends_both_authorization_headers_when_the_aig_token_is_set(
    students_path, prices_path
):
    seen = []
    costs = gateway_costs(students_path, prices_path, CF_AIG_TOKEN=AIG_TOKEN)
    model = gateway_model(costs, recording_handler(seen))

    model.complete(QUESTION)
    model.complete(QUESTION)

    assert len(seen) == 2
    for request in seen:
        assert request.headers[AIG_HEADER] == f"Bearer {AIG_TOKEN}"
        assert request.headers["Authorization"] == f"Bearer {SECRET_TOKEN}"


@pytest.mark.parametrize(
    "raw_token", [None, "", "   "], ids=["unset", "empty", "blank"]
)
def test_gateway_omits_the_aig_header_when_the_token_is_empty(
    students_path, prices_path, raw_token
):
    seen = []
    extra = {} if raw_token is None else {"CF_AIG_TOKEN": raw_token}
    costs = gateway_costs(students_path, prices_path, **extra)

    gateway_model(costs, recording_handler(seen)).complete(QUESTION)

    assert AIG_HEADER not in seen[0].headers
    assert seen[0].headers["Authorization"] == f"Bearer {SECRET_TOKEN}"


def test_gateway_failures_never_leak_the_aig_token(students_path, prices_path):
    def unauthorized(_request):
        return httpx.Response(401, json={**UNAUTHORIZED, "echo": AIG_TOKEN})

    def times_out(request):
        raise httpx.ReadTimeout(f"timed out {AIG_TOKEN}", request=request)

    def connection_fails(request):
        raise httpx.ConnectError(f"refused {AIG_TOKEN}", request=request)

    costs = gateway_costs(students_path, prices_path, CF_AIG_TOKEN=AIG_TOKEN)
    for handler in (unauthorized, times_out, connection_fails):
        with pytest.raises(ModelUnavailable) as raised:
            gateway_model(costs, handler).complete(QUESTION)
        message = str(raised.value)
        assert AIG_TOKEN not in message, handler.__name__
        assert SECRET_TOKEN not in message, handler.__name__


def test_env_example_declares_an_empty_aig_token():
    values = read_env_file(PRODUCT_DIR / ".env.example")

    assert "CF_AIG_TOKEN" in values
    assert values["CF_AIG_TOKEN"] == ""


def test_render_blueprint_declares_the_aig_token_as_a_secret_without_value():
    text = (PRODUCT_DIR / "render.yaml").read_text(encoding="utf-8")
    (service,) = yaml.safe_load(text)["services"]
    variables = {item["key"]: item for item in service["envVars"]}

    assert "CF_AIG_TOKEN" in variables
    assert variables["CF_AIG_TOKEN"]["sync"] is False
    assert "value" not in variables["CF_AIG_TOKEN"]
