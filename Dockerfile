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

RUN mkdir -p /app/data/chroma /app/data/uploads

ENV DATA_DIR=/app/data \
    CHROMA_DIR=/app/data/chroma \
    UPLOADS_DIR=/app/data/uploads \
    SQLITE_PATH=/app/data/app.db \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
