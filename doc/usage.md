# Usage

**Status:** Load, preprocess, structure extraction, and context-aware chunking run in one command. Later stages are not implemented.

## Intended workflow

1. Place documents in `documents/` (or the path set in `config.yaml` / `DOCUMENTS_INPUT_PATH`).
2. Configure preprocessing, chunking, metadata, embeddings, and store in `config.yaml`.
3. Point `metadata.schema` at a subject-specific `metadata_schema.yaml`.
4. Run a processing pass (command TBD).
5. Inspect the processing manifest and intermediate results before relying on stored records.

## Processing modes

- **Standard:** load → preprocess → structure → chunk → extract metadata → validate → embed → store
- **Metadata-disabled:** load → preprocess → structure → chunk → embed → store

Preprocessing and context preservation remain available when metadata extraction is off.

## Incremental and forced runs

- `processing.force: false` — skip unchanged documents; process new and changed ones
- `processing.force: true` — reprocess all applicable stages and replace obsolete records

Configuration changes should be able to trigger reprocessing when needed.

## Load output

A successful load produces an in-memory `NormalizedDocument`: document-level metadata plus pages of reading-order blocks (`kind`, text, style hints, location). That tree is the “original document structure” inspection surface. Later stages mark exclusions and build a section tree from these blocks; they do not re-parse a flattened PDF string.

### Console (load step)

The console shows discovery settings, each file considered, and a count summary. It does **not** print block text unless preview is enabled.

```text
document-load
  input_path: ./documents
  recursive: true

  loaded  documents/World report on social determinants of health equity, WHO 2025.pdf
          title: World report on social determinants of health equity
          pages: 248  blocks: 10376  text_chars: 657650

  skipped documents/notes.txt
          reason: unsupported_format (txt)

summary: discovered=2 loaded=1 skipped_unsupported=1 skipped_image_only=0 failed=0
```

### Console (preprocess step)

After load, the same command prints keep/exclude counts and each excluded section title:

```text
document-preprocess
  enabled: true
  exclude_sections: cover, foreword, acknowledgements, table_of_contents, …

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             kept: 8120  excluded: 2237  by_rule: 400  by_alias: 1200  by_llm: 0
             excluded_sections:
               cover                 "World report on social determinants of health equity"  p1-b1
               table_of_contents     "Contents"  p5-b2
               foreword              "Foreword"  p7-b2
```

Cover is pages before Contents when a TOC heading exists. No TOC means no cover marks. References and citations are **kept by default**; add `references` to `exclude_sections` only if you want them dropped. LLM classification is optional (`LLM_API_KEY`); without a key, aliases and rules still run.

Always print **excluded section titles** (one line per excluded span: type, heading text, start `block_id`). If a document has no named front-matter spans (typical of short web-print PDFs), the line is `excluded_sections: (none)`. After the per-file list, `named_excludes:` recaps only the documents that did have named spans so they are not buried. Do not dump every excluded body block. Preview stays optional and truncated.

### Console (structure step)

After preprocess, the same command prints the retained outline (kept blocks only):

```text
document-structure
  sections: 28  subsections: 18  implicit_title_sections: 1

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             sections: 12  max_depth: 3
             outline:
               1  "Executive summary"  p14-b3
               1  "Part 1: The state of social determinants of health equity"  p31-b2
               2    "Chapter 1: Inequities in today’s world"  p33-b2
```

Always print the **outline** (depth, heading, start `block_id`). Heading-light PDFs (Healthy People scrapes) show one implicit section named from the document title. A Part/Chapter/Recommendation/Annex or dotted number must appear before weaker `1. Title` lines or leftover LLM headings are used. Running headers, bibliography lines, citation marks, and sentence fragments are body, not new sections.

### Console (chunk step)

After structure, the same command prints the chunk list (original-body character counts; heading prefix is extra context and is not counted):

```text
document-chunk
  chunks: 84  oversized_atomic: 1

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             chunks: 61  max_chars: 1482
             chunks:
               c1  "Executive summary"  912  p14-b4
               c2  "1.1.1 Definitions"  1104  p36-b44
```

Always print **one line per chunk** (id, section heading, original char count, start `block_id`). Start `block_id` is the first block covered by that chunk’s original text, not the section heading. Do not dump original or contextual text unless `--preview-blocks` / `PREVIEW_BLOCKS` is set. Sizes come from `config.yaml` `chunking:` (`target_size` 1000, `max_size` 1500, `min_size` 300, `overlap` 100 characters of original body). Paragraphs over `max_size` split on sentences, then on whitespace if needed; tables, lists, and captions stay one chunk. Sections are not merged even when under `min_size`. Bibliography is kept and chunked unless `references` is added to `exclude_sections`.

By default the console does **not** print block text. To sample the tree, set `preview_blocks` / `PREVIEW_BLOCKS` / `--preview-blocks N` (first N blocks of each loaded document, one line each, text truncated).

```text
document-load
  input_path: ./documents
  recursive: true
  preview_blocks: 5

  loaded  documents/World report on social determinants of health equity, WHO 2025.pdf
          title: World report on social determinants of health equity
          pages: 248  blocks: 10376  text_chars: 657650
          preview (first 5 of 10376):
            p1-b1  heading_candidate  World report on social determinants of health equity
            p1-b2  text  ...
```

## Inspection

Users should be able to inspect, at minimum:

1. Original document structure (the load block tree)
2. Excluded / preprocessed sections
3. Retained structure
4. Generated chunks
5. Extracted metadata
6. Validated metadata
7. Final metadata-store records

## Commands

```bash
python -m document_metadata_store
python -m document_metadata_store --config config.yaml
python -m document_metadata_store --preview-blocks 20
```

Runs load, preprocess, structure, then chunk against `documents/` (or `DOCUMENTS_INPUT_PATH`). `--preview-blocks` prints the first N blocks per document (preprocess preview includes keep/exclude; structure preview samples outline nodes; chunk preview samples `contextual_text`). Set `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-sonnet-5`, and `LLM_API_KEY` for leftover heading classification; omit the key to use aliases and rules only.
