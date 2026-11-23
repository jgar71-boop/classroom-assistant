"""Configuración del Classroom Assistant, armada desde variables de entorno."""

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from app.compliance import check_production
from app.pricing import PriceTable
from app.security import ApiKeys, parse_api_keys

GATEWAY_PROVIDER = "gateway"
SUPPORTED_PROVIDERS = ("fake", GATEWAY_PROVIDER)
DEFAULTS = {
    "MODEL_PROVIDER": "fake",
    "AGENT_MAX_STEPS": "3",
    "MAX_QUESTION_CHARS": "2000",
    "STUDENTS_PATH": "data/students.json",
    "SERVICE_NAME": "classroom-assistant",
    "SLO_P95_MS": "2000",
    "LANGSMITH_TRACING": "false",
    "HIDE_INPUTS": "true",
    "HIDE_OUTPUTS": "true",
    "CF_GATEWAY_ID": "default",
    "MODEL_SMALL": "@cf/meta/llama-3.1-8b-instruct-fast",
    "MODEL_LARGE": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
    "ROUTING": "true",
    "ROUTER_MAX_CHARS": "80",
    "HISTORY_WINDOW": "6",
    "MODEL_MAX_TOKENS": "300",
    "MODEL_TEMPERATURE": "0",
    "MODEL_TIMEOUT_SECONDS": "20",
    "CACHE_TTL_SECONDS": "0",
    "PRICES_PATH": "data/model_prices.json",
    "ENVIRONMENT": "development",
    "API_KEYS": "",
    "RATE_LIMIT_PER_MINUTE": "30",
}
# Solo estos dos: un ``prod`` mal escrito no se salta el compliance.
SUPPORTED_ENVIRONMENTS = ("development", "production")
BOOLEAN_VALUES = {"true": True, "false": False}
API_KEY_VARIABLE = "LANGSMITH_API_KEY"
# Variables de Cloudflare sin valor por omisión: con ``gateway`` son obligatorias.
REQUIRED_GATEWAY_VARIABLES = ("CF_ACCOUNT_ID", "CF_API_TOKEN")


@dataclass(frozen=True)
class CostSettings:  # pylint: disable=too-many-instance-attributes
    """Configuración del modelo real y de las palancas de costo (fase 3).

    El token de Cloudflare no aparece en ``repr``.

    :param cf_account_id: Cuenta de Cloudflare
    :type cf_account_id: str
    :param cf_gateway_id: Id del AI Gateway
    :type cf_gateway_id: str
    :param cf_api_token: Token secreto de Cloudflare
    :type cf_api_token: str
    :param model_small: Modelo barato
    :type model_small: str
    :param model_large: Modelo capaz
    :type model_large: str
    :param routing: Si se enruta por pregunta
    :type routing: bool
    :param router_max_chars: Largo a partir del cual se usa el modelo capaz
    :type router_max_chars: int
    :param history_window: Mensajes de historial que se mandan al modelo
    :type history_window: int
    :param model_max_tokens: Tope de tokens de salida
    :type model_max_tokens: int
    :param model_temperature: Temperatura del modelo
    :type model_temperature: float
    :param model_timeout_seconds: Tiempo máximo de una llamada al gateway
    :type model_timeout_seconds: float
    :param cache_ttl_seconds: TTL de la caché del gateway (0: apagada)
    :type cache_ttl_seconds: int
    :param prices_path: Ruta del archivo de precios
    :type prices_path: pathlib.Path
    :param prices: Tabla de precios ya validada
    :type prices: app.pricing.PriceTable
    """

    cf_account_id: str = field(default="", repr=False)
    cf_gateway_id: str = DEFAULTS["CF_GATEWAY_ID"]
    cf_api_token: str = field(default="", repr=False)
    model_small: str = DEFAULTS["MODEL_SMALL"]
    model_large: str = DEFAULTS["MODEL_LARGE"]
    routing: bool = True
    router_max_chars: int = int(DEFAULTS["ROUTER_MAX_CHARS"])
    history_window: int = int(DEFAULTS["HISTORY_WINDOW"])
    model_max_tokens: int = int(DEFAULTS["MODEL_MAX_TOKENS"])
    model_temperature: float = float(DEFAULTS["MODEL_TEMPERATURE"])
    model_timeout_seconds: float = float(DEFAULTS["MODEL_TIMEOUT_SECONDS"])
    cache_ttl_seconds: int = int(DEFAULTS["CACHE_TTL_SECONDS"])
    prices_path: Path = Path(DEFAULTS["PRICES_PATH"])
    prices: PriceTable = field(default_factory=PriceTable, repr=False)


