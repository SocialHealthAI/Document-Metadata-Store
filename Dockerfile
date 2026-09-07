FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/app/config.yaml \
    DOCUMENTS_INPUT_PATH=/app/documents

COPY pyproject.toml README.md requirements.txt ./
COPY src ./src
COPY config.yaml metadata_schema.yaml ./
COPY documents ./documents

RUN pip install --no-cache-dir .

CMD ["python", "-m", "document_metadata_store"]
