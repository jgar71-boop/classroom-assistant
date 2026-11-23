# Classroom Assistant

Registro de alumnos (nombre, materia, grado y número de salón) con un asistente que responde
preguntas sobre ellos. Desde la fase 2, cada petición se puede rastrear: lleva un `request_id`, deja
eventos JSON en la salida estándar y suma a las métricas de `GET /metrics`. Las trazas en LangSmith
son opcionales. Desde la fase 3, el asistente puede usar el modelo real (Cloudflare Workers AI por
AI Gateway) y cada respuesta informa su modelo, su ruta y su costo en USD. Desde la fase 4, los
datos de los alumnos solo se ven con una clave por cliente, hay un límite de peticiones por
cliente y, en producción, unas reglas de compliance impiden arrancar con una configuración
insegura.

La arquitectura y las decisiones (ADR) están en `doc/`. La lista de compliance está en
`doc/compliance-checklist.md`.

## Cómo correrlo

```bash
cd product
uv pip install -r requirements.txt
uv run uvicorn app.main:app --no-access-log
```

Se usa `--no-access-log` para que la salida estándar tenga solo líneas JSON del log de eventos.
La página web queda en `http://127.0.0.1:8000/`. Hay que correrlo desde `product/`: las rutas por
omisión (`data/students.json`, `data/model_prices.json`) son relativas.

Para el modelo real, copia `.env.example` a `.env`, pon `MODEL_PROVIDER=gateway` y completa
`CF_ACCOUNT_ID` y `CF_API_TOKEN` (el token es secreto y nunca se sube al repositorio).

Para usar la API o la página hay que definir `API_KEYS` (por ejemplo en `.env`) con la forma
`cliente:clave,cliente2:clave2`. En la página se escribe la clave en el campo «Clave de acceso»:
se guarda solo en `sessionStorage` de la pestaña y se manda en `X-API-Key`.

Pruebas, desde la raíz del repositorio (no llaman a la red):

```bash
uv run python -m verification unit
uv run python -m verification qa
uv run python -m verification contract-04
uv run python -m verification e2e
uv run python -m verification evaluate
uv run python -m verification docker
```

## Seguridad

- **Clave por cliente.** `POST /ask`, `GET /metrics`, `POST /students`, `GET /students` y
  `GET /students/{id}` exigen `X-API-Key`. Sin clave o con una inválida responden
  `401 {"detail": "invalid or missing API key"}`. `GET /`, `GET /health` y `/docs` no la piden.
  Las claves se comparan con `hmac.compare_digest`. El log, la auditoría y la traza llevan el
  nombre del cliente (`client`), nunca la clave.
- **Límite de peticiones.** Más de `RATE_LIMIT_PER_MINUTE` peticiones de un cliente en un minuto
  responden `429 {"detail": "rate limit exceeded"}` con `Retry-After` (segundos que faltan). El
  límite es por proceso: con varias instancias se multiplica.
- **Compliance.** Con `ENVIRONMENT=production` el producto no arranca si `MODEL_PROVIDER` es
  `fake`, si `API_KEYS` está vacía o tiene una clave de menos de 16 caracteres, o si
  `LANGSMITH_TRACING=true` y `HIDE_INPUTS` o `HIDE_OUTPUTS` no valen `true`. Si `API_KEYS` está
  mal formada tampoco arranca: el error dice qué entrada falla y su largo, nunca su valor.

## Publicación

El producto se publica en Render como contenedor (`Dockerfile` y `render.yaml`), y Render solo
despliega si pasa el pipeline de CI (`.github/workflows/ci.yml`). En Render se escriben los
secretos `API_KEYS`, `CF_ACCOUNT_ID` y `CF_API_TOKEN`; nunca van en el repositorio.
`LANGSMITH_API_KEY` es opcional y se agrega en Render > Environment solo si se encienden las
trazas.

### Límite conocido: los datos en Render

En el plan gratuito de Render el disco del contenedor **no persiste**: cada despliegue o
reinicio vuelve a la semilla de `data/students.json`, y los alumnos registrados se pierden. Es
aceptable para esta demostración. La salida es un disco persistente de Render (plan de pago),
montado por ejemplo en `/var/data` con `STUDENTS_PATH=/var/data/students.json`, o una base de
datos.

## API

| Ruta | Para qué |
| --- | --- |
| `GET /` | Página web: registro, lista y chat; muestra el `request_id` de cada respuesta |
| `GET /health` | Estado y `pid` del proceso |
| `POST /students` | Registra un alumno |
| `GET /students` | Lista alumnos; filtros `classroom` y `subject` |
| `GET /students/{id}` | Un alumno por id |
| `POST /ask` | Pregunta al asistente; incluye `request_id`, `model`, `route`, `cached_calls` y `cost_usd` |
| `GET /metrics` | Peticiones, `error_rate`, latencia p50/p95, tokens, altas, `cost_usd` y SLO |

Toda respuesta lleva el encabezado `X-Request-ID`. Si el cliente lo manda con 1 a 128 letras,
dígitos, `.`, `_` o `-`, se conserva; si no, se genera un UUID. Un fallo interno responde `500`
con `{"detail": "internal error", "request_id": ...}`. Si el modelo real falla o tarda más de
`MODEL_TIMEOUT_SECONDS`, `POST /ask` responde `502` con
`{"detail": "model unavailable", "request_id": ...}`.

