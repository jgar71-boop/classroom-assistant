# 0003. Interfaz de modelo, modelo simulado e inyección en `create_app`

Estado: propuesto

## Contexto

En esta sesión no hay modelo real: se necesita un modelo determinista, sin red ni costo, y poder cambiarlo
después sin tocar el agente. Las pruebas deben usar sus propios datos y configuración.

## Decisión

- `llm.py` define el protocolo `LanguageModel.complete(messages)`, que devuelve el texto JSON y los tokens de
  entrada y salida.
- `FakeModel` implementa las cinco reglas de la especificación en orden, lee las materias del repositorio en
  cada llamada y cuenta tokens por palabras. `build_model(settings, repository)` lo elige según
  `MODEL_PROVIDER` (solo `fake`).
- `create_app(settings=None, model=None, repository=None)` construye lo que no recibe desde el entorno;
  `config.load_settings` valida y falla al arrancar con un mensaje claro.
- Una sola función `normalize` (casefold sin tildes) la usan el filtro de la API, la herramienta y el
  modelo simulado.

## Consecuencias

- Agregar un proveedor real es un nuevo `LanguageModel` y una rama en `build_model`, sin cambiar el agente.
- Las pruebas inyectan un repositorio en `tmp_path` y modelos guionizados para cubrir errores y el tope.
- El modelo simulado no razona: sus respuestas solo sirven para verificar el flujo, no la calidad.
