# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

FROM python:3.11-slim AS runtime
# libgomp1 is required by chromadb's onnxruntime dependency at import time.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 appuser
WORKDIR /app
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    DEBUG=false
COPY --from=builder /opt/venv /opt/venv
COPY apps/ ./apps/
COPY packages/ ./packages/
COPY scripts/ ./scripts/
COPY alembic.ini ./
COPY data/embeddings/ ./data/embeddings/
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 8000
CMD ["python", "scripts/api.py"]
