"""Enrutador por pregunta: una regla en código elige el modelo chico o el grande."""

import re
from dataclasses import dataclass

from app.repository import normalize

REASON_DISABLED = "routing_disabled"
REASON_LONG = "long_question"
REASON_SHORT = "short_question"
KEYWORD_PREFIX = "keyword:"
# En el orden de la especificación y con su forma original.
KEYWORDS = ("compara", "resume", "explica", "por qué", "analiza", "todos")


def _keyword_pattern(keyword):
    """Arma la expresión que busca la palabra normalizada al inicio de una palabra.

    :param keyword: Palabra clave con su forma original
    :type keyword: str
    :return: Expresión regular compilada
    :rtype: re.Pattern
    """
    words = normalize(keyword).split()
    return re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in words))


KEYWORD_PATTERNS = tuple((word, _keyword_pattern(word)) for word in KEYWORDS)


@dataclass(frozen=True)
class RouteDecision:
    """Modelo elegido para una pregunta y el motivo.

    :param model: Nombre del modelo elegido
    :type model: str
    :param reason: Motivo: ``routing_disabled``, ``long_question``,
        ``keyword:<palabra>`` o ``short_question``
    :type reason: str
    """

    model: str
    reason: str


def choose_route(question, costs):
    """Elige el modelo de una pregunta.

    :param question: Pregunta de la persona
    :type question: str
    :param costs: Configuración de costos
    :type costs: app.config.CostSettings
    :return: Modelo y motivo
    :rtype: RouteDecision
    """
    if not costs.routing:
        return RouteDecision(costs.model_large, REASON_DISABLED)
    if len(question) > costs.router_max_chars:
        return RouteDecision(costs.model_large, REASON_LONG)
    normalized = normalize(question)
    for word, pattern in KEYWORD_PATTERNS:
        if pattern.search(normalized):
            return RouteDecision(costs.model_large, KEYWORD_PREFIX + word)
    return RouteDecision(costs.model_small, REASON_SHORT)
