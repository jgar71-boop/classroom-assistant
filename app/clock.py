"""Reloj inyectable: único lugar del producto que lee la hora del sistema."""

import time
from datetime import datetime, timezone
from typing import Protocol


class Clock(Protocol):
    """Interfaz de cualquier reloj que use el producto."""

    def now(self):
        """Devuelve la hora actual.

        :return: Hora con zona UTC
        :rtype: datetime.datetime
        """

    def monotonic(self):
        """Devuelve segundos de un reloj que nunca retrocede.

        :return: Segundos desde un origen arbitrario
        :rtype: float
        """


class SystemClock:
    """Reloj real del sistema."""

    def now(self):
        """Devuelve la hora actual del sistema en UTC.

        :return: Hora con zona UTC
        :rtype: datetime.datetime
        """
        return datetime.now(timezone.utc)

    def monotonic(self):
        """Devuelve segundos del contador de alta resolución del sistema.

        :return: Segundos desde un origen arbitrario
        :rtype: float
        """
        return time.perf_counter()
