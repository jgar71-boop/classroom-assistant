# Arquitectura del Classroom Assistant

El producto es un registro de alumnos (nombre, materia, grado y salón) con un asistente que responde preguntas
sobre ellos. Es una API FastAPI sin estado de negocio: los datos viven en un archivo JSON que solo toca el
repositorio. Cada fase le agrega algo:

- **Fase 2, observabilidad**: un id por petición, log JSON, métricas del proceso y trazas opcionales.
- **Fase 3, costos**: el modelo real (Workers AI por AI Gateway) y cuatro palancas de costo para `POST /ask`.
- **Fase 4, producción**: una clave por cliente, límite de peticiones y compliance al arrancar. Se empaqueta en
  un contenedor, pasa por un CI de cuatro etapas y se publica en Render.

```mermaid
flowchart LR
    Browser["Página web<br/>static/index.html<br/>clave en sessionStorage"]
    subgraph API["main.py · create_app()"]
        MW["Middleware de observabilidad<br/>X-Request-ID, latencia,<br/>error 500"]
        Sec["Middleware de seguridad<br/>401 sin clave · 429 con Retry-After<br/>libres: /, /health, /docs"]
        Routes["Rutas<br/>/students, /ask, /metrics<br/>502 si el modelo falla"]
    end
    Config["config.py<br/>Settings + CostSettings<br/>+ SecuritySettings"]
    Compliance["compliance.py<br/>check_production<br/>no arranca si incumple"]
    Security["security.py<br/>ApiKeys (compare_digest)<br/>RateLimiter por cliente"]
    Prices["pricing.py<br/>PriceTable<br/>data/model_prices.json"]
    Router["router.py<br/>choose_route: model + route"]
    Ctx["request_context.py<br/>request_id + client<br/>(ContextVar)"]
    Clock["clock.py<br/>Clock inyectado"]
    Events["events.py<br/>EventLog: JSON por línea<br/>con client, nunca la clave"]
    Metrics["metrics.py<br/>Metrics del proceso"]
    Tracing["tracing.py<br/>@traceable opcional<br/>model, route, client, cost_usd"]
    subgraph Agents["Un Agent por modelo"]
        AgentS["Agent MODEL_SMALL"]
        AgentL["Agent MODEL_LARGE"]
    end
    LLM["llm.py<br/>LanguageModel.complete()<br/>FakeModel"]
    Gateway["gateway.py<br/>GatewayModel"]
    CF[("Cloudflare AI Gateway<br/>Workers AI")]
    Repo["repository.py<br/>StudentRepository<br/>Lock + escritura atómica"]
    File[("STUDENTS_PATH<br/>students.json<br/>efímero en Render free")]
    Stdout[["stdout"]]
    LangSmith[("LangSmith<br/>solo con clave")]

    Browser -- "HTTP JSON + X-API-Key" --> MW
    MW --> Sec
    Sec -- "identify, check" --> Security
    Sec -- "client" --> Ctx
    Sec --> Routes
    MW --> Ctx
    MW -- "request, error" --> Events
    MW -- "latencia, status" --> Metrics
    Clock --> MW
    Clock --> Security
    Clock --> Events
    Config --> Compliance
    Config --> Security
    Config --> Routes
    Prices --> Config
    Routes -- "POST/GET /students" --> Repo
    Routes -- "student_created" --> Events
    Routes -- "pregunta" --> Router
    Routes -- "POST /ask" --> Agents
    Routes -- "agent_run" --> Events
    Routes -- "tokens, cost_usd" --> Metrics
    Ctx -- "request_id, client" --> Events
    Agents -- "costo por llamada" --> Prices
    Agents -- "tool_call" --> Events
    Agents -- "messages" --> LLM
    LLM -- "MODEL_PROVIDER=gateway" --> Gateway
    Gateway -- "httpx inyectado" --> CF
    Agents -- "get / find_by_*" --> Repo
    Agents -. "trazas con request_id y client" .-> Tracing
    Tracing -. "HIDE_INPUTS/OUTPUTS" .-> LangSmith
    LLM -- "subjects()" --> Repo
    Events --> Stdout
    Repo -- "temporal + os.replace" --> File
```

## Publicación

