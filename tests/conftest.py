"""Fixtures y pasos compartidos de las pruebas del Classroom Assistant.

Toda prueba trabaja sobre archivos en ``tmp_path``: nunca se lee ni se escribe
``product/data/``, que es la base de datos real y cambia con el uso. Los alumnos y
los precios de prueba se definen aquí.
"""

import io
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pytest_bdd import given, parsers, then, when

from app.config import load_settings
from app.llm import FakeModel
from app.main import create_app
from app.repository import StudentRepository


def _student(number, name, subject, grade, classroom):
    """Arma un alumno de prueba con su id ``STU-000n``."""
    return {
        "id": f"STU-{number:04d}",
        "name": name,
        "subject": subject,
        "grade": grade,
        "classroom": classroom,
    }


SAMPLE_STUDENTS = [
    _student(1, "Valeria Torres", "Matemáticas", 3, 101),
    _student(2, "Diego Hernández", "Matemáticas", 3, 101),
    _student(3, "Camila Ramírez", "Historia", 5, 204),
    _student(4, "Mateo Sánchez", "Ciencias", 4, 110),
    _student(5, "Lucía Morales", "Inglés", 6, 305),
    _student(6, "Santiago Castro", "Historia", 5, 204),
    _student(7, "Regina Flores", "Ciencias", 4, 110),
    _student(8, "Emiliano Vargas", "Matemáticas", 2, 101),
    _student(9, "Ximena Ortiz", "Inglés", 6, 305),
    _student(10, "Sebastián Reyes", "Arte", 1, 112),
]

# Clientes y claves de prueba (fase 4). Las claves tienen 16 caracteres o más,
# como exige el compliance de producción. No son claves reales.
TEST_CLIENT = "teacher"
TEST_API_KEY = "teacher-key-0123456789"
OFFICE_CLIENT = "office"
OFFICE_API_KEY = "office-key-9876543210"
WRONG_API_KEY = "wrong-key-0000000000"
TEST_API_KEYS = f"{TEST_CLIENT}:{TEST_API_KEY},{OFFICE_CLIENT}:{OFFICE_API_KEY}"
API_KEY_HEADER = "X-API-Key"
# Límite alto por omisión: las pruebas de las fases 1 a 3 no deben toparse con él.
TEST_RATE_LIMIT = "1000"


def read_env_file(path):
    """Variables y valores de un archivo ``.env``, sin comentarios ni líneas vacías.

    :param path: Ruta del archivo, por ejemplo ``.env.example``
    :type path: pathlib.Path
    :return: Nombre de cada variable con su valor
    :rtype: dict[str, str]
    """
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            name, _, value = line.partition("=")
            values[name.strip()] = value.strip()
    return values


def security_env(path, prices_path, env):
    """Variables de prueba con clave y límite por omisión, que ``env`` puede cambiar.

    :param path: Archivo temporal de alumnos
    :type path: pathlib.Path
    :param prices_path: Archivo temporal de precios
    :type prices_path: pathlib.Path
    :param env: Variables propias de la prueba
    :type env: dict
    :return: Variables completas para ``load_settings``
    :rtype: dict
    """
    variables = {
        "STUDENTS_PATH": str(path),
        "PRICES_PATH": str(prices_path),
        "API_KEYS": TEST_API_KEYS,
        "RATE_LIMIT_PER_MINUTE": TEST_RATE_LIMIT,
    }
    variables.update({key: str(value) for key, value in env.items()})
    return variables


def key_headers(api_key):
    """Encabezados por omisión del ``TestClient``: con clave o sin ella.

    :param api_key: Clave a mandar en ``X-API-Key``, o ``None``
    :type api_key: str or None
    :return: Encabezados
    :rtype: dict
    """
    return {API_KEY_HEADER: api_key} if api_key else {}


