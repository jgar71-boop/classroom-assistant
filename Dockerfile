# Imagen del Classroom Assistant para Render (ver doc/adr/0012-container-ci-and-render.md).
FROM python:3.12-slim

# Sin archivos .pyc y con la salida sin búfer, para que el log JSON salga al momento
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Usuario sin privilegios que corre el servicio
RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin appuser

# Primero las dependencias, para aprovechar la caché de capas de Docker
COPY requirements.txt .
RUN pip install -r requirements.txt

# El código; .dockerignore deja fuera .env, las pruebas y los cachés
COPY . .

# El producto guarda los alumnos en data/ con escritura atómica (archivo temporal
# en la misma carpeta), así que el usuario necesita ser dueño de la carpeta entera
RUN chown -R appuser:appuser /app/data

USER appuser

EXPOSE 8000

# Render da el puerto en PORT; en local se usa 8000. Sin access log, la salida
# estándar tiene solo las líneas JSON del log de eventos
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --no-access-log"]
