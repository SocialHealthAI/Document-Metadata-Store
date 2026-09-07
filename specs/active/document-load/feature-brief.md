# Feature Brief: Document Load (PDFs first)

**Task ID:** document-load
**Created:** 2026-09-06
**Status:** Implemented (load slice)

---

## Problem Statement

The pipeline has no DocumentLoader. Nothing can preprocess, chunk, or store knowledge until documents are read into a normalized representation. This slice implements that first stage for text-extractable PDFs only, discovering files under `documents/` so later stages have a stable input contract.

## Target Users

Operators who drop source files into `documents/` (or `documents.input_path`) and run a processing pass. They need originals left untouched and enough document-level metadata and text to inspect what was loaded.

## Core Requirements

### Must Have

- [x] Discover files under `documents/` (config `documents.input_path`, env `DOCUMENTS_INPUT_PATH`; honor `documents.recursive`)
- [x] Load **all text-extractable PDFs** in that tree
- [x] Skip non-PDF files (DOCX, TXT, Markdown, HTML, other) without failing the run
- [x] Skip or flag scanned / image-only PDFs — **no OCR**
- [x] Convert each loaded PDF into the locked **block-level** normalized representation (see below) — not flat page text
- [x] Preserve available document-level metadata from the PDF Info dict (title, author, dates, language when present). Organization / source URL / version stay unset unless the PDF provides them. XMP not implemented.
- [x] Preserve reading-order blocks with `kind`, text, style hints (when the PDF provides them), and source location; keep all extracted content (reversible; do not drop regions at load)
- [x] Never modify the original source file
- [x] Expose a replaceable `DocumentLoader` interface so later formats plug in without changing callers
- [x] Record per-document load outcome (loaded, skipped unsupported, skipped image-only, failed) in memory for the later processing manifest
- [x] Write the locked **console summary** (see below) — not the full block tree
- [x] Prove the path against `documents/World report on social determinants of health equity, WHO 2025.pdf`

### Nice to Have

- [ ] Incremental skip of unchanged PDFs (fingerprint / `force=false`) — product spec §14, later slice
- [ ] Persist an inspectable dump of “original document structure” (product spec §18)
- [ ] Load DOCX, TXT, Markdown, HTML

## Technical Approach

Greenfield Python 3.12 package (matches the Dockerfile stub). A loader orchestrator discovers files from config/env, dispatches `.pdf` to a PDF implementation, and returns a `NormalizedDocument` tree. Other extensions are skipped with a recorded reason. Image-only or empty-text PDFs are flagged, not OCR’d.

This slice does **not** run preprocessing, section detection, or metadata schemas. It **does** emit the primitive tree those stages consume. Load must not flatten a PDF to a string; heading styles, tables, captions, and locations cannot be recovered later.

### Locked contract: `NormalizedDocument`

```text
NormalizedDocument
  metadata          # id, title, author, organization, publication_date,
                    # source, source_url, document_type, language, version
  source            # original path; read-only; never written back
  pages[]
    page_number
    blocks[]        # reading order
      block_id      # stable within the document for this load
      kind          # text | heading_candidate | paragraph | list_item | table | caption
      text
      style_hints   # font size, bold, indent — if the PDF provides them; omit if unknown
      location      # page, optional bbox
```

**Handoff (later slices, not this one):**

1. **Load** — format-specific extract → this tree; keep all blocks
2. **Preprocess** — mark exclude/keep on blocks; do not delete source data
3. **Structure extract** — promote heading candidates + order into a section tree
4. **Metadata / chunk** — walk that section tree; inherit document metadata from `NormalizedDocument.metadata`

`kind` values are **observables**, not a finished outline. `heading_candidate` means “looks like a heading from style or position,” not a confirmed section. Tables and captions are distinct blocks when the extractor can tell them apart; otherwise use `text` and do not invent structure.

### Locked contract: console output

The tree stays in memory. The console gets a **run header, one line-group per discovered file, and a summary**. Do not print block text or the full `NormalizedDocument`.

```text
document-load
  input_path: ./documents
  recursive: true

  loaded  documents/World report on social determinants of health equity, WHO 2025.pdf
          title: World report on social determinants of health equity
          pages: 148  blocks: 4201  text_chars: 512334

  skipped documents/notes.txt
          reason: unsupported_format (txt)

  skipped documents/scan.pdf
          reason: image_only

  failed  documents/broken.pdf
          error: <short message>

summary: discovered=4 loaded=1 skipped_unsupported=1 skipped_image_only=1 failed=0
```

