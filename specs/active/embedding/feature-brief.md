# Feature Brief: Embedding Generation

**Task ID:** embedding
**Created:** 2026-09-15
**Status:** Implemented

---

## Problem Statement

Chunks already carry headings plus body (`contextual_text`) and optional filter tags. Nothing turns that prose into vectors, so the later store has nothing to search by similarity. This slice embeds each chunk in the same CLI run without writing to the metadata store, embedding metadata strings, or modifying source PDFs.

## Target Users

The same operators as load through metadata: they drop PDFs in `documents/`, run one command, and need a compact per-document embed recap (counts, model, dim, sample — not 500 vectors) before a later store slice.

## Core Requirements

### Must Have

- [x] Run **in the same process/CLI** after metadata extraction (`python -m document_metadata_store` / `docker compose up`) — not a separate command
- [x] Embed `EnrichedDocument` as-is (including Unknown fields and `metadata.enabled: false`)
- [x] Vectorize **`contextual_text` only**. Metadata lists stay on the record beside the vector. Do not concatenate or embed tag strings
- [x] Local **`sentence-transformers` / `all-MiniLM-L6-v2`** (384-dim, CPU) in the app image. No API key. **No embedding settings in `config.yaml` or `.env`**
- [x] Copy-on-write: wrap `EnrichedChunk` (e.g. `EmbeddedChunk`) with `embedding`, `dim`, and model id. Do not mutate `original_text` / `contextual_text`
- [x] Batch encode with `processing.batch_size` (default 50). Per-batch/per-chunk encode failure → that chunk unmarked/failed; continue the document
- [x] Subject-independent: same local model for every corpus — not `if subject == …`
- [x] Never modify original source files
- [x] Console: **counts + model/dim + a small sample**, not one vector per chunk. See Console below
- [ ] Prove against the WHO 2025 PDF **and** one Healthy People scrape (vectors present, dim 384, source PDFs unchanged)

### Nice to Have

- [x] Bake the model into the Docker image at build time so `compose up` does not need Hugging Face at runtime
- [ ] Persist an inspectable embedding dump (product spec §18)
- [ ] Metadata store writes (next slice)
- [ ] GPU / CUDA device selection

## Technical Approach

After `extract_metadata_documents`, an embedder walks each `EnrichedDocument`. For every chunk it encodes **`chunk.contextual_text`**. Copy-on-write: emit an embedded record wrapping the frozen `EnrichedChunk`.

Hardcoded local adapter: `SentenceTransformer("all-MiniLM-L6-v2")` on CPU. No `embeddings:` YAML, no `EMBEDDING_*` env. `metadata.enabled: false` still produces `EnrichedDocument`s with empty fields — **still embed those chunks**.

Add `sentence-transformers` (CPU torch) to package dependencies.

Unit tests inject `embed_batch` (fixed dim, no live model). Live WHO/HP proof is the same operator run as metadata (`docker compose up --build`), not pytest-in-image.

**Patterns to Follow:**

- Same CLI chain: `cli.py` load → preprocess → structure → chunk → extract metadata → **embed**
- Protocol + run/outcome + continue-on-per-file-failure (`pipeline/extractor.py`)
- Injectable batch function for tests (`metadata/llm.py` `complete_batch`)
- Frozen wrap; do not mutate chunker/extractor output
- Compact console (`format_metadata_run`): header, per-file stats, sample — never dump payloads
- Canonical docs: product spec §9, `doc/architecture.md` embedder

**Key Decisions:**

- **Same CLI:** embed after metadata in one run
- **Local MiniLM only:** no operator embedding config
- **No metadata validation stage** in the product pipeline
- **Prose vectors, tag filters:** synonymy (US / USA) is cosine over `contextual_text`, not over metadata strings
- **No store:** vectors stay in memory for console + later persist
- **Histogram-style console:** WHO ~500 chunks must not print vectors

### Embedding (locked)

```text
0. Always run after metadata (no embeddings.enabled / provider / model knobs)
1. Encode with local sentence-transformers / all-MiniLM-L6-v2
2. For each EnrichedDocument (whether metadata ran or was skipped):
   - batch chunks by processing.batch_size
   - encode each chunk's contextual_text
   - attach embedding + dim + model on a copy-on-write wrapper
3. Encode failure → that chunk embed_failed; continue
4. Do not rewrite original_text, contextual_text, or metadata lists
5. Do not write the metadata store
```

### Console (counts + sample)

```text
document-embed
  model: all-MiniLM-L6-v2  dim: 384
  records: 519  embedded: 519  failed: 0

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             records: 519  dim: 384  failed: 0
             sample:
               c1   chars=842
               c41  chars=1204
```

Always print **model, dim, counts**. Sample size = `preview_blocks` when > 0, otherwise **5**. Do not print vector components. Do not print one line per chunk. Preview may add truncated `contextual_text` on the sample.

## Next Actions

1. [x] Models: `EmbeddedChunk` / `EmbeddedDocument` wrapping `EnrichedChunk` (vector, dim, model, fail flag)
2. [x] Hardcoded MiniLM adapter; batched encode; injectable `embed_batch`; no config/env
3. [x] Wire after metadata in CLI; counts + sample console; Docker dep; optional bake model in image
4. [x] Tests: dim 384, does not embed tags, console does not dump vectors, metadata-disabled still embeds
5. [x] Update `doc/installation.md`, `README.md`, `specs/index.md` (architecture/usage/product spec already aligned)

## Success Criteria

- [x] One command loads through metadata then attaches vectors; source PDFs unchanged
- [x] Each successful chunk has a 384-dim embedding from `contextual_text` only
- [x] `metadata.enabled: false` still embeds; no embedding keys in config or `.env`
- [x] Console is counts + sample, not 500 vectors
- [ ] WHO and one Healthy People scrape produce embeddings in Docker without an embedding API key
- [x] Unit tests do not require a live model download

## Open Questions

- Better default retrieval model (`bge-small-en-v1.5` vs MiniLM) — MiniLM locked for CPU/image size
- Torch CPU image size — pin a CPU wheel in Docker if the default torch install is too large
- Store slice will persist `{chunk_id, document_id, text, embedding, metadata, provenance}`

---

## Changelog

| Version | Date | Change | Reason |
|---------|------|--------|--------|
| 1.0 | 2026-09-15 | Initial brief | Product spec §9; local sentence-transformers; skip validation; embed contextual_text |
| 1.1 | 2026-09-15 | No operator provider/key; drop validation stage | Local default; metadata tests stand in for §8 |
| 1.2 | 2026-09-15 | Remove embedding config knobs; drop §8 | Operator-config not needed; validation not a requirement |

---

*Brief created with SDD 6.0 - Ready to code!*
