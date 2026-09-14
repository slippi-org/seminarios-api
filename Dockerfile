# Seminarios API. Built for linux/arm64 (the Pi is aarch64).
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    SEM_DB_PATH=/data/seminarios.sqlite

WORKDIR /app

# Dependencies first, so a source edit does not reinstall the world.
COPY pyproject.toml README.md ./
COPY app ./app
COPY manage.py ./
RUN pip install --no-cache-dir .

# The database is a BIND MOUNT from the host, so the container user must own it
# there too. uid 1000 is `aaron` on ag-rpi5 -- change both together or the API
# starts and then cannot write.
RUN useradd --uid 1000 --create-home seminarios \
    && mkdir -p /data \
    && chown -R seminarios:seminarios /data /app
USER seminarios

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=5 --start-period=15s \
    CMD python -c "import urllib.request,sys; \
sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
