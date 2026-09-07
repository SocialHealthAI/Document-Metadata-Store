# Installation

## Prerequisites

- Python 3.12+, or Docker and Docker Compose
- A copy of this repository

Provider credentials for embeddings / LLM / metadata store are not required for the load step.

## Configure

1. Copy `.env.example` to `.env`.
2. Place text-extractable PDFs under `documents/` (or the path in `DOCUMENTS_INPUT_PATH` / `config.yaml`).
3. Original source documents must never be modified.

## Local run (load step)

```bash
python -m pip install -e .
python -m document_metadata_store
```

Optional: `python -m document_metadata_store --config config.yaml`

To print the first N blocks of each loaded document:

```bash
python -m document_metadata_store --preview-blocks 20
```

Or set `PREVIEW_BLOCKS=20` / `documents.preview_blocks` in `config.yaml` (default `0` = summary only).

The command discovers `documents/`, loads text PDFs with **pypdf** (and **fonttools**, needed to decode embedded CFF/Type1 fonts such as those in the WHO report), prints the console summary, and keeps `NormalizedDocument` trees in memory for the process. Exit status is `1` if any PDF failed to parse.

## Docker

```bash
docker compose build
docker compose up
```

The image installs the package and runs `python -m document_metadata_store`. Compose mounts `./documents` and `config.yaml` into the container.

To preview blocks without a rebuild, set `PREVIEW_BLOCKS` in `.env` (for example `PREVIEW_BLOCKS=20`) and run `docker compose up`. Or:

```bash
docker compose run --rm document-metadata-store python -m document_metadata_store --preview-blocks 20
```

## Input documents

This slice loads **text-extractable PDFs** only. Other formats and image-only PDFs are skipped. Later slices add DOCX, TXT, Markdown, and HTML.
