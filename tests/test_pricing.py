"""Pruebas de la tabla de precios por millón de tokens."""

import json

import pytest

from conftest import MODEL_LARGE, MODEL_SMALL, TEST_PRICES, write_prices

from app.pricing import PriceTable


def test_cost_uses_prices_per_million_tokens(prices_path):
    prices = PriceTable.load(prices_path)

    assert prices.cost(MODEL_SMALL, 1_000_000, 500_000) == pytest.approx(
        0.045 + 0.192
    )
    assert prices.cost(MODEL_LARGE, 1000, 200) == pytest.approx(
        (1000 * 0.293 + 200 * 2.253) / 1_000_000
    )
    assert prices.cost(MODEL_LARGE, 0, 0) == 0


def test_bad_price_files_and_unknown_models_are_rejected(tmp_path, prices_path):
    negative = json.loads(json.dumps(TEST_PRICES))
    negative["models"][MODEL_SMALL]["output"] = -1
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    bad_files = (
        write_prices(tmp_path / "negative.json", negative),
        broken,
        tmp_path / "missing.json",
    )

    for path in bad_files:
        with pytest.raises(ValueError):
            PriceTable.load(path)
    with pytest.raises(ValueError, match="@cf/unknown/model"):
        PriceTable.load(prices_path).require(MODEL_SMALL, "@cf/unknown/model")