MODEL_SMALL = "@cf/meta/llama-3.1-8b-instruct-fast"
MODEL_LARGE = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
TEST_PRICES = {
    "currency": "USD",
    "unit": "per million tokens",
    "models": {
        "fake": {"input": 0.0, "output": 0.0},
        MODEL_SMALL: {"input": 0.045, "output": 0.384},
        MODEL_LARGE: {"input": 0.293, "output": 2.253},
    },
}


def write_prices(path, prices=None):
    """Escribe un archivo de precios por millón de tokens.

    :param path: Ruta del archivo a escribir
    :type path: pathlib.Path
    :param prices: Contenido; por omisión ``TEST_PRICES``
    :type prices: dict or None
    :return: La misma ruta
    :rtype: pathlib.Path
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(prices or TEST_PRICES), encoding="utf-8")
    return path


def expected_cost(model, input_tokens, output_tokens):
    """Costo esperado en USD según ``TEST_PRICES``.

    :param model: Nombre del modelo
    :type model: str
    :param input_tokens: Tokens de entrada
    :type input_tokens: int
    :param output_tokens: Tokens de salida
    :type output_tokens: int
    :return: Costo en USD
    :rtype: float
    """
    price = TEST_PRICES["models"][model]
    return (input_tokens * price["input"] + output_tokens * price["output"]) / 1e6


@pytest.fixture
def prices_path(tmp_path):
    """Archivo temporal de precios con los dos modelos de prueba.

    :param tmp_path: Carpeta temporal de pytest
    :type tmp_path: pathlib.Path
    :return: Ruta del archivo de precios
    :rtype: pathlib.Path
    """
    return write_prices(tmp_path / "config" / "model_prices.json")


@pytest.fixture
def students_path(tmp_path):
    """Ruta temporal del archivo de alumnos, todavía sin crear.

    :param tmp_path: Carpeta temporal de pytest
    :type tmp_path: pathlib.Path
    :return: Ruta del archivo de alumnos
    :rtype: pathlib.Path
    """
    return tmp_path / "students.json"


@pytest.fixture
def sample_path(students_path):
    """Archivo temporal con los diez alumnos de prueba de ``SAMPLE_STUDENTS``.

    :param students_path: Ruta temporal del archivo de alumnos
    :type students_path: pathlib.Path
    :return: Ruta del archivo ya escrito
    :rtype: pathlib.Path
    """
    students_path.write_text(
        json.dumps(SAMPLE_STUDENTS, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return students_path


@pytest.fixture
def make_client(prices_path):
    """Fabrica clientes de prueba con configuración, modelo y repositorio inyectados.

    :param prices_path: Archivo temporal de precios
    :type prices_path: pathlib.Path
    :return: Función ``build(path, api_key=TEST_API_KEY, **env)`` que devuelve un
        ``TestClient`` que manda ``X-API-Key`` por omisión (``api_key=None``: sin
        clave)
    :rtype: collections.abc.Callable
    """

    def build(path, api_key=TEST_API_KEY, **env):
        settings = load_settings(security_env(path, prices_path, env))
        repository = StudentRepository(settings.students_path)
        model = FakeModel(repository)
        app = create_app(settings=settings, model=model, repository=repository)
        return TestClient(app, headers=key_headers(api_key))

    return build


FIXED_NOW = datetime(2026, 1, 15, 10, 30, tzinfo=timezone.utc)


class FakeClock:
    """Reloj de prueba: hora fija y ``monotonic`` que avanza un paso por llamada.

    :param step_seconds: Segundos que avanza ``monotonic`` en cada llamada
    :type step_seconds: float
    """

    def __init__(self, step_seconds=0.001):
        self.step_seconds = step_seconds
        self._elapsed = 0.0

    def now(self):
        """Devuelve siempre la misma hora en UTC.

        :return: Hora fija con zona UTC
        :rtype: datetime.datetime
        """
        return FIXED_NOW

    def monotonic(self):
        """Avanza el reloj un paso y devuelve los segundos acumulados.

        :return: Segundos desde el inicio del reloj
        :rtype: float
        """
        self._elapsed += self.step_seconds
        return self._elapsed


def read_log(stream):
    """Interpreta cada línea del log como un objeto JSON.

    :param stream: Salida donde escribió el ``EventLog``
    :type stream: io.StringIO
    :return: Eventos en el orden en que se escribieron
    :rtype: list[dict]
    """
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


@pytest.fixture
def log_stream():
    """Salida en memoria para el log de eventos.

    :return: Flujo de texto vacío
    :rtype: io.StringIO
    """
    return io.StringIO()


@pytest.fixture
def make_observed_client(log_stream, prices_path):
    """Fabrica clientes con reloj falso, log en memoria y métricas propias.

    :param log_stream: Salida en memoria del log
    :type log_stream: io.StringIO
    :param prices_path: Archivo temporal de precios
    :type prices_path: pathlib.Path
    :return: Función ``build(path, repository=None, clock=None, model=None,
        rate_limiter=None, api_key=TEST_API_KEY, **env)``
    :rtype: collections.abc.Callable
    """
    # Importación tardía: así las pruebas de la fase 1 no dependen de estos módulos.
    from app.events import EventLog  # pylint: disable=import-outside-toplevel
    from app.metrics import Metrics  # pylint: disable=import-outside-toplevel

    def build(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        path,
        repository=None,
        clock=None,
        model=None,
        rate_limiter=None,
        api_key=TEST_API_KEY,
        **env,
    ):
        settings = load_settings(security_env(path, prices_path, env))
        clock = clock or FakeClock()
        repository = repository or StudentRepository(settings.students_path)
        events = EventLog(settings.service_name, clock, stream=log_stream)
        extra = {} if rate_limiter is None else {"rate_limiter": rate_limiter}
        app = create_app(
            settings=settings,
            model=model or FakeModel(repository),
            repository=repository,
            clock=clock,
            events=events,
            metrics=Metrics(),
            **extra,
        )
        return TestClient(
            app, headers=key_headers(api_key), raise_server_exceptions=False
        )

    return build


class ManualClock:
    """Reloj de prueba que solo avanza cuando la prueba lo pide.

    Sirve para el límite de peticiones: ``monotonic`` no cambia entre llamadas.
    """

    def __init__(self):
        self._elapsed = 0.0

    def now(self):
        """Devuelve siempre la misma hora en UTC.

        :return: Hora fija con zona UTC
        :rtype: datetime.datetime
        """
        return FIXED_NOW

    def monotonic(self):
        """Devuelve los segundos acumulados sin avanzar.

        :return: Segundos desde el inicio del reloj
        :rtype: float
        """
        return self._elapsed

    def advance(self, seconds):
        """Avanza el reloj ``seconds`` segundos.

        :param seconds: Segundos a avanzar
        :type seconds: float
        """
        self._elapsed += seconds


@pytest.fixture
def manual_clock():
    """Reloj manual que empieza en 0 segundos.

    :return: Reloj de prueba
    :rtype: ManualClock
    """
    return ManualClock()


@given("the registry has the ten sample students", target_fixture="client")
def registry_with_samples(sample_path, make_client):
    """Cliente sobre el archivo con los alumnos de ejemplo."""
    return make_client(sample_path)


@given(
    parsers.parse(
        'I register "{name}" studying "{subject}" in grade {grade:d} '
        "and classroom {classroom:d}"
    ),
    target_fixture="response",
)
@when(
    parsers.parse(
        'I register "{name}" studying "{subject}" in grade {grade:d} '
        "and classroom {classroom:d}"
    ),
    target_fixture="response",
)
def register_student(client, name, subject, grade, classroom):
    """Registra un alumno por la API y devuelve la respuesta."""
    payload = {
        "name": name,
        "subject": subject,
        "grade": grade,
        "classroom": classroom,
    }
    return client.post("/students", json=payload)


@then(parsers.parse("the response status is {status:d}"))
def response_status_is(response, status):
    """Comprueba el código HTTP de la última respuesta."""
    assert response.status_code == status, response.text
