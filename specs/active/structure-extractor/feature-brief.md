# Feature Brief: Structure Extraction

**Task ID:** structure-extractor
**Created:** 2026-09-13
**Status:** Implemented (heading filters v1.2)

---

## Problem Statement

Preprocess marks keep/exclude on blocks but does not build an outline. Chunking and metadata need a section → subsection → paragraph tree so knowledge units inherit headings and parent context. This slice promotes kept blocks into that tree without deleting source data, flattening pages, or embedding excluded front matter.

## Target Users

The same operators as load/preprocess: they drop PDFs in `documents/`, run one command, and need to see the retained outline (section titles and nesting) before later stages chunk and embed.

## Core Requirements

### Must Have

- [x] Run **in the same process/CLI** as load and preprocess (`python -m document_metadata_store` / `docker compose up`) — not a separate command
- [x] Consume `PreprocessedDocument`; walk **kept** blocks only for the retained tree
- [x] **Omit excluded blocks** from the section tree (they stay on the annotated preprocess tree for inspection; do not attach an `excluded` branch)
- [x] Identify sections, subsections, headings, and paragraph groups; preserve parent/child relationships
- [x] Promote tables, lists, and captions **only when load already set those kinds** — do not invent `table` / `list_item` / `caption`
- [x] **Do not rely on `kind == heading_candidate`** (WHO extract is almost all `text`)
- [x] **Hybrid heading promotion:** deterministic rules first (numbering, Chapter/Part, retained titles, style hints, preprocess heading-like); send leftover heading-like lines to the existing Anthropic hook (`LLM_PROVIDER=anthropic`, default `LLM_MODEL=claude-sonnet-5`). No key → rules only. LLM failure does not fail the batch
- [x] **No headings after rules+LLM:** one implicit section whose title is `metadata.title`, else first kept page-1 text, else `"untitled"`
- [x] **Under-nest.** Prefer a flatter tree over inventing false subsections. Uncertain leftover → not a heading
- [x] Subject-independent: heading patterns and prompts in config/code defaults, not `if subject == …`
- [x] Never modify original source files; never delete preprocess annotations
- [x] Console: per processed document, section/subsection counts and an **outline of section titles** (depth, heading, start `block_id`). Do not dump every paragraph. Preview (when `PREVIEW_BLOCKS` > 0) can sample nodes
- [x] Prove against the WHO 2025 PDF (nested Chapter/Part/Recommendation outline on kept content) **and** one Healthy People scrape PDF (implicit title section)

### Nice to Have

- [ ] Infer table/list/caption kinds that load did not emit (deferred; quality open from preprocess)
- [ ] Persist an inspectable dump of retained structure (product spec §18)
- [ ] Chunking (next slice)

## Technical Approach

After `preprocess_documents`, a `StructureExtractor` protocol walks kept `AnnotatedBlock`s in reading order and returns a `StructuredDocument` (copy; `Block` stays frozen). Heading candidates are the same conservative set preprocess uses, plus numbered patterns (`1.2`, `Chapter 3`, `Part 2`, `Recommendation 3.1`) and stronger style hints when present. Unclassified leftovers go to Anthropic as “heading or none” (optional level hint). A heading opens a node; following kept blocks attach until the next heading at the same or higher level. Numbered prefixes set depth; otherwise depth is conservative (new heading is a sibling unless numbering or a clear Part/Chapter/subsection cue says otherwise).

If no heading is confirmed, emit a single section from the document title and attach every kept block under it.

Chunking is not this slice. The tree is the input the chunker will walk (spec §6).

**Patterns to Follow:**

- Same CLI chain: `cli.py` load → preprocess → structure
- Protocol + run/outcome + continue-on-per-file-failure (`pipeline/preprocessor.py`)
- Config YAML + env (`config.py`); optional LLM already wired
- Console header / per-file / summary; opt-in preview (`console.py`)
- Locked load tree; preprocess keep/exclude; do not flatten
- Canonical docs: product spec §5 and §6.1–6.2, `doc/architecture.md` handoff table

**Key Decisions:**

