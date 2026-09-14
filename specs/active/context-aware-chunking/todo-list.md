# context-aware-chunking Todo

## Pre-flight
- [x] Review feature brief v1.0 + structure pipeline patterns

## Implementation
- [x] **models**: Chunk, ChunkedDocument
- [x] **config**: wire chunking target/max/min/overlap
- [x] **engine**: section walk, pack, sentence split, atomic units, overlap
- [x] **orchestrator + CLI**: after structure; console chunk list
- [x] **tests**: prefix, split, atomic, no cross-section merge, WHO + Healthy People
- [x] **docs**: architecture, usage, installation

## Progress
### Done
- [x] Same CLI: load → preprocess → structure → chunk
- [x] Character sizes; heading prefix excluded; no cross-section merge
- [x] Console chunk list (id + heading + chars + start block)
- [x] WHO nested headings + Healthy People implicit title splits

### Blockers
- [ ]

---
Start: 2026-09-14
Done: 2026-09-14
