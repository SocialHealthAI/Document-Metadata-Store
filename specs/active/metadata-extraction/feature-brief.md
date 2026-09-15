# Feature Brief: Metadata Extraction

**Task ID:** metadata-extraction
**Created:** 2026-09-14
**Status:** Implemented

---

## Problem Statement

Chunks are bounded retrieval units with headings, but they have no structured applicability tags. Embedding will vectorize `contextual_text` for semantic search; operators still need **filterable** fields so a record can be judged as about a place, a population, a time, and a topic. This slice extracts those fields per chunk without writing to the metadata store, embedding, or modifying source PDFs.

## Target Users

The same operators as load through chunk: they drop PDFs in `documents/`, run one command, and need a compact per-document metadata recap (not 500 lines) before embed and store.

## Core Requirements

### Must Have

- [x] Run **in the same process/CLI** after chunking (`python -m document_metadata_store` / `docker compose up`) — not a separate command
- [x] Honor `metadata.enabled`; when `false`, skip extraction and print that metadata was skipped (chunking still runs)
- [x] This version’s schema is **four fields only:** `topic`, `geography`, `population`, `time_period`. Extra stub fields (`evidence_type`, `organization`, …) are **out of this schema** until a later version
- [x] **`topic` is one field** whose values may be social factors (housing, income, discrimination, …) **or** health conditions (diabetes, maternal mortality, …). Do not split into two fields
- [x] Each field is a **list of 0..n values**. Empty list = **Unknown**. Do not invent a value to fill a slot
- [x] Values are **free-text phrases** grounded in the chunk (including its heading prefix). No controlled vocabulary in this slice
- [x] Extract **per chunk** with the LLM (same Anthropic adapter as preprocess/structure). Do not run a separate document/section extraction pass. **Batch** chunks into LLM requests (`processing.batch_size`, default 50)
- [x] Each value carries **provenance:** `explicit` | `inherited` | `inferred` | `unknown`, plus optional confidence. `inherited` means the value comes from heading/document context in `contextual_text`, not from a prior pipeline pass
- [x] Subject-independent: field names, prompts, and schema path live in `metadata_schema.yaml` / `config.yaml` `metadata.schema` — not `if subject == …`
- [x] Never modify original source files; never mutate chunks’ original/contextual text
- [x] Console: **per-document histograms + a small sample**, not one line per chunk. See Console below
- [x] Prove against the WHO 2025 PDF **and** one Healthy People scrape (heading-light implicit title)

### Nice to Have

- [x] Batched LLM HTTP calls (many chunks per request) while still extracting independently per chunk
- [ ] Cheap date/place regex as a fallback when no LLM key (otherwise all fields stay Unknown)
- [ ] Persist an inspectable metadata dump (product spec §18)
- [ ] Controlled vocabularies and aliases (deferred until store **filters** exist)

## Technical Approach

After `chunk_documents`, a `MetadataExtractor` walks each `ChunkedDocument`. For every chunk it sends **`contextual_text`** (headings + body) to the LLM and asks for the four list fields plus provenance. Copy-on-write: emit an enriched record wrapping the frozen `Chunk`; do not mutate the chunker output.

**Embeddings (later) use `contextual_text`.** Metadata lists stay beside the vector for filter/rank (product spec §9). Synonymy such as US / USA / United States is a property of **semantic search over chunk prose**, not of cosine distance between metadata tag strings. This slice therefore does **not** embed field values and does **not** ship a vocabulary; free-text tags are for inspection and for a future filter layer.

No LLM key or `metadata.enabled: false`: skip or leave fields empty/Unknown; do not fail the batch. Per-chunk LLM failure → that chunk’s fields Unknown; continue.

Schema file `metadata_schema.yaml` is the source of field names and types (`list` of strings, not required). Engine is generic over whatever fields the schema lists; this version’s file contains only the four fields.

**Patterns to Follow:**

- Same CLI chain: `cli.py` load → preprocess → structure → chunk → **extract metadata**
- Protocol + run/outcome + continue-on-per-file-failure (`pipeline/chunker.py`)
- Config YAML + env (`config.py`); `config.yaml` already has `metadata.enabled` and `metadata.schema`
- Existing Anthropic JSON helper (`preprocess/llm.py`): optional, fail-soft
- Frozen `Chunk`; copy-on-write enriched records
- Canonical docs: product spec §7–§7.2 and §9, `doc/architecture.md` handoff table

**Key Decisions:**

