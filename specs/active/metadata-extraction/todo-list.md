# metadata-extraction Todo

## Pre-flight
- [x] Review feature brief v1.1 + chunk pipeline patterns; batch LLM calls (user-locked)

## Implementation
- [x] **models**: MetadataValue, ChunkMetadata, EnrichedChunk, EnrichedDocument
- [x] **config**: MetadataConfig (enabled, schema path, batch_size from processing)
- [x] **schema + engine**: load YAML fields; batched Anthropic JSON; fail-soft
- [x] **orchestrator + CLI**: after chunk; histogram + sample console
- [x] **tests**: lists, mixed topic, skip/disabled, batching, WHO + Healthy People
- [x] **docs**: architecture, usage, installation, README, index, brief

## Progress
### Done
- [x] Same CLI: load → preprocess → structure → chunk → metadata
- [x] Four free-text list fields; batched LLM (`processing.batch_size` 50)
- [x] Histogram + sample console; skip when disabled; Unknown without API key
- [x] WHO + Healthy People succeed with Unknown when no LLM key

### Blockers
- [ ]

---
Start: 2026-09-14
Done: 2026-09-14
