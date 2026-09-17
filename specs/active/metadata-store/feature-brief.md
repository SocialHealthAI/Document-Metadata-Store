# Feature Brief: Metadata Store

**Task ID:** metadata-store
**Created:** 2026-09-16
**Status:** Implemented

---

## Problem Statement

Embeddings and metadata tags exist only in memory for one CLI run. Nothing persists a knowledge record, so an agent cannot retrieve by similarity plus filters. This slice writes each successful embedded chunk to a **local** store after embed, and ships a Python **`search()`** library that agents import. It does not add an HTTP server, an extra Compose service, or a store vocabulary.

## Target Users

- **Operators** who drop PDFs in `documents/` and run one command; they need a compact persist recap (counts + sample, not 500 records) and unchanged source files.
- **Agents / scripts** in the same environment that import `search()` against the persisted files (same MiniLM, optional metadata filters).

## Core Requirements

### Must Have

- [x] Run **in the same process/CLI** after embed (`python -m document_metadata_store` / `docker compose up`) — not a separate ingest command
- [x] Persist each successful embedded chunk as a knowledge record: **chunk id, document id, text (`contextual_text`), embedding (384-dim MiniLM), metadata lists, provenance**. Skip `embed_failed` chunks
- [x] **Local embedded** backend in the app process. Persist to a directory/volume. **No extra Compose vector-store service. No store URL or API key**
- [x] **`MetadataStore` protocol** so a later provider can be swapped. This slice implements **one** provider: Chroma `PersistentClient` (collection + persist path)
- [x] On reprocess of a document, **replace** that document’s records (delete-then-insert by `document_id`). Do not leave duplicate chunks. Skip-unchanged fingerprinting is **out of this slice**
- [x] Python library **`search(query, filters=None, k=8)`** that: embeds `query` with the same MiniLM; retrieves a similarity candidate pool; **OR within a field, AND across fields** on tag-list overlap; returns `{text, metadata, provenance, score}` — not raw vectors. Empty / Unknown tags on a record do **not** satisfy a required filter. Omit a filter field (or pass `[]`) to leave that axis unconstrained
- [x] Do **not** embed metadata tag strings or cosine them against the chunk vector. Do **not** expand synonyms inside `search()` (the caller builds the filter list; see `doc/usage.md`)
- [x] `time_period` values are already calendar years at ingest; a filter of `["2020"]` must match a chunk whose list includes `2020` (a former 2019–2022 span)
- [x] `metadata.enabled: false` still stores those chunks (empty tags); they only appear when the caller does not require those fields
- [x] Subject-independent: persist path, collection, and field names come from config/schema — not `if subject == …`
- [x] Never modify original source files; never mutate `original_text` / `contextual_text`
- [x] Console: **counts + persist path + collection + a small sample**, not one line per record. See Console below
- [ ] Prove against the WHO 2025 PDF **and** one Healthy People scrape (records persist; `search()` returns hits with provenance)

### Nice to Have

- [ ] Operator CLI wrapper around `search()` (agents import the function; CLI is inspect-only)
- [ ] Tag-overlap score boost (usage.md optional); cosine rank is enough this slice
- [ ] Incremental skip of unchanged documents (`processing.force` / fingerprint) — later
- [ ] HTTP search API — later (would make the image a long-running server)
- [ ] Inspectable dump file (product spec §18 is the console stages, including store)
- [ ] Processing manifest (product spec §16)

## Technical Approach

After `embed_documents`, a store writer walks each `EmbeddedDocument`. For every chunk with a 384-dim vector it upserts one record. Copy-on-write: do not mutate `EmbeddedChunk`. Re-running a document deletes existing ids for that `document_id` then inserts the new set.

**Provider:** `MetadataStore` protocol (`upsert_document`, `delete_document`, `query_candidates`). First implementation: Chroma `PersistentClient` at `metadata_store.persist_path` (default `./data/metadata-store`), collection `metadata_store.collection` (default `knowledge`). Chroma metadata is scalar; store tag lists and provenance as JSON on the record payload and **filter overlap in Python** after ANN retrieve (candidate pool: `max(k * 5, 50)`). Interface stays so Qdrant/LanceDB can replace Chroma later without changing `search()`.

**`search()`** lives in `document_metadata_store.store` (re-export from the package). It loads config, encodes `query` with `encode_texts`, asks the store for nearest neighbors, applies OR/AND list overlap, truncates to `k`. Tests inject a fake store + fake encode (no live Chroma/MiniLM required in unit tests).

Docker: mount the persist directory. Keep the image **one-shot ingest**; `search()` is in-process against those files, not a server.

**Patterns to Follow:**

