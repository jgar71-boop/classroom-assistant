"""Respuesta de un modelo, compartida por el modelo simulado y el real."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Completion:
    """Respuesta de un modelo.

    :param text: Texto de la respuesta (un objeto JSON)
    :type text: str
    :param input_tokens: Tokens de entrada aproximados
    :type input_tokens: int
    :param output_tokens: Tokens de salida aproximados
    :type output_tokens: int
    :param cached: Si la respuesta vino de la caché del gateway (no cuesta)
    :type cached: bool
    """

    text: str
    input_tokens: int
    output_tokens: int
    cached: bool = False
