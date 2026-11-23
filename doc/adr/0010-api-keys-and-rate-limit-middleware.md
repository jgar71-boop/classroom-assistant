# 0010. Clave por cliente y límite de peticiones en un middleware

Estado: propuesto

## Contexto

Los nombres de los alumnos son datos personales. `/ask`, `/metrics` y `/students` tienen que pedir clave, y cada
cliente necesita su propio límite de peticiones. Si la clave se revisara con un `Depends` de FastAPI, un JSON
malformado respondería `422` antes que `401`. Además, cada ruta podría olvidar la protección.

## Decisión

- `API_KEYS` se lee al arrancar y queda en un `ApiKeys` inmutable que no muestra las claves en `repr`. Se compara
  con `hmac.compare_digest` sobre bytes contra todas las claves.
- Un middleware de seguridad va dentro del de observabilidad. Protege por ruta y para cualquier método: `/ask`,
  `/metrics`, `/students` y `/students/*`. Deja libres `/`, `/health`, `/docs` y `/openapi.json`.
- Después de autenticar, un `RateLimiter` en memoria con ventana deslizante de 60 s y el reloj inyectado. Las
  peticiones rechazadas no cuentan, y `Retry-After` dice los segundos que faltan.
- El cliente queda en una `ContextVar`. Así lo toman todos los eventos (`client`) y los metadatos de la traza, y
  la clave nunca pasa por ahí.

## Consecuencias

- Una ruta nueva bajo esos prefijos queda protegida sin hacer nada más. Los `401` y `429` tienen `request_id`,
  log y métrica.
- El límite es por proceso, otra excepción acotada al ADR 0001, como las métricas del ADR 0005. Con varias
  instancias, cada una cuenta aparte. Un límite global pediría un almacén compartido.
- Para cambiar o revocar una clave hay que editar `API_KEYS` y reiniciar.
