"""Prueba de humo del Classroom Assistant publicado.

Uso: ``SMOKE_API_KEY=<clave> python scripts/smoke.py https://<servicio>.onrender.com``

La clave se lee solo de la variable ``SMOKE_API_KEY``, nunca de un argumento,
porque quedaría en el historial de la terminal. La clave nunca se imprime.
La prueba no registra alumnos: solo comprueba que registrar sin clave se
rechaza, así no ensucia los datos reales.
"""

import os
import sys

import httpx

KEY_VARIABLE = "SMOKE_API_KEY"
KEY_HEADER = "X-API-Key"
# Render despierta un servicio dormido en hasta un minuto
TIMEOUT_SECONDS = 90
QUESTION = {"question": "¿Quién es STU-0003?"}
# Alumno válido: así el 401 solo puede venir de la falta de clave
STUDENT = {"name": "Prueba de humo", "subject": "Arte", "grade": 1, "classroom": 1}


def status_of(client: httpx.Client, method: str, path: str, **options) -> int | None:
    """Hace una petición y devuelve su código, o ``None`` si no hubo respuesta.

    :param client: Cliente con la URL base del servicio
    :type client: httpx.Client
    :param method: Método HTTP
    :type method: str
    :param path: Ruta del servicio
    :type path: str
    :return: Código HTTP de la respuesta, o ``None`` ante un error de red
    :rtype: int | None
    """
    try:
        return client.request(method, path, **options).status_code
    except httpx.HTTPError:
        return None


def run_checks(client: httpx.Client, key: str) -> bool:
    """Corre las cuatro comprobaciones e imprime ``[OK]`` o ``[FAIL]`` en cada una.

    :param client: Cliente con la URL base del servicio
    :type client: httpx.Client
    :param key: Clave de la API; se manda en el encabezado y nunca se imprime
    :type key: str
    :return: ``True`` si las cuatro pasan
    :rtype: bool
    """
    checks = [
        ("GET /health", 200, ("GET", "/health", {})),
        ("POST /ask sin clave", 401, ("POST", "/ask", {"json": QUESTION})),
        (
            "POST /ask con clave",
            200,
            ("POST", "/ask", {"json": QUESTION, "headers": {KEY_HEADER: key}}),
        ),
        ("POST /students sin clave", 401, ("POST", "/students", {"json": STUDENT})),
    ]
    passed = True
    for name, expected, (method, path, options) in checks:
        status = status_of(client, method, path, **options)
        mark = "OK" if status == expected else "FAIL"
        passed = passed and status == expected
        received = "sin respuesta" if status is None else status
        print(f"[{mark}] {name} -> {received} (esperado {expected})")
    return passed


def main(argv: list[str], transport: httpx.BaseTransport | None = None) -> int:
    """Corre la prueba de humo contra la URL de ``argv``.

    :param argv: Lista con un solo elemento, la URL del servicio
    :type argv: list[str]
    :param transport: Transporte de ``httpx``; las pruebas pasan uno simulado
    :type transport: httpx.BaseTransport | None
    :return: 0 si todo pasa, 1 si algo falla, 2 si falta la URL o la clave
    :rtype: int
    """
    key = os.environ.get(KEY_VARIABLE, "")
    if len(argv) != 1 or not key:
        print(f"[FAIL] Uso: {KEY_VARIABLE}=<clave> python scripts/smoke.py <url>")
        return 2
    base_url = argv[0].rstrip("/")
    with httpx.Client(
        base_url=base_url, timeout=TIMEOUT_SECONDS, transport=transport
    ) as client:
        passed = run_checks(client, key)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
