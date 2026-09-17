# Document Metadata Store

A generalized tool for converting documents into searchable, context-aware knowledge records. Records are organized in a vector store with associated metadata for each vector. The Document Metadata Store can be used by agents that need document content with provenance. This repository ships a **Social Determinants of Health** sample corpus and store; the same tool can build other knowledge stores through configuration and schemas.

When creating a document store, the tool:

- loads a folder of PDF documents (text-extractable PDFs only)
- preprocesses content to exclude sections (configurable: cover, TOC, acknowledgements, …)
- extracts document structure (sections and subsections) used as heading context
- **context-aware chunking:** splits on section, paragraph, and sentence boundaries (not a fixed sliding window), and prepends ancestor headings to each chunk so the embedding and the metadata extractor see *where* the text sat in the outline
- generates metadata for chunks (configurable schema; this sample uses `topic`, `geography`, `population`, `time_period`)
- embeds chunks with a local model (`all-MiniLM-L6-v2`, 384-dim; no embedding API key)
- persists metadata and vectors in local Chroma files under `data/metadata-store`

Source PDFs are never modified. Sample PDFs belong in `documents/`; the built store belongs in `data/metadata-store`. 

## Building a Metadata Document Store

**Prerequisites:** Python 3.12+, or Docker and Docker Compose.

1. Clone this repository.
2. Copy `.env.example` to `.env`. Set `LLM_API_KEY` if you want LLM-backed section classification and metadata tags; omit it to still load, chunk, embed, and store (metadata fields stay Unknown).
3. Place text-extractable PDFs in `documents/` (or change `documents.input_path` / `DOCUMENTS_INPUT_PATH`). The default schema and exclude lists in `config.yaml` and `metadata_schema.yaml` target SDoH-style reports; change those files for another subject.
4. Run ingest:

```bash
docker compose up --build
```

Or locally:

```bash
python -m pip install -e .
python -m document_metadata_store
```

Records are written to `data/metadata-store` (collection `knowledge`). The console prints one compact recap per stage (`document-load` … `document-store`), not one line per chunk.

Full install, env vars, and Docker notes: [doc/installation.md](doc/installation.md) **Building a Metadata Document Store**. Console output and processing modes: [doc/usage.md](doc/usage.md) **Building a Metadata Document Store**. Architecture: [doc/architecture.md](doc/architecture.md).

## Client Usage

Agents do not query the PDF or the section tree. They import **`search()`**, which embeds the query with the same MiniLM model and optionally filters on metadata tags. The client does not have to clone: `pip install git+https://github.com/SocialHealthAI/Document-Metadata-Store.git` installs the library from this **public** repo (no GitHub token). Chroma files still live on disk (`data/metadata-store` from a clone, or a copy).

1. Install the library (GitHub pip, or `python -m pip install -e .` from a clone). Chroma alone is not enough.
2. Point `METADATA_STORE_PERSIST_PATH` at the store folder. Details: [doc/installation.md](doc/installation.md) **Client Usage**.

```python
from document_metadata_store import search

query = "Did housing instability among adults in Kenya change after 2020?"
hits = search(query, filters={"geography": ["Kenya", "Kenyan"]}, k=8)
# each hit: text, metadata, provenance, score
```

`k` is how many hits to return (default 8). Put the user’s question in `query`. Add filters only for tags you are willing to require: empty `time_period` on a chunk will not match `time_period: ["2020"]` even if the prose mentions 2020. Start with the filter you trust (often place), tighten if results are noisy, relax if you get none. Do not AND all four fields on the first call.

Full filter rules and the search loop: [doc/usage.md](doc/usage.md) **Client Usage**.