- Same CLI chain: `cli.py` load → … → embed → **store**
- Protocol + run/outcome + continue-on-per-file-failure (`pipeline/embedder.py`)
- Config YAML + env (`config.py`); wire `metadata_store.persist_path` / `collection` (provider fixed this slice)
- Frozen wrap; do not mutate embedder output
- Compact console (`format_embed_run`): header, per-file counts, sample — never dump vectors
- Canonical docs: product spec §10–§12, §11 provenance, `doc/usage.md` Agent query, `doc/architecture.md` MetadataStore

**Key Decisions:**

- **Same CLI:** persist after embed in one run
- **Local Chroma files:** matches MiniLM (no extra service, no store API key)
- **Library `search()`, not HTTP:** agents import it; Compose stays one-shot
- **Filter in Python after ANN:** list overlap (OR/AND) is the product rule; do not depend on Chroma `where` for lists
- **No synonym expander in the store:** caller expands Ohio/OH; `search()` does exact string overlap on tags
- **Replace by document_id:** honor “obsolete records must be replaced”; fingerprint skip later
- **Histogram-style console:** WHO ~500 chunks must not print payloads

### Persist (locked)

```text
0. After embed, for each EmbeddedDocument:
   - delete existing records with that document_id
   - upsert each chunk that has dim=384 and not embed_failed
1. Record payload:
   - ids: chunk_id, document_id
   - text: contextual_text
   - embedding: 384 floats, model id + dim
   - metadata: topic, geography, population, time_period lists (values only for filters; keep origin on the record for provenance)
   - provenance: document title, source, source_url, version, section_heading, parent_heading, pages, start_block_id
2. Persist under metadata_store.persist_path; collection metadata_store.collection
3. Per-document store failure → that file failed; continue the batch
4. Do not rewrite original_text, contextual_text, or source PDFs
```

### `search()` (locked)

```text
search(query: str, filters: dict[str, list[str]] | None = None, k: int = 8) -> list[SearchHit]

1. Encode query with all-MiniLM-L6-v2 (same as ingest)
2. ANN candidate pool from the collection (not the section tree)
3. Keep a candidate if every present filter field overlaps (OR within list, AND across fields)
4. Rank remaining by cosine/distance; return top k as {text, metadata, provenance, score}
5. Do not return embeddings. Do not query headings as a tree.
```

### Console (counts + sample)

```text
document-store
  provider: chroma  collection: knowledge  path: data/metadata-store
  records: 519  upserted: 519  failed: 0

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             records: 519  upserted: 519  replaced: 519
             sample:
               c1   topic=[housing instability]  geo=[Kenya]  time=[2020, 2021]
               c41  topic=[]  geo=[]  time=[]
```

Always print **provider, collection, path, counts**. Sample size = `preview_blocks` when > 0, otherwise **5**. Do not print vector components. Do not print one line per record.

## Next Actions

1. [x] Models: `SearchHit` / provenance payload; `StoreConfig`; `MetadataStore` protocol
2. [x] Chroma PersistentClient adapter; upsert/replace by document_id; persist_path volume
3. [x] `search()` + OR/AND overlap filter; same MiniLM encode; injectable store/encode for tests
4. [x] Wire after embed in CLI; counts + sample console; Docker volume for persist dir
5. [x] Tests: persist skip failed embeds; replace on re-run; filter 2020 matches year list; empty tags miss required filter; console does not dump vectors
6. [x] Update `doc/architecture.md`, `doc/usage.md`, `doc/installation.md`, `README.md`, `specs/index.md`

## Success Criteria

- [x] One command loads through embed then persists records; source PDFs unchanged
- [x] Each stored chunk has text, 384-dim embedding, metadata lists, and provenance
- [x] `search("…", filters={"time_period": ["2020"]}, k=8)` can return a chunk tagged with 2020 from an expanded 2019–2022 span
- [x] No extra Compose service; no store API key; persist dir is a local volume
- [x] Console is counts + sample, not 500 records
- [ ] WHO and one Healthy People scrape produce stored records; `search()` returns citable hits
- [x] Unit tests do not require a live model download (inject encode); Chroma can be tmp-dir in integration tests

## Open Questions

- Candidate pool size (`max(k * 5, 50)`) may need a bump if filters are very selective — tune after WHO proof
- Second provider (Qdrant/LanceDB) — interface only this slice
- Manifest + incremental fingerprint — later slices

---

## Changelog

| Version | Date | Change | Reason |
|---------|------|--------|--------|
| 1.0 | 2026-09-16 | Initial brief | Product spec §10; local Chroma; library `search()`; locks from operator Q1=A Q2=library |

---

*Brief created with SDD 6.0 - Ready to code!*
