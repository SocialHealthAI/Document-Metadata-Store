FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/app/config.yaml \
    DOCUMENTS_INPUT_PATH=/app/documents \
    HF_HOME=/app/.cache/huggingface \
    HF_HUB_DISABLE_TELEMETRY=1

COPY pyproject.toml README.md requirements.txt ./
COPY src ./src
COPY config.yaml metadata_schema.yaml ./
COPY documents ./documents

RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir . \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

CMD ["python", "-m", "document_metadata_store"]
