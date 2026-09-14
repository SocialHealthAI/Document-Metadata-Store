# Feature Brief: Context-Aware Chunking

**Task ID:** context-aware-chunking
**Created:** 2026-09-14
**Status:** Implemented

---

## Problem Statement

Structure extraction builds a retained section tree but does not split it into retrieval units. Metadata and embeddings need bounded chunks that still carry section and parent headings, so a sentence like “This increased to 23% in 2022.” is stored with enough context to stand alone. This slice walks the tree and emits those chunks without LLM-written prose, flattening pages, or modifying source PDFs.

## Target Users

The same operators as load/preprocess/structure: they drop PDFs in `documents/`, run one command, and need to see chunk counts and a compact chunk list before later stages attach metadata and embed.

## Core Requirements

### Must Have

- [x] Run **in the same process/CLI** as load, preprocess, and structure (`python -m document_metadata_store` / `docker compose up`) — not a separate command
- [x] Consume `StructuredDocument`; walk each section’s **own body** then its children (preamble body is not lost under the parent heading)
- [x] Split on **logical boundaries** in order: section → paragraph `BodyUnit` → sentences when a paragraph exceeds `max_size`. Do not split at a fixed character offset when a boundary is available
- [x] **Configurable** `target_size`, `max_size`, `min_size`, `overlap` (already stubbed in `config.yaml`). Wire them through `config.py` / env. Defaults: 1000 / 1500 / 300 / 100
- [x] Size is **characters of original body**. The heading prefix does **not** count toward target/max/min/overlap
- [x] **Do not merge across section boundaries** even if a chunk is under `min_size`
- [x] `table` / `list_item` / `caption` `BodyUnit`s stay **one chunk** even when over `max_size`
- [x] Each chunk keeps: chunk id, document id, section id, section heading, parent heading/context, original text, contextual text (headings + original), source location (start/end `block_id` + pages)
- [x] **Context prefix is structural only** — ancestor headings + this section’s heading. Do not call an LLM to write new contextual prose (product spec §6.1)
- [x] Overlap is the last `overlap` characters of **original body** from the previous chunk **in the same section**
- [x] Subject-independent: sizes and strategy from config, not `if subject == …`
- [x] Never modify original source files; never mutate the structure tree
- [x] Console: per processed document, chunk count, then **one line per chunk** (id, section heading, original char count, start `block_id`). Do not dump full chunk text unless `--preview-blocks` / `PREVIEW_BLOCKS` > 0
- [x] Prove against the WHO 2025 PDF (many sections, nested headings on chunks) **and** one Healthy People scrape (implicit title section split by size/paragraphs)

### Nice to Have

- [ ] Token-based sizes (deferred; characters first, no tokenizer dependency)
- [ ] Persist an inspectable chunk dump (product spec §18)
- [ ] Metadata extraction (next slice)

## Technical Approach

After `extract_structures`, a `Chunker` protocol walks each `SectionNode` depth-first. For every node it packs that node’s `body` `BodyUnit`s into chunks, then recurses into `children`. Heading-only nodes with empty body emit nothing; children still inherit the parent heading in their context prefix.

Packing: append paragraph units until adding another would pass `target_size`, never past `max_size` unless the unit is unsplittable. A paragraph over `max_size` is split on sentence boundaries; a leftover shorter than `min_size` may join the next paragraph **in the same section**. Tables, list items, and captions are never split.

Each chunk stores original body separately from `contextual_text` (`Section: …` / `Subsection: …` lines, then original text). Embeddings (later) should use `contextual_text`. Chunk ids are deterministic (`{document_id}:{section_id}:c{n}`).

No embeddings, store writes, or metadata schema in this slice.

**Patterns to Follow:**

