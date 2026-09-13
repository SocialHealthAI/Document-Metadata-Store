# document-preprocessing Todo

## Pre-flight
- [x] Review feature brief v1.6 + keep-references evolution

## Implementation
- [x] **models**: AnnotatedBlock, PreprocessedDocument, ExcludedSection
- [x] **config**: PreprocessingConfig + LLM env; cover + aliases in YAML
- [x] **rules/aliases**: heading-like under-span; cheap rules; alias map
- [x] **cover**: pages until Contents; no TOC skip
- [x] **llm**: optional Anthropic adapter
- [x] **spans + orchestrator**: mark copy; same CLI
- [x] **console**: counts + excluded section titles + preview disposition
- [x] **tests**: enabled=false, TOC/foreword/exec summary, no TOC, aliases
- [x] **docs**: architecture, usage, installation
- [x] **keep citations**: drop `references` from default `exclude_sections`; retain citation headings; optional exclude still works

## Progress
### Done
- [x] Load then preprocess in `python -m document_metadata_store`
- [x] Hybrid classifier (rules + aliases + optional Anthropic)
- [x] WHO 2025 fixture proof (skip if PDF absent)
- [x] Canonical docs updated
- [x] References/citations kept by default (brief v1.6)

### Blockers
- [ ]

---
Start: 2026-09-08
Done: 2026-09-09
