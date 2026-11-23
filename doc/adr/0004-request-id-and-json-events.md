# 0004. Id por petición y eventos JSON con campos fijos

Estado: propuesto

## Contexto

Hay que poder responder con datos qué pasó con cualquier petición, sin que el log guarde el nombre de un
alumno ni el texto de las preguntas y respuestas. Las pruebas deben ser deterministas, así que la hora no
puede salir de `datetime.now()` directo.

## Decisión

- Un middleware HTTP en `main.py` envuelve toda petición: resuelve el id (`X-Request-ID` si cumple
  `^[A-Za-z0-9._-]{1,128}$`, si no un `uuid4`), lo fija en una `ContextVar`, mide la latencia, atrapa
  cualquier excepción (evento `error` con solo `type(exc).__name__` y `500` con
  `{"detail": "internal error", "request_id"}`), pone el encabezado y emite el evento `request`.
- `EventLog` escribe una línea JSON por evento en la salida estándar, con métodos de campos fijos
  (`request`, `agent_run`, `tool_call`, `student_created`, `error`): no existe un método que acepte texto libre.
- La hora y la latencia vienen de un `Clock` inyectado en `create_app`; `SystemClock` es la única llamada real.

## Consecuencias

- Agente y herramientas leen el id de la `ContextVar` sin cambiar sus firmas.
- Agregar un campo nuevo al log exige tocar `EventLog`, lo que obliga a revisar si es un dato personal.
- Los mensajes de error no se registran: para depurar hay que reproducir con el `request_id` y las trazas.
