"""Métricas de observación de este proceso (nunca datos de alumnos)."""

import math
import os
import threading
from collections import deque

LATENCY_WINDOW = 1000
SERVER_ERROR_STATUS = 500


def _nearest_rank(sorted_values, percentile):
    """Calcula un percentil por rango más cercano.

    :param sorted_values: Valores ordenados de menor a mayor
    :type sorted_values: list[float]
    :param percentile: Percentil entre 0 y 100
    :type percentile: float
    :return: Valor del percentil; ``0.0`` sin datos
    :rtype: float
    """
    if not sorted_values:
        return 0.0
    rank = max(1, math.ceil(percentile / 100 * len(sorted_values)))
    return float(sorted_values[rank - 1])


class Metrics:
    """Contadores en memoria del proceso, protegidos con un candado.

    :param window: Cuántas latencias recientes se guardan
    :type window: int
    """

    def __init__(self, window=LATENCY_WINDOW):
        self._lock = threading.Lock()
        self._latencies = deque(maxlen=window)
        self._requests = 0
        self._errors = 0
        self._tokens = {"input": 0, "output": 0}
        self._students_created = 0
        self._cost_usd = 0.0

    def record_cost(self, cost_usd):
        """Suma el costo en USD de una corrida del agente.

        :param cost_usd: Costo de la corrida
        :type cost_usd: float
        """
        with self._lock:
            self._cost_usd += float(cost_usd)

    def record_request(self, latency_ms, status):
        """Registra una petición terminada.

        :param latency_ms: Latencia en milisegundos
        :type latency_ms: float
        :param status: Código HTTP; ``5xx`` cuenta como error
        :type status: int
        """
        with self._lock:
            self._requests += 1
            if status >= SERVER_ERROR_STATUS:
                self._errors += 1
            self._latencies.append(float(latency_ms))

    def record_tokens(self, input_tokens, output_tokens):
        """Suma los tokens de una corrida del agente.

        :param input_tokens: Tokens de entrada
        :type input_tokens: int
        :param output_tokens: Tokens de salida
        :type output_tokens: int
        """
        with self._lock:
            self._tokens["input"] += input_tokens
            self._tokens["output"] += output_tokens

    def record_student_created(self):
        """Cuenta un alumno registrado."""
        with self._lock:
            self._students_created += 1

    def snapshot(self, slo_p95_ms):
        """Arma el cuerpo de ``GET /metrics``.

        :param slo_p95_ms: Meta de latencia p95 en milisegundos
        :type slo_p95_ms: int
        :return: Peticiones, errores, latencias, tokens, altas, costo y SLO
        :rtype: dict
        """
        with self._lock:
            latencies = sorted(self._latencies)
            requests = self._requests
            errors = self._errors
            tokens = dict(self._tokens)
            created = self._students_created
            cost_usd = self._cost_usd
        p95 = _nearest_rank(latencies, 95)
        return {
            "pid": os.getpid(),
            "requests": requests,
            "error_rate": errors / requests if requests else 0.0,
            "latency_ms": {"p50": _nearest_rank(latencies, 50), "p95": p95},
            "tokens": tokens,
            "students_created": created,
            "cost_usd": cost_usd,
            "slo": {"p95_ms_target": slo_p95_ms, "met": p95 < slo_p95_ms},
        }
