FROM python:3.11-slim

WORKDIR /app

# System deps for pypdf/onnxruntime wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static
COPY eval ./eval
COPY sample_docs ./sample_docs

RUN mkdir -p /app/data/chroma /app/data/uploads /app/.cache

# Hosts like Hugging Face Spaces run the container as an arbitrary non-root
# UID, so the working dir needs to be writable by whoever that turns out to
# be. HOME is set explicitly because Chroma's embedding model cache resolves
# via Path.home(), which errors on a UID with no /etc/passwd entry.
ENV HOME=/app
RUN chmod -R 777 /app

ENV DATA_DIR=/app/data \
    CHROMA_DIR=/app/data/chroma \
    UPLOADS_DIR=/app/data/uploads \
    SQLITE_PATH=/app/data/app.db \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD curl -f "http://localhost:${PORT:-8000}/health" || exit 1

# Platforms like Render/Railway/Fly inject PORT and require the app to bind
# to it, overriding the fixed 8000 above (docker-compose doesn't set PORT,
# so local runs still default to 8000). Shell form is required for the
# ${PORT:-8000} expansion to happen at container start, not build time.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
