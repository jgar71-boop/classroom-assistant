"""Pruebas de la configuración que se arma desde las variables de entorno."""

from pathlib import Path

import pytest

from conftest import write_prices

from app.config import load_settings


@pytest.fixture
def data_folder(tmp_path, monkeypatch):
    """Trabaja en una carpeta temporal con ``data/`` y sus precios, como el producto."""
    monkeypatch.chdir(tmp_path)
    write_prices(tmp_path / "data" / "model_prices.json")


@pytest.mark.usefixtures("data_folder")
def test_settings_use_the_documented_defaults():
    settings = load_settings({})

    assert settings.model_provider == "fake"
    assert settings.agent_max_steps == 3
    assert settings.max_question_chars == 2000
    assert Path(settings.students_path) == Path("data/students.json")


@pytest.mark.parametrize(
    ("env", "variable"),
    [
        ({"AGENT_MAX_STEPS": "0"}, "AGENT_MAX_STEPS"),
        ({"STUDENTS_PATH": "missing/students.json"}, "STUDENTS_PATH"),
    ],
    ids=["zero_max_steps", "missing_folder"],
)
@pytest.mark.usefixtures("data_folder")
def test_invalid_setting_stops_the_app_with_a_clear_message(env, variable):
    with pytest.raises(ValueError, match=variable):
        load_settings(env)
