"""API web del Classroom Assistant (FastAPI).

Los alumnos y las conversaciones no se guardan en memoria; solo los contadores de
observación de ``app.metrics``.
"""

import os
from pathlib import Path
from typing import Annotated, List, Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, StrictInt, StringConstraints, field_validator

from app.agent import Agent
from app.clock import SystemClock
from app.config import GATEWAY_PROVIDER, load_settings
from app.events import EventLog
from app.gateway import ModelUnavailable
from app.llm import build_model
from app.metrics import Metrics
from app.repository import StudentRepository, normalize
from app.request_context import (
    API_KEY_HEADER,
    REQUEST_ID_HEADER,
    current_client,
    current_request_id,
    resolve_request_id,
)
from app.router import choose_route
from app.security import RateLimiter
from app.tracing import trace_context

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_PAGE = STATIC_DIR / "index.html"
MILLISECONDS = 1000
INTERNAL_ERROR_STATUS = 500
INTERNAL_ERROR_DETAIL = "internal error"
MODEL_UNAVAILABLE_STATUS = 502
MODEL_UNAVAILABLE_DETAIL = "model unavailable"
UNAUTHORIZED_STATUS = 401
UNAUTHORIZED_DETAIL = "invalid or missing API key"
RATE_LIMITED_STATUS = 429
RATE_LIMITED_DETAIL = "rate limit exceeded"
RETRY_AFTER_HEADER = "Retry-After"
# Rutas que piden clave, para cualquier método. ``/``, ``/health``, ``/docs`` y
# ``/openapi.json`` quedan libres.
PROTECTED_PATHS = frozenset({"/ask", "/metrics", "/students"})
PROTECTED_PREFIX = "/students/"

NameText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]
SubjectText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)
]
GradeNumber = Annotated[StrictInt, Field(ge=1, le=12)]
ClassroomNumber = Annotated[StrictInt, Field(ge=1, le=999)]


class StudentIn(BaseModel):
    """Datos de entrada para registrar un alumno.

    :param name: Nombre, de 1 a 100 caracteres sin espacios de los extremos
    :type name: str
    :param subject: Materia, de 1 a 60 caracteres sin espacios de los extremos
    :type subject: str
    :param grade: Grado, entero de 1 a 12
    :type grade: int
    :param classroom: Número de salón, entero de 1 a 999
    :type classroom: int
    """

    name: NameText
    subject: SubjectText
    grade: GradeNumber
    classroom: ClassroomNumber


class HistoryItem(BaseModel):
    """Un mensaje previo de la conversación que manda el navegador.

    :param role: ``user`` o ``assistant``
    :type role: str
    :param content: Texto del mensaje
    :type content: str
    """

    role: Literal["user", "assistant"]
    content: str


def _build_ask_model(max_chars):
    """Crea el modelo de entrada de ``POST /ask`` con el largo máximo configurado.

    :param max_chars: Largo máximo de la pregunta
    :type max_chars: int
    :return: Clase Pydantic ``AskIn``
    :rtype: type
    """

    class AskIn(BaseModel):
        """Pregunta para el asistente.

        :param question: Pregunta no vacía de máximo ``MAX_QUESTION_CHARS``
        :type question: str
        :param history: Conversación previa, opcional
        :type history: list[HistoryItem]
        """

        question: Annotated[str, Field(max_length=max_chars)]
        history: List[HistoryItem] = Field(default_factory=list)

        @field_validator("question")
        @classmethod
        def question_not_blank(cls, value):
            """Rechaza preguntas vacías o solo con espacios.

            :param value: Pregunta recibida
            :type value: str
            :return: La misma pregunta
            :rtype: str
            :raises ValueError: Si está vacía tras quitar espacios
            """
            if not value.strip():
                raise ValueError("question must not be empty")
            return value

    return AskIn


