# 0008. Enrutamiento por regla en código, un agente por modelo

Estado: propuesto

## Contexto

La palanca de mayor ahorro es mandar las preguntas simples al modelo barato. Usar otro modelo para decidir
costaría tokens y no sería repetible; el motivo de cada decisión debe poder auditarse.

## Decisión

- `router.py` expone `choose_route(question, costs) -> RouteDecision(model, reason)` con reglas en orden:
  `routing_disabled`, `long_question` (más de `ROUTER_MAX_CHARS`), `keyword:<palabra>` y `short_question`.
- Las palabras se buscan sobre `normalize(question)` (sin mayúsculas ni tildes) al inicio de una palabra,
  para aceptar «resumen» o «explícame» y no activar «todos» con «métodos». El motivo usa la palabra original.
- `create_app` arma un `Agent` por nombre de modelo; la ruta elige el agente. `Agent` conserva su firma
  posicional y recibe `model_name`, `prices` e `history_window` como argumentos con nombre.

## Consecuencias

- La decisión es determinista y barata, y `route` va en la respuesta, el log y la traza.
- Una regla simple se equivoca a veces; `evaluate` y las pruebas con el modelo real dicen si conviene.
- Cambiar las palabras o el umbral es cambiar una constante y su prueba.
