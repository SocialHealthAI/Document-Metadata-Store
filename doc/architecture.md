# Architecture

**Status:** Active for the load contract; other stages still stubbed. Keep aligned with `specs/Document Metadata Store.md` and `specs/active/document-load/feature-brief.md`.

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

| Stage | Consumes | Produces |
|-------|----------|----------|
| DocumentLoader | Source file (read-only) | `NormalizedDocument` (all blocks kept) |
| Preprocessor | That tree | Same blocks, marked keep/exclude; exclusion reasons + locations |
| StructureExtractor | Kept (and available excluded) blocks | Section → subsection → paragraph tree |
| MetadataExtractor / Chunker | Section tree + document metadata | Knowledge records |

`kind` is an observable (`heading_candidate` means style/position suggests a heading). Confirmed sections are Structure Extraction’s job.

## Components

| Component | Responsibility |
|-----------|----------------|
| DocumentLoader | Load PDF with **pypdf** into in-memory `NormalizedDocument`; console summary; optional first-N block preview |
| Preprocessor | Configurable include/exclude of non-knowledge sections (mark blocks; do not delete) |
| StructureExtractor | Promote blocks into sections, headings, tables, figure captions, lists |
| Chunker | Structural, context-aware knowledge units |
| MetadataExtractor | Configurable schema; inheritance; explicit/inherited/inferred/unknown |
| MetadataValidator | Required fields, types, vocabularies, conflicts |
| EmbeddingProvider | Vendor-agnostic embeddings with contextual text |
| MetadataStore | Persistent records; semantic + metadata retrieval; re-index |
| ManifestManager | Per-run audit trail |

## Deployment (intended)

Docker Compose hosts the application and any chosen metadata-store service. Provider implementations are swappable behind interfaces. Runtime for the load slice is Python 3.12.

## Open

- Concrete embedding and store providers
- Inspection/API surface beyond the load console

Load extract uses **pypdf** plus **fonttools** so embedded CFF/Type1 fonts decode correctly. Font size, bold (from font name), indent, and bbox come from text visitors when present. Tables and captions are usually `text`; do not invent those kinds without a reliable signal.
