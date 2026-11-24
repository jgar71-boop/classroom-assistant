# 0002. Un solo agente de solo lectura con bucle con tope

Estado: propuesto; modificado por el [ADR 0008](0008-rule-based-routing.md) (una instancia por modelo)

## Contexto

El asistente responde preguntas sobre los alumnos. Un modelo puede pedir herramientas sin fin, devolver JSON
inválido o intentar cambiar datos. El alta debe pasar siempre por la validación de `POST /students`.

## Decisión

- Una sola clase `Agent` con tres herramientas que solo llaman a métodos de lectura del repositorio:
  `get_student`, `search_by_classroom` y `search_by_subject`. El agente no expone ni recibe `add`.
  Desde el ADR 0008, `create_app` arma una instancia de esa clase por modelo (`MODEL_SMALL` y
  `MODEL_LARGE`, en `_build_agents`); todas tienen las mismas herramientas y el mismo tope.
- Protocolo de un único objeto JSON por vuelta: `{"tool", "args"}` o `{"answer"}`. El resultado se agrega
  como mensaje `user` que empieza con `Resultado de la herramienta: `.
- El bucle corre como máximo `AGENT_MAX_STEPS` vueltas; al agotarlo responde exactamente
  `No pude completar la respuesta. Intenta con una pregunta más concreta.`
- JSON mal formado, herramienta desconocida o argumentos inválidos se devuelven al modelo como resultado de
  error; el agente no lanza excepciones hacia la API.

## Consecuencias

- El costo y la latencia por pregunta quedan acotados y son predecibles.
- El asistente no puede corromper el registro aunque el modelo se equivoque, sea cual sea el modelo elegido.
- Preguntas que necesitan más vueltas que el tope reciben el mensaje fijo; el tope se ajusta por entorno.
