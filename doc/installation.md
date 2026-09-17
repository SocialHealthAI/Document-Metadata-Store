# Installation

This tool has two roles: **building** a store from PDFs, and **using** that store from an agent or script. Details of console output and `search()` filters are in [usage.md](usage.md).

---

## Building a Metadata Document Store

Ingest loads PDFs, chunks them, extracts metadata, embeds `contextual_text` with local MiniLM (`all-MiniLM-L6-v2`, 384-dim, no embedding API key), and writes Chroma files under `data/metadata-store`. Source PDFs are never modified.

### Prerequisites

- Python 3.12+, or Docker and Docker Compose
- A clone of this repository

Preprocess and metadata extraction can run without `LLM_API_KEY` (aliases/rules; metadata fields stay Unknown). Set `LLM_PROVIDER=anthropic` and `LLM_API_KEY` for leftover heading classification and tagged metadata. Metadata LLM calls are batched (`PROCESSING_BATCH_SIZE` / `processing.batch_size`, default 50). There is no store URL or API key.

### Configure

1. Copy `.env.example` to `.env`.
2. Place text-extractable PDFs under `documents/` (or `DOCUMENTS_INPUT_PATH` / `config.yaml` `documents.input_path`). This repository may already include sample PDFs.
3. Adjust `config.yaml` and `metadata_schema.yaml` for the subject. Defaults target SDoH-style reports.
4. Original source documents must never be modified.

### Local run

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

The command discovers `documents/`, then load → preprocess → structure → chunk → metadata → embed → store. Exit status is `1` if any PDF failed at a stage. Records land in `data/metadata-store` (collection `knowledge`).

This full install includes PDF libraries, Anthropic, MiniLM, and Chroma. That is the **builder** stack.

### Docker

```bash
docker compose build
docker compose up
```

The image installs the package, **CPU torch**, and MiniLM weights, then runs `python -m document_metadata_store` once (it is not a long-running server). Chroma files live in the `data/metadata-store` volume. Rebuild after code changes: `docker compose up --build`. Scroll to `document-structure`, `document-chunk`, `document-metadata`, `document-embed`, and `document-store`. Without an API key, metadata histograms are empty (Unknown) but embeddings and store still run.

To preview without a rebuild, set `PREVIEW_BLOCKS` in `.env` (for example `PREVIEW_BLOCKS=20`) and run `docker compose up`. Or:

```bash
docker compose run --rm document-metadata-store python -m document_metadata_store --preview-blocks 20
```

### Input documents

This slice loads **text-extractable PDFs** only. Other formats and image-only PDFs are skipped. Later slices add DOCX, TXT, Markdown, and HTML.

---

## Client Usage

This repository is **public** (`https://github.com/SocialHealthAI/Document-Metadata-Store`). Clients and agent images can `pip install` from GitHub with no token.

Agents and scripts that only **call `search()`** do not run ingest. There is no HTTP SDK. `search()` embeds the query with the same local MiniLM model as ingest and reads **Chroma files on disk**.

A client is **not** Chroma-only. Besides `chromadb`, `search()` needs this package (filter rules, provenance shape) and `sentence-transformers` so query vectors match ingest. A `pip install` of the package currently pulls the full dependency set (including PDF/LLM libraries unused at query time).

### Install the library

The client does **not** have to clone the repo. Because the GitHub project is public, pip needs no credentials:

```bash
python -m pip install "git+https://github.com/SocialHealthAI/Document-Metadata-Store.git"
```

If you already cloned, an editable install is equivalent:

```bash
python -m pip install -e .
```

A published PyPI package is not provided in this slice. GitHub install ships the Python package (`src/` only); it does **not** unpack `data/metadata-store` into the client project.

### Provide the store files

`search()` must see the Chroma directory ingest wrote (the whole folder, not one file):

- **Clone of this repo:** use `data/metadata-store` when the sample store is present.
- **Otherwise:** copy `data/metadata-store` (Windows: `data\metadata-store`) from ingest (from the **host** volume if ingest ran in Docker). Also match collection name (`knowledge` by default); copying the `metadata_store:` block from `config.yaml` is enough.

Do not copy source PDFs unless the client needs them. Never modify original documents. After a new ingest, replace the client copy so search sees new records.

### Set a user-level environment variable

Point `search()` at that folder with a persistent user or system variable (not only a shell you close). A `.env` in the ingest repo is not visible to another project.

| Variable | Value |
|----------|--------|
| `METADATA_STORE_PERSIST_PATH` | Absolute path to the store folder |
| `METADATA_STORE_COLLECTION` | Same as ingest (default `knowledge`) |

**Windows** (then open a new terminal):

```bat
setx METADATA_STORE_PERSIST_PATH "C:\path\to\metadata-store"
setx METADATA_STORE_COLLECTION "knowledge"
```

**macOS / Linux** (then open a new shell):

```bash
echo 'export METADATA_STORE_PERSIST_PATH=/path/to/metadata-store' >> ~/.bashrc
echo 'export METADATA_STORE_COLLECTION=knowledge' >> ~/.bashrc
```

### Agent Dockerfile

Bake the library and MiniLM into the **agent** image instead of running `python -m pip install -e .` on a developer machine. `git` is required for a GitHub pip install. The repo is public, so the `git+https://` URL needs **no GitHub token**. Install **CPU torch** first so pip does not pull a CUDA wheel. Copy the whole `data/metadata-store` folder into the image (pip does not ship it).

```dockerfile
# Python 3.12+ (same as ingest)
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ENV HF_HOME=/opt/hf-cache \
    HF_HUB_DISABLE_TELEMETRY=1 \
    METADATA_STORE_PERSIST_PATH=/opt/metadata-store \
    METADATA_STORE_COLLECTION=knowledge

# CPU torch, then this package (pulls chromadb + sentence-transformers + unused ingest deps)
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir "git+https://github.com/SocialHealthAI/Document-Metadata-Store.git" \
    && python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Whole Chroma directory from ingest (or from this repo if the sample store is committed)
COPY data/metadata-store /opt/metadata-store
```

If the agent image cannot `COPY` from this repo, mount the folder at runtime instead of `COPY`:

```yaml
# compose fragment
services:
  agent:
    volumes:
      - /host/path/to/metadata-store:/opt/metadata-store:ro
    environment:
      METADATA_STORE_PERSIST_PATH: /opt/metadata-store
      METADATA_STORE_COLLECTION: knowledge
```

First `search()` will not hit Hugging Face at runtime if MiniLM was baked as above. The public GitHub URL in `pip install` needs no credentials.

### Call `search()`

```python
from document_metadata_store import search

hits = search("housing in Kenya", filters={"geography": ["Kenya"]}, k=8)
```

`k` is how many hits to return (default 8). First `search()` may download MiniLM if it is not cached. No store API key.

How to choose filters (start with one trusted field, tighten if noisy, relax if empty): [usage.md](usage.md) **Client Usage**.
