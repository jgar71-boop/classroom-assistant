"""Claves por cliente y límite de peticiones por cliente (fase 4).

Ninguna función de este módulo escribe una clave: los errores dicen el número de
entrada y su largo, y ``ApiKeys`` no muestra las claves en ``repr``.
"""

import hmac
import math
import threading
from collections import deque
from dataclasses import dataclass, field

API_KEYS_VARIABLE = "API_KEYS"
ENTRY_SEPARATOR = ","
CLIENT_SEPARATOR = ":"
WINDOW_SECONDS = 60
MIN_RETRY_AFTER = 1


def _malformed(number, entry):
    """Arma el error de una entrada mal formada, con su número y su largo.

    :param number: Número de la entrada, desde 1
    :type number: int
    :param entry: Texto de la entrada (no se incluye en el mensaje)
    :type entry: str
    :return: Error sin el valor de la entrada
    :rtype: ValueError
    """
    return ValueError(
        f"{API_KEYS_VARIABLE} entry {number} is malformed (length {len(entry)})"
    )


@dataclass(frozen=True)
class ApiKeys:
    """Claves por cliente, inmutables y sin las claves en ``repr``.

    Se arma con ``parse_api_keys``; las claves se guardan como bytes UTF-8.

    :param entries: Pares ``(cliente, clave en bytes)`` ya validados
    :type entries: tuple[tuple[str, bytes], ...]
    """

    entries: tuple = field(default=(), repr=False)

    def __len__(self):
        """Cantidad de clientes.

        :rtype: int
        """
        return len(self.entries)

    @property
    def clients(self):
        """Nombres de los clientes, en el orden de ``API_KEYS``.

        :rtype: tuple[str, ...]
        """
        return tuple(client for client, _ in self.entries)

    def key_lengths(self):
        """Largo de cada clave, en el orden de ``API_KEYS``; nunca su valor.

        :return: Largos en caracteres
        :rtype: tuple[int, ...]
        """
        return tuple(len(key.decode("utf-8")) for _, key in self.entries)

    def identify(self, presented):
        """Devuelve el cliente dueño de la clave presentada, o ``None``.

        Compara con ``hmac.compare_digest`` sobre bytes UTF-8 contra todas las
        claves, sin cortar en la primera que coincide, para no filtrar tiempos.

        :param presented: Valor del encabezado ``X-API-Key``, o ``None``
        :type presented: str or None
        :return: Nombre del cliente, o ``None`` si no hay coincidencia
        :rtype: str or None
        """
        if not presented or not isinstance(presented, str):
            return None
        candidate = presented.encode("utf-8")
        found = None
        for client, key in self.entries:
            if hmac.compare_digest(candidate, key) and found is None:
                found = client
        return found


def parse_api_keys(raw):
    """Lee ``API_KEYS`` con la forma ``cliente:clave,cliente2:clave2``.

    Cada entrada se corta en el primer ``:`` y se le quitan los espacios. Un
    texto vacío da un ``ApiKeys`` sin clientes.

    :param raw: Valor de ``API_KEYS``
    :type raw: str or None
    :return: Claves por cliente
    :rtype: ApiKeys
    :raises ValueError: Si una entrada está vacía, no tiene ``:``, tiene cliente o
        clave vacíos o repite un cliente; el mensaje da el número de entrada y su
        largo, nunca su valor
    """
    text = (raw or "").strip()
    if not text:
        return ApiKeys()
    entries = []
    seen = set()
    for number, entry in enumerate(text.split(ENTRY_SEPARATOR), start=1):
        client, separator, key = entry.partition(CLIENT_SEPARATOR)
        client, key = client.strip(), key.strip()
        if not separator or not client or not key or client in seen:
            raise _malformed(number, entry)
        seen.add(client)
        entries.append((client, key.encode("utf-8")))
    return ApiKeys(tuple(entries))


class RateLimiter:
    """Límite de peticiones por cliente en una ventana deslizante de 60 segundos.

    Una petición rechazada no ocupa lugar, y cada cliente guarda como mucho
    ``limit_per_minute`` marcas de tiempo.

    :param limit_per_minute: Peticiones permitidas por cliente por minuto
    :type limit_per_minute: int
    :param clock: Reloj con ``monotonic()``
    :type clock: app.clock.Clock
    :raises ValueError: Si el límite es menor que 1
    """

    def __init__(self, limit_per_minute, clock):
        if limit_per_minute < 1:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be at least 1")
        self._limit = limit_per_minute
        self._clock = clock
        self._windows = {}
        self._lock = threading.Lock()

    def check(self, client):
        """Cuenta una petición del cliente si cabe en su ventana.

        :param client: Nombre del cliente autenticado
        :type client: str
        :return: ``None`` si pasa, o los segundos de ``Retry-After`` (mínimo 1)
        :rtype: int or None
        """
        with self._lock:
            now = self._clock.monotonic()
            window = self._windows.setdefault(client, deque(maxlen=self._limit))
            while window and window[0] + WINDOW_SECONDS <= now:
                window.popleft()
            if len(window) < self._limit:
                window.append(now)
                return None
            wait = math.ceil(window[0] + WINDOW_SECONDS - now)
            return max(MIN_RETRY_AFTER, wait)