```mermaid
flowchart LR
    Push["git push / pull request"] --> Style["style<br/>pylint 88"]
    Style --> Unit["unit<br/>pytest + BDD<br/>cobertura >= 80 %"]
    Unit --> E2E["e2e<br/>Playwright, modelo simulado"]
    E2E --> Docker["docker<br/>docker build"]
    Docker -- "checksPass" --> Render["Render Blueprint<br/>render.yaml, plan free<br/>secretos sync: false"]
    Render -- "/health" --> Live["Servicio Live"]
    Live --> Smoke["scripts/smoke.py<br/>SMOKE_API_KEY del entorno"]
```

## Piezas

- `config.py`: lee y valida las variables de las cuatro fases y llama al compliance. No guarda
  `LANGSMITH_API_KEY`, y no muestra `CF_API_TOKEN` ni `API_KEYS` en `repr`.
- `compliance.py`: con `ENVIRONMENT=production` no deja arrancar con el modelo simulado, sin claves o con claves
  cortas, ni con trazas que no ocultan entradas y salidas.
- `security.py`: interpreta `API_KEYS`, identifica al cliente con `hmac.compare_digest` y lleva el límite por
  cliente con ventana deslizante.
- `pricing.py`: precios por millón de tokens y el costo de una llamada.
- `router.py`: elige `MODEL_SMALL` o `MODEL_LARGE` y dice el motivo.
- `gateway.py`: llama a AI Gateway. Toda falla se vuelve `ModelUnavailable`.
- `clock.py`: hora UTC y reloj monotónico inyectables. Lo usan la latencia, el log y el límite.
- `request_context.py`: el `request_id` y el cliente autenticado, cada uno en su `ContextVar`.
- `events.py`: eventos con campos fijos y `client`. No llevan datos personales ni claves.
- `metrics.py`: contadores, p50/p95, SLO y costo acumulado del proceso.
- `tracing.py`: trazas de LangSmith, privadas por omisión, con modelo, ruta, cliente y costo.
- `repository.py`: el único acceso al archivo. Da ids `STU-NNNN` consecutivos bajo candado.
- `llm.py`: la interfaz de modelo, el modelo simulado determinista y `build_model`.
- `agent.py`: protocolo JSON, tope de vueltas, ventana de historial y costo por llamada.
- `main.py`: los dos middlewares (observabilidad por fuera, seguridad por dentro), Pydantic estricto, las rutas
  y un agente por modelo.
- `static/index.html`: tiene el campo de clave (contraseña, en `sessionStorage`), el alta, la lista y el chat.
  Muestra «Clave inválida» y «Demasiadas peticiones». Escribe solo con `textContent`.
- `Dockerfile`, `.github/workflows/ci.yml`, `render.yaml` y `scripts/smoke.py`: empaquetan, prueban, publican y
  comprueban.

## Decisiones

- [0001 API sin estado con repositorio de archivo JSON atómico](adr/0001-stateless-api.md)
- [0002 Un solo agente de solo lectura con bucle con tope](adr/0002-read-only-agent-bounded-loop.md)
- [0003 Interfaz de modelo, modelo simulado e inyección](adr/0003-model-interface-and-injection.md)
- [0004 Id por petición y eventos JSON con campos fijos](adr/0004-request-id-and-json-events.md)
- [0005 Métricas en memoria del proceso, excepción acotada al ADR 0001](adr/0005-in-process-metrics.md)
- [0006 Trazas opcionales en LangSmith, privadas por omisión](adr/0006-optional-langsmith-tracing.md)
- [0007 Modelo real por AI Gateway con cliente HTTP inyectado](adr/0007-gateway-model-injected-http.md)
- [0008 Enrutamiento por regla en código, un agente por modelo](adr/0008-rule-based-routing.md)
- [0009 Costo por llamada con tabla de precios validada al arrancar](adr/0009-cost-per-call-and-price-table.md)
- [0010 Clave por cliente y límite de peticiones en un middleware](adr/0010-api-keys-and-rate-limit-middleware.md)
- [0011 Compliance como código: el producto no arranca si incumple](adr/0011-compliance-as-code-at-startup.md)
- [0012 Contenedor, CI en cuatro etapas y Render con disco efímero](adr/0012-container-ci-and-render.md)
- Lista de compliance: [compliance-checklist.md](compliance-checklist.md), que escribe `security`.
