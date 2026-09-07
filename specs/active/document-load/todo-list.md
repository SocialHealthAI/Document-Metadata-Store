# document-load Todo

## Pre-flight
- [x] Review feature brief + product spec §3 + architecture/usage
- [x] Lock pypdf (user) and remaining defaults

## Implementation
- [x] **types**: NormalizedDocument / page / block models
- [x] **config**: Load config.yaml + DOCUMENTS_INPUT_PATH
- [x] **pdf**: pypdf extract → block tree; image-only detect
- [x] **orchestrator**: Discover documents/, skip/fail per file
- [x] **console**: Locked summary format
- [x] **cli**: `python -m document_metadata_store`
- [x] **tests**: Generated PDF, skip non-PDF, skip image-only
- [x] **who-fixture**: WHO 2025 PDF loaded (248 pages, 10376 blocks, 657650 chars)
- [x] **docs**: Dockerfile, installation, architecture, brief v1.3

## Progress
### Done
- [x] Defaults: pypdf; Document ID = SHA-256 of resolved path; continue on failure; under-classify headings

### Blockers
- [ ]

## DoD
Tests pass + console contract + source PDFs unchanged

---
Start: 2026-09-06
