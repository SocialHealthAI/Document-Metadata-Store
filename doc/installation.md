# Installation

## Prerequisites

- Python 3.12+, or Docker and Docker Compose
- A copy of this repository

Provider credentials for embeddings / metadata store are not required. Preprocess can run without `LLM_API_KEY` (alias/rules only). Anthropic is used when `LLM_PROVIDER=anthropic` and `LLM_API_KEY` are set.

## Configure

1. Copy `.env.example` to `.env`.
2. Place text-extractable PDFs under `documents/` (or the path in `DOCUMENTS_INPUT_PATH` / `config.yaml`).
3. Original source documents must never be modified.

## Local run

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

The command discovers `documents/`, loads text PDFs with **pypdf** (and **fonttools**), preprocesses keep/exclude marks, builds a retained section tree, then emits context-aware chunks. Exit status is `1` if any PDF failed to parse, preprocess, extract structure, or chunk.

## Docker

```bash
docker compose build
docker compose up
```

The image installs the package and runs `python -m document_metadata_store` once (it is not a long-running server). Rebuild after code changes: `docker compose up --build`. Scroll to `document-structure` and `document-chunk` after preprocess. Short PDFs often show `excluded_sections: (none)` and one implicit title section split into size-bounded chunks.

To preview blocks without a rebuild, set `PREVIEW_BLOCKS` in `.env` (for example `PREVIEW_BLOCKS=20`) and run `docker compose up`. Or:

```bash
docker compose run --rm document-metadata-store python -m document_metadata_store --preview-blocks 20
```

## Input documents

This slice loads **text-extractable PDFs** only. Other formats and image-only PDFs are skipped. Later slices add DOCX, TXT, Markdown, and HTML.