def is_protected(path):
    """Indica si una ruta pide ``X-API-Key``.

    :param path: Ruta de la petición, sin la query
    :type path: str
    :return: ``True`` para ``/ask``, ``/metrics``, ``/students`` y
        ``/students/...``
    :rtype: bool
    """
    trimmed = path.rstrip("/") or "/"
    return trimmed in PROTECTED_PATHS or trimmed.startswith(PROTECTED_PREFIX)


def _build_security_guard(settings, rate_limiter):
    """Arma la revisión de clave y de límite que corre antes de FastAPI.

    Corre antes de validar el cuerpo, así un JSON malformado sin clave responde
    ``401`` y no ``422``. Nunca escribe la clave ni los encabezados.

    :param settings: Configuración con ``security.api_keys``
    :type settings: app.config.Settings
    :param rate_limiter: Límite de peticiones por cliente
    :type rate_limiter: app.security.RateLimiter
    :return: Función ``guard(request)`` que devuelve una respuesta de rechazo, o
        ``None`` y fija ``current_client`` si la petición puede seguir
    :rtype: collections.abc.Callable
    """
    api_keys = settings.security.api_keys

    def guard(request):
        """Revisa la clave y el límite de una petición a una ruta protegida.

        :param request: Petición entrante
        :type request: fastapi.Request
        :return: ``401`` o ``429`` si se rechaza; ``None`` si pasa
        :rtype: fastapi.responses.JSONResponse or None
        """
        if not is_protected(request.url.path):
            return None
        client = api_keys.identify(request.headers.get(API_KEY_HEADER))
        if client is None:
            return JSONResponse(
                status_code=UNAUTHORIZED_STATUS,
                content={"detail": UNAUTHORIZED_DETAIL},
            )
        # Desde aquí cada evento lleva el nombre del cliente, también un 429.
        current_client.set(client)
        retry_after = rate_limiter.check(client)
        if retry_after is not None:
            return JSONResponse(
                status_code=RATE_LIMITED_STATUS,
                content={"detail": RATE_LIMITED_DETAIL},
                headers={RETRY_AFTER_HEADER: str(retry_after)},
            )
        return None

    return guard


def _add_observability_middleware(app, clock, events, metrics, guard):
    """Agrega el middleware que da id, protege, mide, atrapa errores y registra.

    La revisión de seguridad corre dentro de este middleware, en el mismo
    contexto: así un ``401`` o un ``429`` también tienen ``request_id``, log y
    métrica, y el evento ``request`` lleva el ``client``.

    :param app: Aplicación FastAPI
    :type app: fastapi.FastAPI
    :param clock: Reloj con ``monotonic()``
    :type clock: app.clock.Clock
    :param events: Log de eventos
    :type events: app.events.EventLog
    :param metrics: Métricas del proceso
    :type metrics: app.metrics.Metrics
    :param guard: Revisión de clave y límite (ver ``_build_security_guard``)
    :type guard: collections.abc.Callable
    """

    @app.middleware("http")
    async def observe_request(request: Request, call_next):
        """Asigna el id, revisa la clave, mide la latencia y registra la petición.

        :param request: Petición entrante
        :type request: fastapi.Request
        :param call_next: Siguiente paso de la cadena
        :type call_next: collections.abc.Callable
        :return: Respuesta con el encabezado ``X-Request-ID``
        :rtype: starlette.responses.Response
        """
        started = clock.monotonic()
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = current_request_id.set(request_id)
        client_token = current_client.set(None)
        try:
            try:
                response = guard(request) or await call_next(request)
            except Exception as error:  # pylint: disable=broad-exception-caught
                # Cualquier fallo se vuelve un 500 genérico: nunca su mensaje.
                events.error(error)
                response = JSONResponse(
                    status_code=INTERNAL_ERROR_STATUS,
                    content={
                        "detail": INTERNAL_ERROR_DETAIL,
                        "request_id": request_id,
                    },
                )
            response.headers[REQUEST_ID_HEADER] = request_id
            latency_ms = (clock.monotonic() - started) * MILLISECONDS
            events.request(
                request.method, request.url.path, response.status_code, latency_ms
            )
            metrics.record_request(latency_ms, response.status_code)
            return response
        finally:
            current_client.reset(client_token)
            current_request_id.reset(token)


