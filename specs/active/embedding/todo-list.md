# embedding Todo

## Pre-flight
- [x] Review feature brief v1.2: local MiniLM, no config knobs, no validation stage, embed `contextual_text`

## Implementation
- [x] **models**: EmbeddedChunk, EmbeddedDocument wrapping EnrichedChunk
- [x] **engine**: batched MiniLM encode; injectable `embed_batch`; fail-soft split-retry
- [x] **orchestrator + CLI**: after metadata; counts + sample console
- [x] **deps**: sentence-transformers; Docker CPU torch; bake MiniLM in image
- [x] **tests**: dim 384, does not embed tags, console sample, metadata-disabled still embeds
- [x] **docs**: architecture, usage, installation, README, index, brief

## Progress
### Done
- [x] Same CLI: load → preprocess → structure → chunk → metadata → embed
- [x] Local MiniLM (`all-MiniLM-L6-v2`, 384-dim); no embedding config/env
- [x] Console counts + sample; unit tests inject `embed_batch`
- [ ] Live WHO + Healthy People via `docker compose up --build` (operator proof)

### Blockers
- [ ]

---
Start: 2026-09-15
Done: 2026-09-15
