# 0010. Clave por cliente y límite de peticiones en un middleware

Estado: propuesto

## Contexto

Los nombres de los alumnos son datos personales. `/ask`, `/metrics` y `/students` tienen que pedir clave, y cada
cliente necesita su propio límite de peticiones. Si la clave se revisara con un `Depends` de FastAPI, un JSON
malformado respondería `422` antes que `401`. Además, cada ruta podría olvidar la protección.

## Decisión

- `API_KEYS` se lee al arrancar y queda en un `ApiKeys` inmutable que no muestra las claves en `repr`. Se compara
  con `hmac.compare_digest` sobre bytes contra todas las claves.
- La revisión es una función `guard(request)` (la arma `_build_security_guard` en `main.py`) que corre dentro
  del único middleware HTTP, `observe_request`, después de fijar el `request_id` y antes de `call_next`. Si
  devuelve un `401` o `429`, esa es la respuesta; si devuelve `None`, la petición sigue a FastAPI. Protege por
  ruta y para cualquier método: `/ask`, `/metrics`, `/students` y `/students/*`. Deja libres `/`, `/health`,
  `/docs` y `/openapi.json`.
- No es un middleware aparte porque Starlette corre cada middleware interno de `@app.middleware("http")` en otra
  tarea: el `client` que fijara en su `ContextVar` no llegaría al evento `request` que escribe el middleware de
  observabilidad. En el mismo middleware todo comparte el contexto.
- Después de autenticar, un `RateLimiter` en memoria con ventana deslizante de 60 s y el reloj inyectado. Las
  peticiones rechazadas no cuentan, y `Retry-After` dice los segundos que faltan.
- El cliente queda en una `ContextVar`. Así lo toman todos los eventos (`client`) y los metadatos de la traza, y
  la clave nunca pasa por ahí.

## Consecuencias

- Una ruta nueva bajo esos prefijos queda protegida sin hacer nada más. Los `401` y `429` tienen `request_id`,
  log y métrica, y el evento `request` lleva el `client` (también en un `429`).
- El `RateLimiter` es la segunda excepción acotada al ADR 0001, junto con las métricas del ADR 0005: guarda
  estado de operación por proceso, nunca datos de alumnos. Con varias instancias, cada una cuenta aparte. Un
  límite global pediría un almacén compartido.
- Para cambiar o revocar una clave hay que editar `API_KEYS` y reiniciar.
