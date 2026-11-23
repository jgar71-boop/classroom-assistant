# 0005. Métricas en memoria del proceso, excepción acotada al ADR 0001

Estado: propuesto

## Contexto

`GET /metrics` debe informar peticiones, tasa de error, p50/p95, tokens, altas y si se cumple
`SLO_P95_MS` "de este proceso". El ADR 0001 prohíbe guardar estado en memoria entre peticiones.

## Decisión

- `Metrics` vive en memoria, una instancia por app, protegida con `threading.Lock`, y se inyecta en
  `create_app` para las pruebas.
- Solo guarda contadores de observación y una ventana de las últimas 1000 latencias; nunca alumnos,
  preguntas ni historial. Es la única excepción al ADR 0001.
- Percentil por rango más cercano; error = `status >= 500`; `met` es `p95 < SLO_P95_MS`; `pid` en la
  respuesta para saber qué proceso contesta.

## Consecuencias

- Los datos de negocio siguen sin estado: el ADR 0001 se mantiene para todo lo demás.
- Las métricas se pierden al reiniciar y, con varios workers, cada uno reporta las suyas; agregarlas
  requeriría un sistema externo (nuevo ADR).
- La memoria es acotada aunque el proceso atienda muchas peticiones.
