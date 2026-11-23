"""Tabla de precios por modelo, en USD por millón de tokens."""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType

TOKENS_PER_PRICE_UNIT = 1_000_000
PRICE_KINDS = ("input", "output")


def _read_price(model, kind, raw):
    """Valida un precio: número finito y no negativo.

    :param model: Nombre del modelo (para el mensaje de error)
    :type model: str
    :param kind: ``input`` u ``output``
    :type kind: str
    :param raw: Valor leído del archivo
    :type raw: object
    :return: Precio como número real
    :rtype: float
    :raises ValueError: Si no es un número finito mayor o igual a 0
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"Price {kind} of {model} must be a number, got {raw!r}")
    value = float(raw)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Price {kind} of {model} must be >= 0, got {raw!r}")
    return value


@dataclass(frozen=True)
class PriceTable:
    """Precios inmutables por modelo.

    :param prices: Por cada modelo, un par ``(input, output)`` en USD por millón
    :type prices: collections.abc.Mapping
    """

    prices: MappingProxyType = field(
        default_factory=lambda: MappingProxyType({})
    )

    @classmethod
    def load(cls, path):
        """Lee la tabla de precios de un archivo JSON con la clave ``models``.

        :param path: Ruta del archivo de precios
        :type path: str or pathlib.Path
        :return: Tabla de precios validada
        :rtype: PriceTable
        :raises ValueError: Si el archivo no existe, no es JSON válido o algún
            precio es inválido
        """
        source = Path(path)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except OSError as error:
            raise ValueError(f"PRICES_PATH cannot be read: {source}") from error
        except ValueError as error:
            raise ValueError(f"PRICES_PATH is not valid JSON: {source}") from error
        models = data.get("models") if isinstance(data, dict) else None
        if not isinstance(models, dict):
            raise ValueError(f"PRICES_PATH must have a 'models' object: {source}")
        prices = {}
        for model, entry in models.items():
            if not isinstance(entry, dict):
                raise ValueError(f"Prices of {model} must be an object")
            prices[model] = tuple(
                _read_price(model, kind, entry.get(kind)) for kind in PRICE_KINDS
            )
        return cls(MappingProxyType(prices))

    def require(self, *names):
        """Exige que cada modelo tenga precio.

        :param names: Nombres de modelos
        :type names: str
        :raises ValueError: Si algún modelo no tiene precio
        """
        for name in names:
            if name not in self.prices:
                raise ValueError(f"Model without price in PRICES_PATH: {name}")

    def cost(self, model, input_tokens, output_tokens):
        """Calcula el costo en USD de una llamada, sin redondear.

        :param model: Nombre del modelo
        :type model: str
        :param input_tokens: Tokens de entrada
        :type input_tokens: int
        :param output_tokens: Tokens de salida
        :type output_tokens: int
        :return: Costo en USD
        :rtype: float
        :raises ValueError: Si el modelo no tiene precio
        """
        self.require(model)
        input_price, output_price = self.prices[model]
        total = input_tokens * input_price + output_tokens * output_price
        return total / TOKENS_PER_PRICE_UNIT
