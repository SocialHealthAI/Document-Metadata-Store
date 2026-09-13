# Architecture

**Status:** Load, preprocess, and structure extraction are implemented. Later stages still stubbed. Keep aligned with `specs/Document Metadata Store.md` and the active feature briefs.

## Futures

- **Configurable outline labels.** Structure extraction uses a hardcoded English-report prior (`part` / `chapter` / `recommendation` / `annex` / `appendix`, plus dotted `1.2.1` numbers). That is subject-independent and works for WHO-style reports and heading-light scrapes (one implicit title section). It is not universal: later corpora will need `Section` / `Article` / Roman parts / non-English labels (`Capítulo`, `Anexo`) without a code change. Move the named-label list and depths into configuration, the same way `section_aliases` already parameterizes preprocess. Do not add per-document or per-subject branches.

## Purpose

The Document Metadata Store converts documents into searchable, context-aware knowledge records. It is subject-independent. Domain behavior comes from configuration, metadata schemas, controlled vocabularies, and prompts.

## Central principle

Remove irrelevant content, preserve document structure, create meaningful knowledge units, and attach structured metadata that describes their applicability.

## Processing pipeline

```text
Document → Preprocessing → Structure Extraction → Context-Aware Chunking
        → Metadata Extraction → Metadata Validation → Embedding Generation
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
| MetadataExtractor / Chunker | Section tree + document metadata | Knowledge records |

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
| Chunker | Structural, context-aware knowledge units |
| MetadataExtractor | Configurable schema; inheritance; explicit/inherited/inferred/unknown |
| MetadataValidator | Required fields, types, vocabularies, conflicts |
| EmbeddingProvider | Vendor-agnostic embeddings with contextual text |
| MetadataStore | Persistent records; semantic + metadata retrieval; re-index |
| ManifestManager | Per-run audit trail |

## Deployment (intended)

Docker Compose hosts the application and any chosen metadata-store service. Provider implementations are swappable behind interfaces. Runtime is Python 3.12.

## Open

- Concrete embedding and store providers
- Inspection/API surface beyond the load/preprocess/structure console
- Chunking and later stages

Load extract uses **pypdf** plus **fonttools**. Preprocess uses configurable aliases plus an optional Anthropic adapter (`LLM_PROVIDER=anthropic`, default `LLM_MODEL=claude-sonnet-5`).
