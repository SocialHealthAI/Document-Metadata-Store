# metadata-store Todo

## Pre-flight
- [x] Review feature brief v1.0 + embed pipeline patterns; local Chroma; library `search()`

## Implementation
- [x] **models**: SearchHit, Provenance, StoredRecord; StoreConfig
- [x] **protocol + chroma**: MetadataStore; PersistentClient; replace by document_id
- [x] **search**: encode query; ANN pool; OR/AND overlap; injectable store/encode
- [x] **orchestrator + CLI**: after embed; counts + sample console; Docker persist volume
- [x] **tests**: skip failed embeds, replace on re-run, year filter, empty tags, no vector dump
- [x] **docs**: architecture, usage, installation, README, index, brief

## Progress
### Done
- [x] Same CLI: load → … → embed → store
- [x] Local Chroma files; library `search()`; OR/AND filters
- [x] Compact document-store console; skip failed embeds; replace by document_id

### Blockers
- [ ]

---
Start: 2026-09-16
Done: 2026-09-16