- Same CLI chain: `cli.py` load → preprocess → structure → chunk
- Protocol + run/outcome + continue-on-per-file-failure (`pipeline/structure.py`)
- Config YAML + env (`config.py`); `config.yaml` already has a `chunking:` stub
- Console header / per-file / summary; opt-in preview (`console.py`)
- Frozen `Block`; copy-on-write chunk records; do not flatten
- Canonical docs: product spec §6.1–6.2, `doc/architecture.md` handoff table

**Key Decisions:**

- **Same CLI:** load then preprocess then structure then chunk in one run
- **Characters, not tokens:** measure original body with Python `len`
- **Prefix excluded from size:** headings are retrieval context, not packing budget
- **No cross-section merge:** mixed headings would break spec §6.1
- **Atomic non-paragraph units:** preserve tables/lists/captions even when large
- **No LLM context:** spec forbids generated prose
- **Console list:** id + heading + size + start block; preview can sample `contextual_text`

### Chunk packing (locked)

```text
0. Walk StructuredDocument depth-first
1. For each SectionNode, chunk its body, then children
2. Context prefix = ancestor headings + this heading (not counted in size)
3. Paragraph BodyUnits
   - pack while original chars ≤ target_size; never exceed max_size if a split exists
   - paragraph > max_size → split on sentences; if there is no sentence boundary, wrap on whitespace at max_size
   - remainder < min_size → attach to next paragraph in this section if that stays ≤ max_size
4. table / list_item / caption → one chunk, even if > max_size
5. Same-section overlap: last `overlap` chars of previous original body
6. Empty body → no chunk (children still processed)
7. Heading-light implicit section (Healthy People) uses the same packer
```

### Console (extends structure)

```text
document-chunk
  chunks: 84  oversized_atomic: 1

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             chunks: 61  max_chars: 1482
             chunks:
               c1  "Executive summary"  912  p14-b4
               c2  "1.1.1 Definitions"  1104  p36-b44

  processed  documents/healthy_people_scrape/Healthy People 2030 (in 2026), Poverty.pdf
             chunks: 4  max_chars: 1401
             chunks:
               c1  "Poverty"  1002  p1-b1
```

Always print the **chunk list** (one line per chunk: id, section heading, original char count, start `block_id`). Do not dump original/contextual text unless preview is on.

## Next Actions

1. [x] Models: `Chunk` / `ChunkedDocument` (ids, headings, original + contextual text, locations)
2. [x] Wire `ChunkingConfig` from `config.yaml` / env
3. [x] Packer: section walk, paragraph/sentence split, atomic table/list/caption, overlap
4. [x] Wire after structure in CLI; console chunk list
5. [x] Tests: nest context prefix, oversize paragraph split, atomic table, no cross-section merge, implicit-title HP, WHO proof
6. [x] Update `doc/architecture.md`, `doc/usage.md`, `doc/installation.md`

## Success Criteria

- [x] One command loads, preprocesses, extracts structure, and emits chunks; source PDFs unchanged
- [x] Every chunk has section heading + parent context; original text is unmodified body
- [x] WHO chunks inherit nested Chapter/Recommendation headings; none are a single whole-document blob
- [x] A Healthy People scrape yields multiple chunks under the implicit title when the body exceeds `target_size`
- [x] Oversized tables (when load emitted `table`) remain one chunk; oversized paragraphs split on sentences
- [x] Console prints the chunk list (id + heading + size + start block), not every paragraph
- [x] Sizes honor `config.yaml` `chunking:` values

## Open Questions

- Sentence splitter quality on PDF line-wrap (period + space, then whitespace wrap at max_size)
- Whether overlap should also include the heading prefix (locked: original body only)

---

## Changelog

| Version | Date | Change | Reason |
|---------|------|--------|--------|
| 1.0 | 2026-09-14 | Initial brief | Product spec §6; locked size/atomic/console answers |
| 1.1 | 2026-09-14 | Map chunk start blocks; wrap unsplittable oversize text | WHO chunk list review |

---

*Brief created with SDD 6.0 - Ready to code!*
