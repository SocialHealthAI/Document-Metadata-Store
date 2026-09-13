# Feature Brief: Document Preprocessing

**Task ID:** document-preprocessing
**Created:** 2026-09-07
**Status:** Implemented

---

## Problem Statement

Load keeps every block. Knowledge retrieval should not embed cover pages, TOC, foreword, acknowledgements, or similar administrative material — but those regions must remain in the tree so rules can change and the document can be reprocessed. **References and citations stay by default** (they are knowledge). This slice marks keep/exclude on the loaded `NormalizedDocument` without deleting blocks or modifying source files.

## Target Users

The same operators as document-load: they drop PDFs in `documents/`, run one command, and need to see what was kept vs excluded before later stages chunk and embed.

## Core Requirements

### Must Have

- [x] Run **in the same process/CLI** as load (`python -m document_metadata_store` / `docker compose up`) — not a separate command
- [x] Honor `preprocessing.enabled`; when `false`, mark all blocks keep and skip classification
- [x] Configurable `exclude_sections` (functional types, not hardcoded English). Default includes spec §4.1 types such as cover, foreword, acknowledgements, table of contents, list of figures/tables, abbreviations, index. **Do not** exclude executive summary or references/citations unless configured
- [x] **Hybrid classification:** cheap deterministic rules first; LLM only on a small set of heading-like lines; alias matching when no LLM key
- [x] Identify section **spans** (heading-like start → next heading-like start); mark every block in an excluded span
- [x] **Mark, do not delete.** Record for each excluded block: content (the block itself), reason, rule or classifier id, location (`block_id` + page/bbox)
- [x] Subject-independent: synonyms and prompts live in config, not `if subject == …`
- [x] Vendor-agnostic LLM interface; **first adapter is Anthropic** (`LLM_PROVIDER=anthropic`, default `LLM_MODEL=claude-sonnet-5`); continue the run if LLM fails (fall back to aliases; do not fail the whole batch)
- [x] **Cover = pages until Contents:** when `cover` is in `exclude_sections`, mark all blocks on pages **before** the Contents / table-of-contents heading as `cover` (not a title-text span). The Contents page is `table_of_contents`, not cover
- [x] Console: per loaded document, counts kept / excluded / classified-by-rule / classified-by-llm; **log each excluded section’s title** (heading text that opened the span) plus functional type; preview (when `PREVIEW_BLOCKS` > 0) shows keep/exclude on sampled blocks
- [x] Never modify original source files
- [x] Prove against the WHO 2025 PDF: pages before Contents excluded as cover; TOC, foreword, acknowledgements excluded by default; executive summary **and references** retained

### Nice to Have

- [ ] LLM classification of ambiguous heading-like lines that aliases miss (core hybrid already requires the hook; tuning quality is nice-to-have)
- [ ] Persist an inspectable dump of excluded vs retained structure (product spec §18)
- [ ] Image interpretation of figures (out of scope; captions only when load emitted them)
- [ ] Full section tree (Structure Extraction)

## Technical Approach

After `load_documents`, a `Preprocessor` protocol consumes each `NormalizedDocument` and returns the same pages with annotated blocks (copy; `Block` stays frozen). Cheap rules tag running headers, roman folio lines (`iii`, `iv`), and TOC leader-dot lines. Remaining short/heading-like lines are classified against `exclude_sections` via a small alias table, then an LLM if a provider is configured. A match opens a span until the next heading-like line; blocks in that span inherit the section type. Structure Extraction is not this slice.

**Patterns to Follow:**

- `DocumentLoader` Protocol + `LoadRun` / `FileOutcome` + continue-on-per-file-failure (`pipeline/loader.py`)
- Config YAML + env (`config.py`); preprocessing keys already stubbed in `config.yaml`
- Console header / per-file / summary; opt-in preview (`console.py`)
- Locked load tree: do not flatten; do not rely on `kind == heading_candidate` (WHO extract is almost all `text`)
- Canonical docs: product spec §4 and §4.5–4.6, `doc/architecture.md` handoff table

**Key Decisions:**

- **Same CLI:** load then preprocess in one run
- **Hybrid, not LLM-only:** rules + aliases for cheap/stable cases; LLM for terminology variants on heading-like lines only (not 10k body blocks)
- **Spans, not a section tree:** preprocess assigns keep/exclude; Structure Extraction builds outline later
- **Annotation via copy:** e.g. `AnnotatedBlock` wrapping `Block` with `disposition: keep|exclude`, `exclude_reason`, `classifier` (`rule:…` | `alias:…` | `llm:…`)
- **LLM optional; first adapter Anthropic:** `LLM_PROVIDER=anthropic`, default `LLM_MODEL=claude-sonnet-5`, `LLM_API_KEY`. Model id comes from env/config (that default is documented, not the only allowed value). No key → alias/rules only
- **Cover = pages until Contents:** exclude every block whose `location.page` is **less than** the page of the first Contents / `table_of_contents` heading. Image-only pages in that range have no blocks (nothing to mark). **No TOC:** skip cover-by-pages entirely — do not invent a cover span, do not exclude page 1 just because it looks like a title, do not exclude the whole document. Other exclude types (foreword, acknowledgements, …) still apply. References/citations are **not** in the default exclude list
- **Heading-like: under-span.** Prefer missing an exclude heading over treating chapter body as a heading. Conservative candidates only (short lines, `heading_candidate`, or strong TOC/front-matter patterns). If classification is `none` or uncertain, **keep**. Never let an exclude span run through “Chapter 1” / “Part 1” / “Executive summary” unless that type is itself in `exclude_sections`
- **Console excluded titles:** log the heading that opened each excluded span (type + text + start block), not every excluded paragraph
- **Figures/tables:** honor `tables.preserve` (default keep table-like blocks); `figures.mode: captions_only` keeps caption-like text when detectable — do not invent `caption` kinds load did not emit; no OCR

