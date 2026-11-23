"""Log de eventos en JSON, una línea por evento, en la salida estándar."""

import json
import sys
import threading

from app.request_context import current_client, current_request_id


class EventLog:
    """Escribe eventos JSON con ``ts``, ``service``, ``event``, ``request_id`` y
    ``client``.

    Los métodos con nombre de evento tienen campos fijos, para que nadie pueda
    mandar al log el texto de una pregunta o el nombre de un alumno.

    :param service: Valor del campo ``service``
    :type service: str
    :param clock: Reloj con ``now()``
    :type clock: app.clock.Clock
    :param stream: Salida de texto; por omisión la salida estándar
    :type stream: typing.TextIO or None
    """

    def __init__(self, service, clock, stream=None):
        self._service = service
        self._clock = clock
        self._stream = stream if stream is not None else sys.stdout
        self._lock = threading.Lock()

    def emit(self, event, **fields):
        """Escribe un evento como una sola línea JSON.

        :param event: Nombre del evento
        :type event: str
        :param fields: Campos propios del evento
        :type fields: dict
        """
        record = {
            "ts": self._clock.now().isoformat(),
            "service": self._service,
            "event": event,
            "request_id": current_request_id.get(),
            # Solo el nombre del cliente: la clave nunca llega al log.
            "client": current_client.get(),
        }
        record.update(fields)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()

    def request(self, method, path, status, latency_ms):
        """Registra el fin de una petición HTTP.

        :param method: Método HTTP
        :type method: str
        :param path: Ruta sin la query
        :type path: str
        :param status: Código HTTP de la respuesta
        :type status: int
        :param latency_ms: Latencia en milisegundos
        :type latency_ms: float
        """
        self.emit(
            "request",
            method=method,
            path=path,
            status=status,
            latency_ms=round(latency_ms, 3),
        )

    def agent_run(self, question_chars, history_messages, result, route=None):
        """Registra una corrida del agente, sin el texto de pregunta ni respuesta.

        :param question_chars: Largo de la pregunta
        :type question_chars: int
        :param history_messages: Mensajes previos recibidos
        :type history_messages: int
        :param result: Resultado del agente
        :type result: app.agent.AgentResult
        :param route: Motivo del enrutador
        :type route: str or None
        """
        self.emit(
            "agent_run",
            question_chars=question_chars,
            history_messages=history_messages,
            steps=result.steps,
            tools=list(result.tools_used),
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            stopped=result.stopped,
            model=getattr(result, "model", None),
            route=route,
            cost_usd=getattr(result, "cost_usd", 0.0),
        )

    def tool_call(self, tool, args):
        """Registra la auditoría de una herramienta llamada por el agente.

        :param tool: Nombre de la herramienta
        :type tool: str
        :param args: Argumento esperado de la herramienta, ya filtrado
        :type args: dict
        """
        self.emit("audit", action="tool_call", tool=tool, args=dict(args))

    def student_created(self, student):
        """Registra la auditoría de un alta, sin el nombre del alumno.

        :param student: Alumno guardado
        :type student: dict
        """
        self.emit(
            "audit",
            action="student_created",
            student_id=student.get("id"),
            grade=student.get("grade"),
            classroom=student.get("classroom"),
        )

    def error(self, error):
        """Registra un error con su tipo, nunca con su mensaje.

        :param error: Excepción atrapada
        :type error: BaseException
        """
        self.emit("error", error_type=type(error).__name__)
