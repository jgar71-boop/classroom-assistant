# 0009. Costo por llamada con tabla de precios validada al arrancar

Estado: propuesto

## Contexto

Cada palanca debe medirse en dólares sin red, y un modelo sin precio daría costos falsos en silencio. Las
llamadas que responde la caché del gateway no cuestan.

## Decisión

- `pricing.py` carga `PRICES_PATH` en una `PriceTable` inmutable; `load_settings` exige precio para
  `MODEL_SMALL` y `MODEL_LARGE` y, si falta, el producto no arranca.
- El agente suma el costo por llamada: `(in * input + out * output) / 1_000_000`, sin redondear; una
  `Completion` con `cached=True` suma a `cached_calls` y cuesta 0.
- Con `fake`, los dos modelos simulados responden igual pero se cobran con el precio de su nombre.
- `Metrics` suma `cost_usd` del proceso (misma excepción acotada del ADR 0005); `/students` nunca suma costo.

## Consecuencias

- `evaluate` compara línea base y palancas sin red ni cuota.
- Los precios se actualizan editando un archivo, no el código; una persona los confirma antes de la clase.
- El tope de salida y la caché no se notan con el simulado: se miden con `gateway`.