- **Same CLI:** load then preprocess then structure in one run
- **Kept-only tree:** excluded blocks omitted from the outline (still present on the preprocess annotation)
- **Hybrid headings; leftovers to Anthropic:** rules for stable cases; LLM only on leftover heading-like lines (not all body blocks)
- **Implicit title section:** heading-light documents (Healthy People scrapes) become one section named from `metadata.title`
- **Under-nest:** missing a subsection is better than stuffing chapter body under a false heading
- **No invented kinds:** tables/lists/captions wait for a reliable load signal
- **Console outline:** titles and depth only; `named_excludes` stays on the preprocess step

### Heading promotion (locked)

```text
0. Take kept blocks only (disposition == keep), reading order
1. Cheap heading cues (no LLM)
   - named titles only when heading-shaped: Part/Chapter/Recommendation/Annex + number,
     optional capitalized title; reject sentence tails ("Part 1 comprises…")
   - reject running headers ("Part 1: Chapter 1"), parenthetical cross-refs, font junk,
     citations/dates, and first-on-page repeats seen on ≥3 pages
   - dotted numbers (1.2, 1.1.1)
   - retained titles (Executive summary, References, …) except one-word sentence leftovers
   - do not promote on heading_candidate or style alone
   - bare "PART N:" divider crumbs are not headings; bare Chapter/Recommendation/Annex may be
   - join letter-spaced labels (Cha PTeR → Chapter) and wrap the next short title lines
2. Weak cues only after a strong outline already exists
   - short "1. Title" (not citation marks, dates, or bibliography lines)
   - leftover title-like lines → Anthropic; no key / failure → body
   - once References/Bibliography opens, stop promoting numbered leftovers
3. If zero strong headings
   - one implicit section (Healthy People scrapes); ignore weak cues and leftovers
4. Nest
   - depth from numbering or Part/Chapter vs subsection cues
   - when unsure, sibling (under-nest)
5. Body under current section: consecutive text → paragraph group;
   table / list_item / caption only if load kind says so
```

### Console (extends load/preprocess)

```text
document-structure
  sections: 42  subsections: 18  implicit_title_sections: 0

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             sections: 28  max_depth: 3
             outline:
               1  "Executive summary"  p14-b3
               1  "Part 1: The state of social determinants of health equity"  p31-b2
               2    "Chapter 1: Inequities in today’s world"  p33-b2
               3      "1.2 Updates since the Commission …"  p40-b1

  processed  documents/healthy_people_scrape/Healthy People 2030 (in 2026), Poverty.pdf
             sections: 1  max_depth: 1  implicit: true
             outline:
               1  "Poverty"  p1-b1
```

Always print the **outline** (one line per section/subsection: depth, heading, start `block_id`). Do not dump paragraph text. Preview stays optional and truncated.

## Next Actions

1. [x] Models: `StructuredDocument` / `SectionNode` (heading, level, start `block_id`, children, body units)
2. [x] Heading promoter: rules → leftover Anthropic → implicit title fallback
3. [x] Nesting + attach kept body; omit excluded
4. [x] Wire after preprocess in CLI; console outline
5. [x] Tests: numbered nest, no-heading implicit title, excluded omitted; WHO + one Healthy People proof
6. [x] Update `doc/architecture.md`, `doc/usage.md`, `doc/installation.md`

## Success Criteria

- [x] One command loads, preprocesses, and builds a retained section tree; source PDFs unchanged
- [x] Excluded blocks do not appear as nodes in the tree
- [x] WHO kept content shows Chapter/Part (and numbered) nesting; not a single flat bag of paragraphs
- [x] A Healthy People scrape PDF is one implicit section titled from the document (or first-page) title
- [x] Run succeeds without `LLM_API_KEY` (rules + implicit title only)
- [x] Console prints the outline (depth + title + start block), not every paragraph

## Open Questions

- Depth heuristics for unnumbered title-case leftovers after LLM says “heading”
- When to split paragraph groups vs keep one body stream per section (chunker may split later)

---

## Changelog

| Version | Date | Change | Reason |
|---------|------|--------|--------|
| 1.0 | 2026-09-13 | Initial brief | Structure tree after preprocess |
| 1.1 | 2026-09-13 | Leftovers → Anthropic; implicit title section; omit excluded from tree | User direction |
| 1.2 | 2026-09-13 | Tighten heading cues: no running headers, citations, or sentence fragments | WHO 2025 outline review |
| 1.3 | 2026-09-13 | Strong outline first; heading-light PDFs stay one implicit section | HP scrape + WHO divider crumbs |

---

*Brief implemented with SDD 6.0.*