| Field | When | Meaning |
|-------|------|---------|
| `input_path`, `recursive` | Always | Resolved discovery root from config/env |
| Relative path | Every discovered file | The document that was considered |
| `title` | Loaded, if PDF metadata has it | Human name; omit if unknown (do not invent) |
| `pages` | Loaded | Page count in the tree |
| `blocks` | Loaded | Block count (contract unit) |
| `text_chars` | Loaded | Total characters across block `text` (volume, not a dump) |
| `reason` / `error` | Skipped or failed | Why it was not loaded |
| `summary` | Always | Counts for the run |

`text_chars` and `pages` are both required on loaded files — pages for PDF shape, characters for how much text was extracted. A loaded PDF with `pages > 0` and `text_chars = 0` should have been treated as image-only, not loaded.

**Patterns to Follow:**

- No application-code patterns exist yet; this brief sets the first ones
- Config-driven paths (`config.yaml` + `.env`), subject-independent (no domain-specific branches)
- Pipeline stages as independently replaceable interfaces (`DocumentLoader` in `specs/Document Metadata Store.md` §19)
- Canonical docs: product spec §3, `doc/architecture.md`, `doc/usage.md`, `doc/installation.md`

**Key Decisions:**

- **Python 3.12:** Already chosen in the Dockerfile; lock it for this slice
- **Folder discovery, not a single-file loader:** All text PDFs under `documents/`; the WHO 2025 report is the acceptance fixture
- **Text extraction only:** No scanning/OCR; detect and skip/flag pages or files with no extractable text
- **Block-level load contract (locked):** Pages → reading-order blocks with kind, text, style hints, and location. Load does not build a section tree and does not flatten to page strings
- **Console (locked):** Input path, each discovered file, and for loads pages + blocks + text_chars + title if known. No block body unless `preview_blocks` / `--preview-blocks N` > 0 (first N blocks, truncated)
- **PDF library:** **pypdf** (user) plus **fonttools** (required to decode embedded CFF/Type1 fonts). Weaker layout than PyMuPDF; extract style hints (font size, bold from font name, indent) when visitors provide them. Prefer `text` over invented `table`/`caption`
- **Document ID:** SHA-256 hex of the resolved source path
- **Failed PDF:** Continue the batch; record `failed` + short error
- **heading_candidate:** Under-classify (larger-than-typical font and/or bold short lines)
- **Brief, not full SDD:** One stage, one format; the representation is fixed so later stages can be specified against it

## Next Actions

1. [x] Add a Python package skeleton and types for `DocumentLoader` + locked `NormalizedDocument` / page / block
2. [x] Implement PDF discovery + block-level extract (reading order, kinds, style hints, locations); skip non-PDFs and image-only PDFs
3. [x] Map PDF info/XMP (and filename fallbacks) into `NormalizedDocument.metadata` without writing the source
4. [x] Run against the WHO 2025 PDF and a small mix of skip cases (non-PDF, empty/image-only PDF); confirm blocks are not a single string per page
5. [x] Keep `doc/architecture.md`, `doc/usage.md`, and the product spec aligned with this contract

## Success Criteria

- [x] Every text PDF under `documents/` loads into `NormalizedDocument` without changing the file on disk
- [x] Each loaded document has pages of reading-order blocks (`block_id`, `kind`, `text`, `location`; `style_hints` when available)
- [x] The WHO 2025 report loads with extractable block text and populated document metadata (title/author/date where the PDF provides them)
- [x] Non-PDFs and image-only PDFs are skipped or flagged, and the run continues
- [x] Callers depend only on the `DocumentLoader` interface and this block-level contract
- [x] A load run prints the locked console summary (input path, per-file outcome, pages/blocks/text_chars for loads, run counts) and does not print block text

## Open Questions

- None blocking this slice. pypdf will often emit tables/captions as `text` (do not invent `table`/`caption` without a reliable signal).

---

## Changelog

| Version | Date | Change | Reason |
|---------|------|--------|--------|
| 1.0 | 2026-09-06 | Initial brief | PDF load, discover `documents/` |
| 1.1 | 2026-09-06 | Locked block-level `NormalizedDocument` contract | Later stages need kinds, style hints, and locations; flat page text is not enough |
| 1.2 | 2026-09-06 | Locked console summary (path, per-file outcome, pages/blocks/text_chars) | Operators need run visibility without dumping the in-memory tree |
| 1.3 | 2026-09-06 | Chose pypdf; Document ID = path SHA-256; continue on failure | User direction + remaining brief defaults |
| 1.4 | 2026-09-07 | Added fonttools dependency | pypdf warns and may mis-decode CFF Type1 fonts (e.g. WHO report BasicSans) without it |
| 1.5 | 2026-09-07 | Optional `--preview-blocks N` / `PREVIEW_BLOCKS` console sample | Inspect first N blocks without dumping the full tree |

---

*Brief created with SDD 6.0 - Ready to code!*