def _add_student_routes(app, repository, events, metrics):
    """Agrega las rutas del registro de alumnos.

    :param app: Aplicación FastAPI
    :type app: fastapi.FastAPI
    :param repository: Repositorio de alumnos
    :type repository: app.repository.StudentRepository
    :param events: Log de eventos
    :type events: app.events.EventLog
    :param metrics: Métricas del proceso
    :type metrics: app.metrics.Metrics
    """

    @app.post("/students", status_code=201)
    def register_student(student: StudentIn):
        """Registra un alumno validado y audita el alta sin el nombre.

        :param student: Datos del alumno
        :type student: StudentIn
        :return: El alumno guardado con su ``id``
        :rtype: dict
        """
        saved = repository.add(student.model_dump())
        events.student_created(saved)
        metrics.record_student_created()
        return saved

    @app.get("/students")
    def list_students(
        classroom: Optional[int] = None, subject: Optional[str] = None
    ):
        """Lista los alumnos en orden de id, con filtros opcionales.

        :param classroom: Número de salón para filtrar
        :type classroom: int or None
        :param subject: Materia para filtrar, sin mayúsculas ni tildes
        :type subject: str or None
        :return: Alumnos que cumplen los filtros
        :rtype: list[dict]
        """
        students = repository.list_all()
        if classroom is not None:
            students = [s for s in students if s.get("classroom") == classroom]
        if subject is not None:
            wanted = normalize(subject).strip()
            students = [
                s for s in students if normalize(s.get("subject", "")) == wanted
            ]
        return students

    @app.get("/students/{student_id}")
    def get_student(student_id: str):
        """Devuelve un alumno por id.

        :param student_id: Id del alumno
        :type student_id: str
        :return: El alumno
        :rtype: dict
        :raises HTTPException: ``404`` si no existe
        """
        student = repository.get(student_id)
        if student is None:
            raise HTTPException(status_code=404, detail="Student not found")
        return student


def _build_agents(settings, model, repository, events, http_client):
    """Arma un agente por nombre de modelo (``MODEL_SMALL`` y ``MODEL_LARGE``).

    :param settings: Configuración de la aplicación
    :type settings: app.config.Settings
    :param model: Modelo inyectado para los dos nombres, o ``None``
    :type model: app.llm.LanguageModel or None
    :param repository: Repositorio de alumnos
    :type repository: app.repository.StudentRepository
    :param events: Log de eventos
    :type events: app.events.EventLog
    :param http_client: Cliente HTTP para ``gateway``, o ``None``
    :type http_client: httpx.Client or None
    :return: Agentes por nombre de modelo
    :rtype: dict[str, app.agent.Agent]
    """
    costs = settings.costs
    if (
        model is None
        and settings.model_provider == GATEWAY_PROVIDER
        and http_client is None
    ):
        # Solo con el modelo real se crea un cliente HTTP.
        http_client = httpx.Client()
    agents = {}
    for name in (costs.model_small, costs.model_large):
        agents[name] = Agent(
            model or build_model(settings, repository, name, http_client),
            repository,
            settings.agent_max_steps,
            on_tool_call=events.tool_call,
            model_name=name,
            prices=costs.prices,
            history_window=costs.history_window,
        )
    return agents


