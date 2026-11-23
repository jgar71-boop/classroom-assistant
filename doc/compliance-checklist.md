# Lista de compliance del Classroom Assistant

Cada regla está en el código y se comprueba sola. Las de producción se aplican con `ENVIRONMENT=production`:
si alguna falla, `load_settings` lanza un solo `ValueError` que nombra cada regla, nunca un valor secreto, y el
producto no arranca.

| Regla | Dónde está en el código | Cómo se comprueba |
| --- | --- | --- |
| En producción `MODEL_PROVIDER` no puede ser `fake` | `app/compliance.py`, `production_violations` | Pruebas de `compliance.check_production`; `verification contract-04` |
| En producción `API_KEYS` no puede estar vacía | `app/compliance.py`, `production_violations` | Pruebas de `compliance.check_production` |
| En producción cada clave tiene 16 caracteres o más; el error da el número de entrada y su largo | `app/compliance.py`, `MIN_KEY_LENGTH` | Pruebas con una clave de 15 frente a una de 16 caracteres |
| En producción, con `LANGSMITH_TRACING=true`, `HIDE_INPUTS` y `HIDE_OUTPUTS` valen `true` | `app/compliance.py`, `production_violations` | Pruebas de cada variable en `false` |
| `ENVIRONMENT` solo admite `development` o `production`: un valor mal escrito no se salta el compliance | `app/config.py`, `_security` | `tests/test_security_config.py` |
| `API_KEYS` mal formada impide arrancar; el error da entrada y largo, nunca el valor | `app/security.py`, `parse_api_keys` | `tests/test_security.py` |
| `POST /ask`, `GET /metrics`, `POST /students`, `GET /students` y `GET /students/{id}` exigen `X-API-Key` (`401` sin clave o con una inválida) | `app/main.py`, `is_protected` y `_build_security_guard` | `tests/features/security.feature`; `verification contract-04` |
| `GET /`, `GET /health` y `/docs` no piden clave | `app/main.py`, `PROTECTED_PATHS` | Escenario «The public pages stay open without a key» |
| Las claves se comparan con `hmac.compare_digest` sobre bytes, contra todas las claves | `app/security.py`, `ApiKeys.identify` | Espía de `hmac.compare_digest` en `tests/test_security.py` |
| Más de `RATE_LIMIT_PER_MINUTE` peticiones por cliente en un minuto dan `429` con `Retry-After` | `app/security.py`, `RateLimiter`; `app/main.py` | `tests/test_security.py` con reloj manual; escenario del límite |
| La clave nunca se escribe en el log, la traza, un error ni el `repr` | `app/events.py` (solo `client`), `app/security.py`, `app/config.py` (`repr=False`) | Escenario «The key never appears in the log or in the errors» |
| El log, la auditoría y la traza llevan el nombre del cliente (`client`) | `app/events.py`, `emit`; `app/tracing.py`, `trace_context` | `tests/test_security_config.py` |
| La página guarda la clave en `sessionStorage`, nunca en otro almacenamiento ni en su código | `app/static/index.html` | `tests/test_publication.py` |
| El log nunca lleva nombres de alumnos: `student_created` solo trae `student_id`, `grade` y `classroom` | `app/events.py`, `student_created` | Pruebas de observabilidad de la fase 2; `verification contract-02` |
| El log nunca lleva el texto de la pregunta ni de la respuesta: `agent_run` trae solo largos y conteos | `app/events.py`, `agent_run` | Pruebas de observabilidad de la fase 2 |
| La auditoría de herramientas lleva solo el argumento esperado (`args` filtrados) | `app/agent.py`; `app/events.py`, `tool_call` | Pruebas del agente y de la auditoría de la fase 2 |
| Un error se registra con su tipo, nunca con su mensaje; la respuesta es un `500` genérico | `app/events.py`, `error`; `app/main.py` | Pruebas de errores de la fase 2 |
| Las trazas están apagadas por omisión y ocultan entradas y salidas (`HIDE_INPUTS` y `HIDE_OUTPUTS` en `true`) | `app/config.py`, `DEFAULTS`; `app/tracing.py` | Pruebas de trazas de la fase 2 |
| Los secretos (`CF_API_TOKEN`, `LANGSMITH_API_KEY`, `API_KEYS`) no salen en `repr`, log ni errores | `app/config.py` | Pruebas de configuración de las fases 2 a 4 |