@dataclass(frozen=True)
class ObservabilitySettings:
    """Configuración de observabilidad (fase 2); la clave de LangSmith no se guarda.

    :param service_name: Campo ``service`` del log
    :type service_name: str
    :param slo_p95_ms: Meta de latencia p95 en milisegundos
    :type slo_p95_ms: int
    :param langsmith_tracing: Si se pidieron trazas en LangSmith
    :type langsmith_tracing: bool
    :param hide_inputs: No mandar entradas a LangSmith
    :type hide_inputs: bool
    :param hide_outputs: No mandar salidas a LangSmith
    :type hide_outputs: bool
    :param tracing_enabled: Trazas pedidas y con clave presente
    :type tracing_enabled: bool
    """

    service_name: str = DEFAULTS["SERVICE_NAME"]
    slo_p95_ms: int = int(DEFAULTS["SLO_P95_MS"])
    langsmith_tracing: bool = False
    hide_inputs: bool = True
    hide_outputs: bool = True
    tracing_enabled: bool = False


@dataclass(frozen=True)
class SecuritySettings:
    """Configuración de seguridad (fase 4); las claves no aparecen en ``repr``.

    :param environment: ``development`` o ``production``
    :type environment: str
    :param api_keys: Claves por cliente
    :type api_keys: app.security.ApiKeys
    :param rate_limit_per_minute: Peticiones por cliente por minuto
    :type rate_limit_per_minute: int
    """

    environment: str = DEFAULTS["ENVIRONMENT"]
    api_keys: ApiKeys = field(default_factory=ApiKeys, repr=False)
    rate_limit_per_minute: int = int(DEFAULTS["RATE_LIMIT_PER_MINUTE"])


@dataclass(frozen=True)
class Settings:
    """Configuración inmutable de la aplicación.

    Los campos de observabilidad se leen como atributos directos (por ejemplo
    ``settings.slo_p95_ms``).

    :param model_provider: Proveedor del modelo (``fake`` o ``gateway``)
    :type model_provider: str
    :param agent_max_steps: Tope de vueltas del bucle del agente
    :type agent_max_steps: int
    :param max_question_chars: Largo máximo de la pregunta
    :type max_question_chars: int
    :param students_path: Ruta del archivo JSON de alumnos
    :type students_path: pathlib.Path
    :param observability: Configuración de log, métricas y trazas
    :type observability: ObservabilitySettings
    :param costs: Configuración del modelo real y de las palancas de costo
    :type costs: CostSettings
    :param security: Entorno, claves por cliente y límite de peticiones
    :type security: SecuritySettings
    """

    model_provider: str
    agent_max_steps: int
    max_question_chars: int
    students_path: Path
    observability: ObservabilitySettings = field(
        default_factory=ObservabilitySettings
    )
    costs: CostSettings = field(default_factory=CostSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)

    @property
    def service_name(self):
        """Campo ``service`` del log.

        :rtype: str
        """
        return self.observability.service_name

    @property
    def slo_p95_ms(self):
        """Meta de latencia p95 en milisegundos.

        :rtype: int
        """
        return self.observability.slo_p95_ms

    @property
    def langsmith_tracing(self):
        """Si se pidieron trazas en LangSmith.

        :rtype: bool
        """
        return self.observability.langsmith_tracing

    @property
    def hide_inputs(self):
        """Si se ocultan las entradas en LangSmith.

        :rtype: bool
        """
        return self.observability.hide_inputs

    @property
    def hide_outputs(self):
        """Si se ocultan las salidas en LangSmith.

        :rtype: bool
        """
        return self.observability.hide_outputs

    @property
    def tracing_enabled(self):
        """Si las trazas están encendidas (pedidas y con clave presente).

        :rtype: bool
        """
        return self.observability.tracing_enabled


