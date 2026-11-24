# 0007. Modelo real por AI Gateway con cliente HTTP inyectado

Estado: propuesto

## Contexto

La fase 3 agrega Cloudflare Workers AI a través de AI Gateway. Las pruebas no pueden tocar la red ni gastar
cuota, el token es secreto y una falla del proveedor no debe verse como un error interno genérico. Un gateway
puede tener activado «Authenticated Gateway», que exige un segundo token propio del gateway.

## Decisión

- `gateway.py` define `GatewayModel(costs, model_name, client)`, que cumple la misma interfaz
  `complete(messages)` del ADR 0003; `build_model` lo elige con `MODEL_PROVIDER=gateway`.
- El `httpx.Client` se inyecta (`create_app(http_client=...)`); las pruebas usan `httpx.MockTransport`.
- El prompt de sistema lo antepone `GatewayModel`, así el agente y el modelo simulado no cambian.
- Toda falla (red, timeout, estado no 2xx, cuerpo sin `choices` o `usage`) se vuelve `ModelUnavailable`, y
  `/ask` responde `502 {"detail": "model unavailable", "request_id"}`.
- `CF_API_TOKEN` va en `Authorization: Bearer`. La variable opcional `CF_AIG_TOKEN`, si tiene valor, agrega
  `cf-aig-authorization: Bearer <token>` para gateways con «Authenticated Gateway»; si está vacía, el
  encabezado no se manda.
- `CF_API_TOKEN` y `CF_AIG_TOKEN` viven en `Settings` con `repr=False`; nunca se registra ni la URL, ni los
  encabezados, ni `str(exc)`.

## Consecuencias

- Cambiar de proveedor sigue siendo un `LanguageModel` nuevo y una rama en `build_model`.
- El `502` cuenta como error en `/metrics`; el costo de llamadas previas a la falla se pierde (aceptado).
- Sin `CF_ACCOUNT_ID` o `CF_API_TOKEN` el producto no arranca con `gateway`. Sin `CF_AIG_TOKEN` arranca igual,
  pero un gateway autenticado rechaza la llamada y `/ask` responde `502`.
