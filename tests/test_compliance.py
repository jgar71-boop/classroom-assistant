"""Pruebas del compliance como código: reglas que impiden arrancar en producción."""

import pytest

from app.config import load_settings

LONG_KEY = "prod-key-0123456789"
SHORT_KEY = "short-key-01234"
SIXTEEN_KEY = "exact-key-012345"
CF_TOKEN = "cf-test-secret-token"


@pytest.fixture
def production_env(students_path, prices_path):
    """Variables de un arranque de producción válido, todas en ``tmp_path``."""
    return {
        "STUDENTS_PATH": str(students_path),
        "PRICES_PATH": str(prices_path),
        "ENVIRONMENT": "production",
        "MODEL_PROVIDER": "gateway",
        "CF_ACCOUNT_ID": "acc-123",
        "CF_API_TOKEN": CF_TOKEN,
        "API_KEYS": f"teacher:{LONG_KEY}",
    }


def _refusal(env):
    """Mensaje del error con el que el producto se niega a arrancar."""
    with pytest.raises(ValueError) as error:
        load_settings(env)
    return str(error.value)


def test_each_production_rule_stops_the_app_on_its_own(production_env):
    assert "MODEL_PROVIDER" in _refusal({**production_env, "MODEL_PROVIDER": "fake"})
    assert "API_KEYS" in _refusal({**production_env, "API_KEYS": ""})

    short = _refusal({**production_env, "API_KEYS": f"teacher:{SHORT_KEY}"})
    assert len(SHORT_KEY) == 15
    assert "API_KEYS" in short and "entry 1" in short and "15" in short
    assert load_settings({**production_env, "API_KEYS": f"teacher:{SIXTEEN_KEY}"})

    traced = {**production_env, "LANGSMITH_TRACING": "true"}
    assert "HIDE_INPUTS" in _refusal({**traced, "HIDE_INPUTS": "false"})
    assert "HIDE_OUTPUTS" in _refusal({**traced, "HIDE_OUTPUTS": "false"})


def test_all_production_failures_are_reported_together_without_secrets(
    production_env,
):
    message = _refusal(
        {
            **production_env,
            "MODEL_PROVIDER": "fake",
            "API_KEYS": f"teacher:{SHORT_KEY}",
            "LANGSMITH_TRACING": "true",
            "HIDE_OUTPUTS": "false",
        }
    )
    for rule in ("MODEL_PROVIDER", "API_KEYS", "HIDE_OUTPUTS"):
        assert rule in message
    for secret in (SHORT_KEY, LONG_KEY, CF_TOKEN):
        assert secret not in message


def test_valid_production_starts_and_development_skips_the_rules(production_env):
    settings = load_settings(production_env)
    assert settings.security.environment == "production"
    assert LONG_KEY not in repr(settings)

    relaxed = load_settings(
        {
            **production_env,
            "ENVIRONMENT": "development",
            "MODEL_PROVIDER": "fake",
            "API_KEYS": f"teacher:{SHORT_KEY}",
            "LANGSMITH_TRACING": "true",
            "HIDE_INPUTS": "false",
        }
    )
    assert relaxed.security.environment == "development"