def _int_at_least(env, name, minimum):
    """Lee una variable como entero mayor o igual a ``minimum``.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :param minimum: Valor mínimo permitido
    :type minimum: int
    :return: Valor entero
    :rtype: int
    :raises ValueError: Si no es entero o es menor que ``minimum``
    """
    raw = env.get(name, DEFAULTS[name])
    try:
        value = int(str(raw).strip())
    except ValueError as error:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from error
    if value < minimum:
        raise ValueError(f"{name} must be at least {minimum}, got {value}")
    return value


def _positive_int(env, name):
    """Lee una variable como entero mayor o igual a 1.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :return: Valor entero
    :rtype: int
    :raises ValueError: Si no es entero o es menor que 1
    """
    return _int_at_least(env, name, 1)


def _number(env, name, allow_zero):
    """Lee una variable como número real finito, positivo o no negativo.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :param allow_zero: Si se admite el 0
    :type allow_zero: bool
    :return: Valor real
    :rtype: float
    :raises ValueError: Si no es número finito o queda fuera del rango
    """
    raw = env.get(name, DEFAULTS[name])
    try:
        value = float(str(raw).strip())
    except ValueError as error:
        raise ValueError(f"{name} must be a number, got {raw!r}") from error
    if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
        bound = ">= 0" if allow_zero else "> 0"
        raise ValueError(f"{name} must be {bound}, got {raw!r}")
    return value


def _text(env, name, default=""):
    """Lee una variable de texto sin espacios en los extremos.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :param default: Valor si la variable no existe
    :type default: str
    :return: Texto leído
    :rtype: str
    """
    return str(env.get(name, DEFAULTS.get(name, default))).strip()


def _model_name(env, name):
    """Lee el nombre de un modelo, que no puede quedar vacío.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: ``MODEL_SMALL`` o ``MODEL_LARGE``
    :type name: str
    :return: Nombre del modelo
    :rtype: str
    :raises ValueError: Si queda vacío
    """
    value = _text(env, name)
    if not value:
        raise ValueError(f"{name} must not be empty")
    return value


def _costs(env, provider):
    """Lee la configuración de costos de la fase 3 y carga los precios.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param provider: Proveedor del modelo ya validado
    :type provider: str
    :return: Configuración de costos validada
    :rtype: CostSettings
    :raises ValueError: Si falta una variable de Cloudflare con ``gateway``, si
        algún valor es inválido o si un modelo no tiene precio
    """
    if provider == GATEWAY_PROVIDER:
        for name in REQUIRED_GATEWAY_VARIABLES:
            if not _text(env, name):
                raise ValueError(f"{name} is required with MODEL_PROVIDER=gateway")
    gateway_id = _text(env, "CF_GATEWAY_ID") or DEFAULTS["CF_GATEWAY_ID"]
    model_small = _model_name(env, "MODEL_SMALL")
    model_large = _model_name(env, "MODEL_LARGE")
    raw_prices = _text(env, "PRICES_PATH")
    if not raw_prices:
        raise ValueError("PRICES_PATH must not be empty")
    prices_path = Path(raw_prices)
    prices = PriceTable.load(prices_path)
    prices.require(model_small, model_large)
    return CostSettings(
        cf_account_id=_text(env, "CF_ACCOUNT_ID"),
        cf_gateway_id=gateway_id,
        cf_api_token=_text(env, "CF_API_TOKEN"),
        model_small=model_small,
        model_large=model_large,
        routing=_boolean(env, "ROUTING"),
        router_max_chars=_positive_int(env, "ROUTER_MAX_CHARS"),
        history_window=_int_at_least(env, "HISTORY_WINDOW", 0),
        model_max_tokens=_positive_int(env, "MODEL_MAX_TOKENS"),
        model_temperature=_number(env, "MODEL_TEMPERATURE", allow_zero=True),
        model_timeout_seconds=_number(
            env, "MODEL_TIMEOUT_SECONDS", allow_zero=False
        ),
        cache_ttl_seconds=_int_at_least(env, "CACHE_TTL_SECONDS", 0),
        prices_path=prices_path,
        prices=prices,
    )