### Hybrid classifier (locked)

```text
0. Cover (if cover ∈ exclude_sections)
   - find first Contents / table_of_contents heading (alias or LLM)
   - exclude all blocks on earlier pages as cover (title = document title or first page-1 text)
   - if Contents not found (no TOC), skip cover-by-pages: no cover marks, no cover title in the console
1. Cheap rules (no LLM)
   - repeated running-header lines
   - standalone roman / dotted TOC leader lines
2. Heading-like candidates (under-span)
   - short lines, heading_candidate kind, or strong TOC/front-matter patterns
   - do not treat long prose or chapter openings as candidates
   - when unsure, do not open or extend an exclude span
3. Classify candidate against exclude_sections
   - alias table in config (optional `references` ← bibliography, works cited — used only when `references` is in `exclude_sections`)
   - else Anthropic `claude-sonnet-5` (or configured LLM_MODEL): which configured type, or none?
   - none / uncertain → keep (do not exclude)
4. Span: from this candidate through the block before the next heading-like line
   - stop an exclude span if the next candidate is a retained section (e.g. Executive summary, Chapter, Part, References)
5. Mark exclude or keep; never drop the block
```

### Console (extends load)

```text
document-preprocess
  enabled: true
  exclude_sections: cover, foreword, acknowledgements, table_of_contents, …

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             kept: 8120  excluded: 2237  by_rule: 400  by_alias: 1200  by_llm: 637
             excluded_sections:
               cover                 "World report on social determinants of health equity"  p1-b1
               table_of_contents     "Contents"  p5-b2
               foreword              "Foreword"  p7-b2
               acknowledgements      "Acknowledgements"  p8-b2
             preview (first 5 of 10357):
               p1-b1  text  exclude  cover  World report on
               p5-b2  text  exclude  table_of_contents  Contents
               p7-b2  text  exclude  foreword  Foreword
```

Always print **excluded section titles** (one line per excluded span: type, heading text, start `block_id`). Do not dump every excluded body block. Preview stays optional and truncated.

## Next Actions

1. [x] Extend models + `PreprocessingConfig` (parse existing YAML; add `cover` to default excludes; alias map in config)
2. [x] Implement `Preprocessor` protocol: rules → aliases → optional Anthropic LLM → conservative spans → annotated copy
3. [x] Wire after load in CLI; console keep/exclude counts **and excluded section titles**
4. [x] Tests: generated PDF with Foreword/Contents/Executive summary; no-LLM alias path; enabled=false pass-through
5. [x] WHO 2025 proof + update `doc/architecture.md`, `doc/usage.md`, `doc/installation.md`

## Success Criteria

- [x] One command loads then preprocesses; source PDFs unchanged
- [x] Excluded blocks still present with reason, classifier, and location
- [x] Default config excludes TOC/foreword/acknowledgements-style spans and does not exclude executive summary or references/citations
- [x] Run succeeds without `LLM_API_KEY` (alias/rules only)
- [x] Console reports kept/excluded counts **and each excluded section title**; preview can show disposition
- [x] WHO fixture shows those default excludes in a real extract

## Open Questions

- `figures.mode` / table detection quality until Structure Extraction promotes kinds

---

## Changelog

| Version | Date | Change | Reason |
|---------|------|--------|--------|
| 1.0 | 2026-09-07 | Initial brief | Hybrid preprocess after load |
| 1.1 | 2026-09-07 | Log excluded section titles | Operator visibility |
| 1.2 | 2026-09-07 | First LLM = Anthropic; heading-like under-span | User direction |
| 1.3 | 2026-09-07 | Default model `claude-sonnet-5`; cover = pages until Contents | User direction |
| 1.4 | 2026-09-07 | No TOC → no cover-by-pages | Under-span; do not invent a cover |
| 1.5 | 2026-09-08 | Implemented: TOC continues through leader-dot pages; running-header repeats do not open new spans; `forward` is exact-match only | WHO extract: TOC chapter lines and prose “forward.” were over-spanning |
| 1.6 | 2026-09-09 | Keep references/citations by default; optional exclude via `exclude_sections` | Citations are knowledge, not administrative noise |

---

*Brief implemented with SDD 6.0.*
