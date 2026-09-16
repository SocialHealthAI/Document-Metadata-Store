# Architecture

**Status:** Load, preprocess, structure extraction, context-aware chunking, metadata extraction, and embedding generation are implemented. The metadata store is still stubbed. Keep aligned with `specs/Document Metadata Store.md` and the active feature briefs.

## Futures

- **Configurable outline labels.** Structure extraction uses a hardcoded English-report prior (`part` / `chapter` / `recommendation` / `annex` / `appendix`, plus dotted `1.2.1` numbers). That is subject-independent and works for WHO-style reports and heading-light scrapes (one implicit title section). It is not universal: later corpora will need `Section` / `Article` / Roman parts / non-English labels (`Capítulo`, `Anexo`) without a code change. Move the named-label list and depths into configuration, the same way `section_aliases` already parameterizes preprocess. Do not add per-document or per-subject branches.
- **Metadata controlled vocabularies.** Extraction stores free-text lists (`topic`, `geography`, `population`) and **calendar years** on `time_period` (ranges such as 2019–2022 are expanded to each year so a filter of `["2020"]` overlaps the span). Semantic search uses the chunk embedding (`contextual_text`), not cosine on those tag strings. When metadata **filters** land in the store, grow a schema-file vocabulary (canonical ids + aliases, e.g. `US` ← United States / USA) from extraction histograms and existing codes (ISO 3166, SDoH/HP topic lists). Keep it in `metadata_schema.yaml`, not in application code. Do not block extraction on an empty vocab.
- **Wire references to text.** Bibliography/references are retained and chunked as their own section. In-text markers (`[12]`, author-year) stay raw in body chunks; there is no join to the matching bibliography entry. Later: resolve markers to retained reference chunks and store the link (schema list such as `sources`, and/or chunk-to-chunk ids) beside the vector. Do not treat this as topic/geography metadata or as cosine on tag strings. Do not block embed/store on unresolved cites.
- **Larger embedding models (dimension follows the model).** This version hardcodes `all-MiniLM-L6-v2`, which always emits **384** dimensions (the model’s pooling size, not an operator setting). Retrieval quality may improve with a larger checkpoint; that also grows image size, encode time, and stored vector width. Re-embed the corpus if the model changes, and persist `model` + `dim` on each record. Candidates to try later (local unless noted): `all-mpnet-base-v2` (768), `BAAI/bge-base-en-v1.5` (768), `BAAI/bge-large-en-v1.5` (1024), `intfloat/e5-base-v2` (768), `intfloat/e5-large-v2` (1024), `nomic-embed-text-v1.5` (768). API options if a vendor is added: OpenAI `text-embedding-3-small` (1536) / `text-embedding-3-large` (3072). Do not mix dimensions in one collection.

## Purpose

The Document Metadata Store converts documents into searchable, context-aware knowledge records. It is subject-independent. Domain behavior comes from configuration, metadata schemas, controlled vocabularies, and prompts.

## Central principle

Remove irrelevant content, preserve document structure, create meaningful knowledge units, and attach structured metadata that describes their applicability.

## Processing pipeline

```text
Document → Preprocessing → Structure Extraction → Context-Aware Chunking
        → Metadata Extraction → Embedding Generation
        → Metadata Store
```

Each stage has a single responsibility and is independently configurable.

## Load contract (`NormalizedDocument`)

DocumentLoader emits a block-level tree. It does not flatten to page strings and does not build a section outline.

```text
NormalizedDocument
  metadata          # id, title, author, organization, publication_date,
                    # source, source_url, document_type, language, version
  source            # original path; never written back
  pages[]
    page_number
    blocks[]        # reading order
      block_id
      kind          # text | heading_candidate | paragraph | list_item | table | caption
      text
      style_hints   # font size, bold, indent — when available
      location      # page, optional bbox
```

Preprocessing copies that tree into `AnnotatedBlock` values (`keep` | `exclude`, section type, classifier). Blocks are never deleted.

| Stage | Consumes | Produces |
|-------|----------|----------|
| DocumentLoader | Source file (read-only) | `NormalizedDocument` (all blocks kept) |
| Preprocessor | That tree | Same blocks, marked keep/exclude; exclusion reasons + locations |
| StructureExtractor | Kept blocks only | Section → subsection → paragraph tree (excluded omitted) |
| Chunker | Section tree | Context-aware chunks (original + heading prefix; sizes from config) |
| MetadataExtractor | Chunks + schema | List fields per chunk (topic, geography, population as free-text; time_period as calendar years, ranges expanded) + provenance |
| EmbeddingProvider | Enriched chunks | 384-dim MiniLM vectors from `contextual_text` (metadata lists unchanged) |

`kind` is an observable (`heading_candidate` means style/position suggests a heading). Confirmed sections are Structure Extraction’s job.

Cover (when configured): pages **before** the first Contents heading. No TOC → no cover marks.

References / bibliography / citations are **kept by default**. Operators may add `references` to `exclude_sections` to drop them.

TOC (when configured): the Contents page plus following pages that still contain TOC leader-dot lines. Chapter titles listed in the TOC stay `table_of_contents`, not live chapter spans.

## Components

| Component | Responsibility |
|-----------|----------------|
| DocumentLoader | Load PDF with **pypdf** into in-memory `NormalizedDocument`; console summary; optional first-N block preview |
| Preprocessor | Hybrid keep/exclude (rules, aliases, optional Anthropic LLM); mark blocks; log excluded section titles |
| StructureExtractor | Promote kept blocks into a nested outline after a strong Part/Chapter/dotted cue; leftover heading-like lines may use Anthropic; heading-light docs get one implicit title section; running headers, citations, and sentence fragments are not headings |
| Chunker | Split each section’s body on paragraph/sentence boundaries; prepend ancestor headings; do not merge across sections; tables/lists/captions stay one chunk |
| MetadataExtractor | Schema-driven lists per chunk from `contextual_text`; `time_period` expanded to calendar years; batched Anthropic calls; explicit/inherited/inferred/unknown; histogram console |
| EmbeddingProvider | Local sentence-transformers `all-MiniLM-L6-v2`; encodes `contextual_text`; not operator-configured |
| MetadataStore | Persistent records; semantic + metadata retrieval; re-index |
| ManifestManager | Per-run audit trail |

## Deployment (intended)

Docker Compose hosts the application and any chosen metadata-store service. Provider implementations are swappable behind interfaces. Runtime is Python 3.12.

## Open

- Concrete store provider
- Inspection/API surface beyond the load/preprocess/structure/chunk/metadata/embed console

Load extract uses **pypdf** plus **fonttools**. Preprocess uses configurable aliases plus an optional Anthropic adapter (`LLM_PROVIDER=anthropic`, default `LLM_MODEL=claude-sonnet-5`). Metadata extraction uses the same adapter in batches of `processing.batch_size` (default 50). Embeddings use local sentence-transformers `all-MiniLM-L6-v2` (384-dim, CPU) on `contextual_text`; the model is baked into the Docker image.
