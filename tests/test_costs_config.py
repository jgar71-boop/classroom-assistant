"""Pruebas de la configuración de costos y del archivo ``.env.example``."""

from pathlib import Path

import pytest

from conftest import MODEL_LARGE, MODEL_SMALL, read_env_file

from app.config import DEFAULTS, load_settings

ENV_EXAMPLE = Path(__file__).resolve().parents[1] / ".env.example"
SECRET_TOKEN = "cf-test-secret-token"
COST_VARIABLES = (
    "CF_ACCOUNT_ID",
    "CF_GATEWAY_ID",
    "CF_API_TOKEN",
    "MODEL_SMALL",
    "MODEL_LARGE",
    "ROUTING",
    "ROUTER_MAX_CHARS",
    "HISTORY_WINDOW",
    "MODEL_MAX_TOKENS",
    "MODEL_TEMPERATURE",
    "MODEL_TIMEOUT_SECONDS",
    "CACHE_TTL_SECONDS",
    "PRICES_PATH",
)


@pytest.fixture
def base_env(students_path, prices_path):
    """Variables mínimas: alumnos y precios en ``tmp_path``."""
    return {"STUDENTS_PATH": str(students_path), "PRICES_PATH": str(prices_path)}


@pytest.fixture
def gateway_env(base_env):
    """Variables de un arranque válido con el modelo real."""
    return {
        **base_env,
        "MODEL_PROVIDER": "gateway",
        "CF_ACCOUNT_ID": "acc-123",
        "CF_API_TOKEN": SECRET_TOKEN,
    }


def test_cost_settings_use_the_documented_defaults(base_env):
    costs = load_settings(base_env).costs

    assert (costs.model_small, costs.model_large) == (MODEL_SMALL, MODEL_LARGE)
    assert costs.routing is True
    assert costs.router_max_chars == 80
    assert costs.history_window == 6
    assert costs.model_max_tokens == 300
    assert costs.model_temperature == 0
    assert costs.model_timeout_seconds == 20
    assert costs.cache_ttl_seconds == 0
    assert (costs.cf_account_id, costs.cf_api_token) == ("", "")
    assert costs.cf_gateway_id == "default"


def test_gateway_uses_the_default_gateway_and_hides_the_token(gateway_env):
    settings = load_settings(gateway_env)

    assert settings.model_provider == "gateway"
    assert settings.costs.cf_gateway_id == "default"
    assert settings.costs.cf_api_token == SECRET_TOKEN
    assert SECRET_TOKEN not in repr(settings)
    assert SECRET_TOKEN not in repr(settings.costs)


def test_gateway_without_account_or_token_does_not_start(gateway_env):
    for variable in ("CF_ACCOUNT_ID", "CF_API_TOKEN"):
        with pytest.raises(ValueError, match=variable):
            load_settings({**gateway_env, variable: " "})


def test_invalid_cost_settings_stop_the_app(base_env, tmp_path):
    invalid = (
        {"MODEL_SMALL": "@cf/unknown/model"},
        {"MODEL_LARGE": "@cf/unknown/model"},
        {"PRICES_PATH": str(tmp_path / "missing.json")},
        {"ROUTING": "quizas"},
        {"ROUTER_MAX_CHARS": "0"},
        {"HISTORY_WINDOW": "-1"},
        {"MODEL_MAX_TOKENS": "0"},
        {"MODEL_TEMPERATURE": "-0.5"},
        {"MODEL_TIMEOUT_SECONDS": "0"},
        {"CACHE_TTL_SECONDS": "-5"},
        {"MODEL_PROVIDER": "openai"},
    )
    for extra in invalid:
        with pytest.raises(ValueError):
            load_settings({**base_env, **extra})


def test_env_example_lists_every_variable_without_secrets():
    values = read_env_file(ENV_EXAMPLE)

    missing = (set(DEFAULTS) | set(COST_VARIABLES)) - set(values)
    assert not missing
    assert values["CF_API_TOKEN"] == ""
    assert values["CF_ACCOUNT_ID"] == ""
    assert values.get("LANGSMITH_API_KEY", "") == ""
