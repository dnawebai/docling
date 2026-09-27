FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/docling-models \
    TORCH_HOME=/opt/docling-models \
    DOCLING_ARTIFACTS_PATH=/opt/docling-models \
    OMP_NUM_THREADS=4 \
    PORT=8080

WORKDIR /opt/docling

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN python -m pip install --upgrade pip && \
    python -m pip install --extra-index-url https://download.pytorch.org/whl/cpu ".[standard]" && \
    python -m pip install -r iquash_service/requirements.txt && \
    mkdir -p /opt/docling-models && \
    docling-tools models download

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=5 \
  CMD curl --fail http://127.0.0.1:$PORT/health || exit 1

CMD ["sh", "-c", "uvicorn iquash_service.app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1"]