def create_app(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    settings=None,
    model=None,
    repository=None,
    clock=None,
    events=None,
    metrics=None,
    http_client=None,
    rate_limiter=None,
):
    """Crea la aplicación con sus dependencias inyectadas.

    :param settings: Configuración; si es ``None`` se lee del entorno
    :type settings: app.config.Settings or None
    :param model: Modelo de lenguaje para los dos nombres; si es ``None`` se arma
        uno por nombre desde la configuración
    :type model: app.llm.LanguageModel or None
    :param repository: Repositorio de alumnos; si es ``None`` se arma sobre
        ``STUDENTS_PATH``
    :type repository: app.repository.StudentRepository or None
    :param clock: Reloj; si es ``None`` se usa el del sistema
    :type clock: app.clock.Clock or None
    :param events: Log de eventos; si es ``None`` escribe en la salida estándar
    :type events: app.events.EventLog or None
    :param metrics: Métricas del proceso; si es ``None`` se crean vacías
    :type metrics: app.metrics.Metrics or None
    :param http_client: Cliente HTTP del modelo real; si es ``None`` y el
        proveedor es ``gateway`` se crea uno
    :type http_client: httpx.Client or None
    :param rate_limiter: Límite de peticiones; si es ``None`` se crea uno con
        ``RATE_LIMIT_PER_MINUTE`` sobre el reloj de la aplicación
    :type rate_limiter: app.security.RateLimiter or None
    :return: Aplicación FastAPI
    :rtype: fastapi.FastAPI
    :raises ValueError: Si la configuración es inválida
    """
    settings = settings or load_settings()
    repository = repository or StudentRepository(settings.students_path)
    clock = clock or SystemClock()
    events = events or EventLog(settings.service_name, clock)
    metrics = metrics or Metrics()
    rate_limiter = rate_limiter or RateLimiter(
        settings.security.rate_limit_per_minute, clock
    )
    agents = _build_agents(settings, model, repository, events, http_client)
    ask_model = _build_ask_model(settings.max_question_chars)

    app = FastAPI(title="Classroom Assistant")
    _add_observability_middleware(
        app, clock, events, metrics, _build_security_guard(settings, rate_limiter)
    )

    @app.get("/", include_in_schema=False)
    def home_page():
        """Sirve la página web.

        :return: El archivo ``index.html``
        :rtype: fastapi.responses.FileResponse
        """
        return FileResponse(INDEX_PAGE, media_type="text/html")

    @app.get("/health")
    def health():
        """Indica que el servicio responde.

        :return: Estado y id del proceso
        :rtype: dict
        """
        return {"status": "ok", "pid": os.getpid()}

    @app.get("/metrics")
    def read_metrics():
        """Devuelve las métricas de este proceso.

        :return: Peticiones, errores, latencias, tokens, altas y SLO
        :rtype: dict
        """
        return metrics.snapshot(settings.slo_p95_ms)

    _add_student_routes(app, repository, events, metrics)

    @app.post("/ask")
    def ask(payload: ask_model):
        """Responde una pregunta con el agente; no guarda el historial.

        :param payload: Pregunta e historial
        :type payload: AskIn
        :return: Respuesta, vueltas, herramientas, tokens, modelo, ruta, costo e
            id de la petición; ``502`` si el modelo no está disponible
        :rtype: dict or fastapi.responses.JSONResponse
        """
        request_id = current_request_id.get()
        history = [item.model_dump() for item in payload.history]
        decision = choose_route(payload.question, settings.costs)
        try:
            with trace_context(
                settings,
                request_id,
                decision.model,
                decision.reason,
                client=current_client.get(),
            ):
                result = agents[decision.model].run(payload.question, history)
        except ModelUnavailable as error:
            events.error(error)
            return JSONResponse(
                status_code=MODEL_UNAVAILABLE_STATUS,
                content={
                    "detail": MODEL_UNAVAILABLE_DETAIL,
                    "request_id": request_id,
                },
            )
        events.agent_run(len(payload.question), len(history), result, decision.reason)
        metrics.record_tokens(result.input_tokens, result.output_tokens)
        metrics.record_cost(result.cost_usd)
        return {
            "answer": result.answer,
            "steps": result.steps,
            "tools_used": result.tools_used,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "request_id": request_id,
            "model": decision.model,
            "route": decision.reason,
            "cached_calls": result.cached_calls,
            "cost_usd": result.cost_usd,
        }

    return app


app = create_app()