def _boolean(env, name):
    """Lee una variable que solo admite ``true`` o ``false``.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :param name: Nombre de la variable
    :type name: str
    :return: Valor lógico
    :rtype: bool
    :raises ValueError: Si no es ``true`` ni ``false`` (sin distinguir mayúsculas)
    """
    raw = str(env.get(name, DEFAULTS[name])).strip().lower()
    if raw not in BOOLEAN_VALUES:
        raise ValueError(f"{name} must be true or false, got {raw!r}")
    return BOOLEAN_VALUES[raw]


def _service_name(env):
    """Lee el nombre del servicio para el log.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Nombre del servicio
    :rtype: str
    :raises ValueError: Si queda vacío
    """
    name = str(env.get("SERVICE_NAME", DEFAULTS["SERVICE_NAME"])).strip()
    if not name:
        raise ValueError("SERVICE_NAME must not be empty")
    return name


def _observability(env):
    """Lee la configuración de observabilidad de la fase 2.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Configuración de observabilidad validada
    :rtype: ObservabilitySettings
    :raises ValueError: Si algún valor es inválido
    """
    tracing = _boolean(env, "LANGSMITH_TRACING")
    # Solo se guarda si la clave está presente, nunca su valor.
    has_key = bool(str(env.get(API_KEY_VARIABLE, "")).strip())
    return ObservabilitySettings(
        service_name=_service_name(env),
        slo_p95_ms=_positive_int(env, "SLO_P95_MS"),
        langsmith_tracing=tracing,
        hide_inputs=_boolean(env, "HIDE_INPUTS"),
        hide_outputs=_boolean(env, "HIDE_OUTPUTS"),
        tracing_enabled=tracing and has_key,
    )


def _security(env):
    """Lee la configuración de seguridad de la fase 4.

    :param env: Variables de entorno
    :type env: collections.abc.Mapping
    :return: Configuración de seguridad validada
    :rtype: SecuritySettings
    :raises ValueError: Si ``ENVIRONMENT`` no es conocido, si el límite no es un
        entero >= 1 o si ``API_KEYS`` está mal formada (sin su valor)
    """
    environment = _text(env, "ENVIRONMENT").lower()
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError(
            f"ENVIRONMENT must be one of {SUPPORTED_ENVIRONMENTS}, "
            f"got {environment!r}"
        )
    # El valor es secreto: los errores de ``parse_api_keys`` nunca lo incluyen.
    api_keys = parse_api_keys(str(env.get("API_KEYS", DEFAULTS["API_KEYS"])))
    return SecuritySettings(
        environment=environment,
        api_keys=api_keys,
        rate_limit_per_minute=_positive_int(env, "RATE_LIMIT_PER_MINUTE"),
    )


def load_settings(env=None):
    """Arma la configuración desde el entorno y la valida.

    Con ``ENVIRONMENT=production`` aplica además las reglas de compliance.

    :param env: Variables de entorno; si es ``None`` se usa ``os.environ``
    :type env: collections.abc.Mapping or None
    :return: Configuración validada
    :rtype: Settings
    :raises ValueError: Si algún valor es inválido o si falla el compliance
    """
    env = os.environ if env is None else env
    provider = str(env.get("MODEL_PROVIDER", DEFAULTS["MODEL_PROVIDER"])).strip()
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"MODEL_PROVIDER must be one of {SUPPORTED_PROVIDERS}, got {provider!r}"
        )
    max_steps = _positive_int(env, "AGENT_MAX_STEPS")
    max_chars = _positive_int(env, "MAX_QUESTION_CHARS")
    raw_path = str(env.get("STUDENTS_PATH", DEFAULTS["STUDENTS_PATH"])).strip()
    if not raw_path:
        raise ValueError("STUDENTS_PATH must not be empty")
    students_path = Path(raw_path)
    if not students_path.parent.is_dir():
        raise ValueError(
            f"STUDENTS_PATH folder does not exist: {students_path.parent}"
        )
    settings = Settings(
        model_provider=provider,
        agent_max_steps=max_steps,
        max_question_chars=max_chars,
        students_path=students_path,
        observability=_observability(env),
        costs=_costs(env, provider),
        security=_security(env),
    )
    check_production(settings)
    return settings
