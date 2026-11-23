"""Pruebas del modelo real por AI Gateway, sin red: ``httpx.MockTransport``."""

import json

import httpx
import pytest

from conftest import MODEL_SMALL

from app.config import load_settings
from app.gateway import SYSTEM_PROMPT, GatewayModel, ModelUnavailable

SECRET_TOKEN = "cf-test-secret-token"
GATEWAY_URL = (
    "https://gateway.ai.cloudflare.com/v1/acc-123/gw-test"
    "/workers-ai/v1/chat/completions"
)
QUESTION = [{"role": "user", "content": "¿Quién es STU-0003?"}]


def gateway_costs(students_path, prices_path, **extra):
    """Configuración de costos de un arranque con ``MODEL_PROVIDER=gateway``."""
    env = {
        "STUDENTS_PATH": str(students_path),
        "PRICES_PATH": str(prices_path),
        "MODEL_PROVIDER": "gateway",
        "CF_ACCOUNT_ID": "acc-123",
        "CF_GATEWAY_ID": "gw-test",
        "CF_API_TOKEN": SECRET_TOKEN,
        **extra,
    }
    return load_settings(env).costs


def model_reply(content, prompt_tokens=12, completion_tokens=4):
    """Cuerpo de una respuesta exitosa del gateway."""
    return {
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
    }


def gateway_model(costs, handler):
    """``GatewayModel`` del modelo chico con un cliente que no sale a la red."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return GatewayModel(costs, MODEL_SMALL, client)


def test_gateway_sends_the_documented_request_and_reads_usage(
    students_path, prices_path
):
    seen = []

    def handler(request):
        seen.append(request)
        fenced = '```json\n{"answer": "Camila"}\n```'
        return httpx.Response(200, json=model_reply(fenced))

    model = gateway_model(gateway_costs(students_path, prices_path), handler)
    completion = model.complete(QUESTION)

    assert len(seen) == 1
    request = seen[0]
    assert request.method == "POST"
    assert str(request.url) == GATEWAY_URL
    assert request.headers["Authorization"] == f"Bearer {SECRET_TOKEN}"
    assert "cf-aig-cache-ttl" not in request.headers
    assert request.extensions["timeout"]["read"] == 20
    body = json.loads(request.content)
    assert set(body) == {"model", "messages", "max_tokens", "temperature"}
    assert (body["model"], body["max_tokens"], body["temperature"]) == (
        MODEL_SMALL,
        300,
        0,
    )
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert body["messages"][1:] == QUESTION
    assert json.loads(completion.text) == {"answer": "Camila"}
    assert (completion.input_tokens, completion.output_tokens) == (12, 4)
    assert completion.cached is False


def test_gateway_cache_sends_the_ttl_and_marks_hits_as_cached(
    students_path, prices_path
):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json=model_reply('{"answer": "hola"}'),
            headers={"cf-aig-cache-status": "hit"},
        )

    costs = gateway_costs(students_path, prices_path, CACHE_TTL_SECONDS="300")
    completion = gateway_model(costs, handler).complete(QUESTION)

    assert seen[0].headers["cf-aig-cache-ttl"] == "300"
    assert completion.cached is True


def test_gateway_failures_raise_model_unavailable_without_secrets(
    students_path, prices_path
):
    def times_out(request):
        raise httpx.ReadTimeout("timed out", request=request)

    def server_error(_request):
        return httpx.Response(500, text=f"boom {SECRET_TOKEN}")

    def malformed_body(_request):
        return httpx.Response(200, json={"result": "no choices here"})

    costs = gateway_costs(students_path, prices_path)
    for handler in (times_out, server_error, malformed_body):
        with pytest.raises(ModelUnavailable) as raised:
            gateway_model(costs, handler).complete(QUESTION)
        assert SECRET_TOKEN not in str(raised.value), handler.__name__
        assert "gateway.ai.cloudflare.com" not in str(raised.value), handler.__name__
