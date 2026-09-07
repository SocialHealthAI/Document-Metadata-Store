# Usage

**Status:** Load-step console and discovery are implemented. Later stages are not.

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

Loaded files report **pages**, **blocks**, and **text_chars**. Title is printed only when the PDF provides it.

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

Runs the load step against `documents/` (or `DOCUMENTS_INPUT_PATH`). `--preview-blocks` prints the first N blocks per loaded document. See console output above. Processing, inspection dumps, and retrieval commands for later stages will be documented here when they exist.