## Palancas de costo

- **Enrutamiento:** una regla en código elige `MODEL_LARGE` si `ROUTING=false`
  (`routing_disabled`), si la pregunta pasa de `ROUTER_MAX_CHARS` caracteres (`long_question`) o si
  contiene «compara», «resume», «explica», «por qué», «analiza» o «todos» al inicio de una palabra,
  sin distinguir mayúsculas ni tildes (`keyword:<palabra>`). Si no, `MODEL_SMALL`
  (`short_question`).
- **Ventana de historial:** solo se mandan al modelo los últimos `HISTORY_WINDOW` mensajes.
- **Tope de salida:** `MODEL_MAX_TOKENS` en cada llamada.
- **Caché de AI Gateway:** con `CACHE_TTL_SECONDS` mayor que 0 se manda `cf-aig-cache-ttl`; una
  respuesta con `cf-aig-cache-status: HIT` cuenta en `cached_calls` y no cuesta.

El costo se calcula con `data/model_prices.json` (USD por millón de tokens). Con
`MODEL_PROVIDER=fake` los dos modelos simulados se llaman como `MODEL_SMALL` y `MODEL_LARGE`:
responden igual, pero cuestan según su nombre.

## Log de eventos

Una línea JSON por evento con `ts` (UTC), `service`, `event`, `request_id` y `client` (nombre
del cliente autenticado; `null` en las rutas libres):

- `request`: `method`, `path`, `status`, `latency_ms`.
- `agent_run`: `question_chars`, `history_messages`, `steps`, `tools`, `input_tokens`,
  `output_tokens`, `stopped`, `model`, `route`, `cost_usd`. Nunca el texto de la pregunta ni de
  la respuesta.
- `audit` `tool_call`: `tool` y `args` (solo el argumento esperado).
- `audit` `student_created`: `student_id`, `grade`, `classroom`. Nunca el nombre.
- `error`: `error_type`, sin el mensaje.

## Variables de entorno

| Variable | Por omisión | Para qué |
| --- | --- | --- |
| `MODEL_PROVIDER` | `fake` | Proveedor del modelo: `fake` o `gateway` |
| `AGENT_MAX_STEPS` | `3` | Tope de vueltas del agente |
| `MAX_QUESTION_CHARS` | `2000` | Largo máximo de la pregunta |
| `STUDENTS_PATH` | `data/students.json` | Archivo JSON de alumnos |
| `SERVICE_NAME` | `classroom-assistant` | Campo `service` del log |
| `SLO_P95_MS` | `2000` | Meta de latencia p95 en milisegundos (entero >= 1) |
| `LANGSMITH_TRACING` | `false` | Enciende las trazas (`true` o `false`) |
| `LANGSMITH_API_KEY` | sin valor | Clave de LangSmith; sin ella no hay trazas ni conexiones |
| `HIDE_INPUTS` | `true` | No mandar a LangSmith las entradas |
| `HIDE_OUTPUTS` | `true` | No mandar a LangSmith las salidas |
| `CF_ACCOUNT_ID` | sin valor | Cuenta de Cloudflare; obligatoria con `gateway` |
| `CF_GATEWAY_ID` | `default` | Id del AI Gateway |
| `CF_API_TOKEN` | sin valor | Token secreto de Cloudflare; obligatorio con `gateway` |
| `MODEL_SMALL` | `@cf/meta/llama-3.1-8b-instruct-fast` | Modelo barato |
| `MODEL_LARGE` | `@cf/meta/llama-3.3-70b-instruct-fp8-fast` | Modelo capaz |
| `ROUTING` | `true` | Enrutamiento por pregunta (`true` o `false`) |
| `ROUTER_MAX_CHARS` | `80` | Preguntas más largas van al modelo capaz (entero >= 1) |
| `HISTORY_WINDOW` | `6` | Mensajes de historial que se mandan (entero >= 0) |
| `MODEL_MAX_TOKENS` | `300` | Tope de tokens de salida (entero >= 1) |
| `MODEL_TEMPERATURE` | `0` | Temperatura; con 0 las evaluaciones son repetibles |
| `MODEL_TIMEOUT_SECONDS` | `20` | Tiempo máximo de una llamada al gateway (> 0) |
| `CACHE_TTL_SECONDS` | `0` | Caché del gateway en segundos (0: apagada) |
| `PRICES_PATH` | `data/model_prices.json` | Precios por modelo, en USD por millón de tokens |
| `ENVIRONMENT` | `development` | Con `production` se aplican las reglas de compliance |
| `API_KEYS` | vacía | Clientes y claves, `cliente:clave,cliente2:clave2` (secreto) |
| `RATE_LIMIT_PER_MINUTE` | `30` | Peticiones por cliente por minuto (entero >= 1) |

Un modelo de `MODEL_SMALL` o `MODEL_LARGE` sin precio en `PRICES_PATH` impide arrancar. La clave de
LangSmith se lee solo del entorno: nunca se guarda en la configuración, en el código ni en el log.
El token de Cloudflare y las claves de `API_KEYS` no aparecen en `repr` de la configuración, en
el log ni en los mensajes de error.
