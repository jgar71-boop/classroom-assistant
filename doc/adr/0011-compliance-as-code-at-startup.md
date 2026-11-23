# 0011. Compliance como código: el producto no arranca si incumple

Estado: propuesto

## Contexto

Una configuración insegura en producción expondría datos de alumnos o respuestas inventadas. Por ejemplo: el
modelo simulado, claves cortas o vacías, o trazas que mandan entradas y salidas a LangSmith. Una lista de revisión
en papel se olvida, y un aviso en el log no lo lee nadie.

## Decisión

- `compliance.check_production(settings)` corre al final de `load_settings`, pero solo con
  `ENVIRONMENT=production`. Junta todas las reglas que fallan y lanza un solo `ValueError` que nombra cada una,
  sin valores.
- Las reglas son tres: `MODEL_PROVIDER` no es `fake`, `API_KEYS` no está vacía con todas las claves de 16
  caracteres o más, y con `LANGSMITH_TRACING=true` deben valer `true` tanto `HIDE_INPUTS` como `HIDE_OUTPUTS`.
- `ENVIRONMENT` solo admite `development` y `production`, así un valor mal escrito no se salta las reglas.
- `doc/compliance-checklist.md` enlaza cada regla con su código y su prueba, y suma las reglas de privacidad de
  la fase 2.

## Consecuencias

- Una mala configuración falla al desplegar: Render no pasa el health check y no reemplaza la versión anterior.
- El error dice qué regla falla, nunca el valor de una clave.
- En desarrollo no se aplica, y las pruebas lo comprueban en los dos ambientes.
