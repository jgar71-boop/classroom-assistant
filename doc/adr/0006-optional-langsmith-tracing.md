# 0006. Trazas opcionales en LangSmith, privadas por omisión

Estado: propuesto

## Contexto

Se quiere ver cada corrida del agente, cada llamada al modelo y cada herramienta como trazas, ligadas al
`request_id`. Sin clave el producto debe funcionar igual y no intentar conectarse; las preguntas y respuestas
no deben salir del servidor salvo que alguien lo decida.

## Decisión

- `tracing.py` concentra el uso de `langsmith`: `traceable(...)` decora `Agent.run`, la llamada al modelo y
  las herramientas; `trace_context(settings, request_id)` abre `tracing_context` con
  `metadata={"request_id": ...}`.
- Las trazas se encienden solo si `LANGSMITH_TRACING=true` **y** existe `LANGSMITH_API_KEY`; si no,
  `enabled=False` y no se crea ningún `Client`.
- `HIDE_INPUTS`/`HIDE_OUTPUTS` valen `true` por omisión y se pasan al `Client` como funciones que devuelven `{}`.
- La clave solo la lee `langsmith` del entorno: no se guarda en `Settings`, ni se registra, ni aparece en el código.

## Consecuencias

- Las pruebas corren sin red y comprueban que, apagado, no se crea el cliente.
- Con los valores por omisión las trazas muestran estructura, tiempos y metadatos, no el contenido.
- Cambiar de proveedor de trazas toca solo `tracing.py`.
