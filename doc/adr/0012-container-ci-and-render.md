# 0012. Contenedor, CI en cuatro etapas y Render con disco efímero

Estado: propuesto

## Contexto

El producto se publica en Render y los ingenieros tienen que ver cada etapa antes de que llegue a producción.
El plan gratuito de Render no guarda el disco del contenedor, y los alumnos se guardan en
`data/students.json`.

## Decisión

- La imagen usa `python:3.12-slim` con un usuario sin root que es dueño de `data/`. Arranca con
  `sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"`. `.dockerignore` deja fuera `.env`, las
  pruebas y los cachés.
- El CI de GitHub Actions corre en cada push y pull request con la cadena `style` -> `unit` -> `e2e` -> `docker`,
  unida con `needs`.
- `render.yaml` es un Blueprint con un servicio web que se llama igual que el repositorio, con
  `autoDeployTrigger: checksPass`. Los secretos van con `sync: false` y se escriben solo en Render.
- La prueba de humo `scripts/smoke.py` comprueba la seguridad publicada sin registrar alumnos.
- Se acepta que los datos se pierdan: cada despliegue o reinicio vuelve a la semilla de `data/students.json`.

## Consecuencias

- Solo se publica lo que pasó las cuatro etapas, y una persona aprueba cada push.
- Los alumnos registrados en Render se pierden. Esto queda escrito aquí y en el `README.md`. Hay dos salidas: un
  disco persistente de Render (plan de pago, montado en `/var/data` con
  `STUDENTS_PATH=/var/data/students.json`, sin cambiar el código) o una base de datos detrás de
  `StudentRepository`.
- La imagen incluye las dependencias de prueba mientras `requirements.txt` sea uno solo.