- **Same CLI:** extract after chunk in one run
- **Lists, not singletons:** a chunk may mention several geographies or years
- **One topic field:** social factors and health conditions share `topic`
- **Free-text this slice:** no vocab; do not treat embedding synonymy as a substitute for later filter aliases
- **Per-chunk LLM:** no inherit-first pass; headings already sit in `contextual_text`
- **No validation stage:** provenance is classified here; required fields / vocab are not a pipeline step
- **Histogram console:** WHO ~500 chunks must not dump every record

### Extraction (locked)

```text
0. If metadata.enabled is false → skip; console says skipped
1. Load schema from metadata.schema (four list fields this version)
2. For each batch of chunks (`processing.batch_size`), prompt LLM with those chunks' contextual_text
   - return JSON: chunk_id → field → [{value, origin, confidence?}, ...]
   - origin in explicit | inherited | inferred | unknown
   - topic values may be social factors or health conditions
   - only values grounded in the supplied text; else omit (Unknown)
3. No LLM / parse failure → split the batch and retry; a single-chunk failure stays Unknown; continue
4. Do not rewrite original_text or contextual_text
```

### Console (histogram + sample)

```text
document-metadata
  records: 519  with_any_field: 480  llm_failed: 2

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             records: 519
             topic:        housing (41), income (28), diabetes (6), …
             geography:    Kenya (12), Brazil (9), global (80), …
             population:   adults (22), children (11), …
             time_period:  2020-2023 (18), 2015 (7), …
             origins:      explicit=612 inferred=40 inherited=88 unknown=44
             sample:
               c1   topic=[housing instability]  geo=[Kenya]  pop=[]  time=[2022]
               c41  topic=[definitions]          geo=[]       pop=[]  time=[]
```

Always print **counts and top-N histogram terms** per field, plus a **sample of tagged chunks** (original `cN` index). If none are tagged, sample the first N. Sample size = `preview_blocks` when > 0, otherwise **5**. Do not print one line per chunk. Do not dump full chunk text unless preview is on (then sample may include a truncated `contextual_text`).

Failed LLM batches are **split in half and retried** down to one chunk so a truncated 50-chunk response does not wipe a whole document.

## Next Actions

1. [x] Models: per-value provenance + enriched chunk/document types (lists on the four fields)
2. [x] Load `metadata_schema.yaml` (list fields); wire `MetadataConfig` from `config.yaml` / env
3. [x] LLM extractor over `contextual_text`; batched; fail-soft; `metadata.enabled` short-circuit
4. [x] Wire after chunk in CLI; histogram + sample console
5. [x] Tests: list cardinality, mixed topic (social + health), empty/Unknown, skip when disabled, WHO + Healthy People proof
6. [x] Update `doc/architecture.md`, `doc/usage.md`, `doc/installation.md`, `README.md`, `specs/index.md`

## Success Criteria

- [x] One command loads through chunk then attaches metadata; source PDFs unchanged
- [x] Schema-driven four list fields; topic may hold both a social factor and a health condition on the same chunk
- [x] No invented fillers; missing → empty / Unknown
- [x] Console is a histogram + sample, not 500 lines
- [x] WHO and one Healthy People scrape produce tagged records when LLM is configured; without a key, run still succeeds with Unknown
- [x] `metadata.enabled: false` skips extraction

## Open Questions

- Time-period normalization (raw `2020-2023` vs structured start/end) — free-text strings this slice
- Batch size for Anthropic when WHO is ~500 chunks — locked: `processing.batch_size` (default 50)
- When store filters land: aliases/vocab for `United States` / `USA` / `US` as filter keys — **not** by embedding the tag strings. Tracked in `doc/architecture.md` **Futures** (metadata controlled vocabularies)

---

## Changelog

| Version | Date | Change | Reason |
|---------|------|--------|--------|
| 1.0 | 2026-09-14 | Initial brief | Product spec §7; locked lists, per-chunk LLM, free-text, histogram console |
| 1.1 | 2026-09-14 | Vocab deferred to architecture Futures | Free-text lists this slice; filter aliases later |
| 1.2 | 2026-09-14 | Batch LLM calls; implemented | processing.batch_size; histogram console |
| 1.3 | 2026-09-15 | Split-retry failed batches; sample tagged chunks | WHO/HP log: llm_failed hid later tags |
| 1.4 | 2026-09-15 | Drop metadata-validation follow-on | Extraction tests stand in; pipeline is extract → embed |

---

*Brief created with SDD 6.0 - Ready to code!*
