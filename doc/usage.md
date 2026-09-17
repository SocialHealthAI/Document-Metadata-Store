# Usage

**Status:** Load through store runs in one command. Agents import `search()` against local Chroma files.

Install and env vars: [installation.md](installation.md).

---

## Building a Metadata Document Store

### Workflow

1. Place documents in `documents/` (or the path in `config.yaml` / `DOCUMENTS_INPUT_PATH`).
2. Configure preprocessing, chunking, metadata, and store in `config.yaml`.
3. Point `metadata.schema` at a subject-specific `metadata_schema.yaml`.
4. Run `python -m document_metadata_store` (or `docker compose up`).
5. Inspect console stages (including `document-store`) before relying on stored records.

### Processing modes

- **Standard:** load → preprocess → structure → chunk → extract metadata → embed → store
- **Metadata-disabled:** load → preprocess → structure → chunk → embed → store

Preprocessing and context preservation remain available when metadata extraction is off.

### Incremental and forced runs

This slice always reprocesses discovered PDFs and **replaces** that document’s stored records (`document_id`). Skip-unchanged fingerprinting (`processing.force: false`) is not implemented yet. `processing.force` / `overwrite` in `config.yaml` are reserved for that later behavior.

### Commands

```bash
python -m document_metadata_store
python -m document_metadata_store --config config.yaml
python -m document_metadata_store --preview-blocks 20
```

Runs load, preprocess, structure, chunk, metadata, embed, then **store** against `documents/` (or `DOCUMENTS_INPUT_PATH`). `--preview-blocks` prints the first N blocks per document (preprocess preview includes keep/exclude; structure preview samples outline nodes; chunk preview samples `contextual_text`; metadata, embed, and store preview add truncated text on the sample). Set `LLM_PROVIDER=anthropic`, `LLM_MODEL=claude-sonnet-5`, and `LLM_API_KEY` for leftover heading classification and metadata extraction; omit the key to use aliases/rules for preprocess and leave metadata Unknown. Embeddings always run locally (no embedding API key). Records persist under `data/metadata-store`.

### Load output

A successful load produces an in-memory `NormalizedDocument`: document-level metadata plus pages of reading-order blocks (`kind`, text, style hints, location). That tree is the “original document structure” inspection surface. Later stages mark exclusions and build a section tree from these blocks; they do not re-parse a flattened PDF string.

#### Console (load step)

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

#### Console (preprocess step)

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

#### Console (structure step)

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

#### Console (chunk step)

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

#### Console (metadata step)

After chunking, the same command extracts schema fields (`topic`, `geography`, `population`, `time_period`) as lists on each chunk. Topic, geography, and population are free-text. `time_period` is **calendar years** only (a span such as 2019–2022 is stored as `2019`, `2020`, `2021`, `2022`). Values are grounded in `contextual_text`. Extraction is batched (`processing.batch_size`, default 50). Without `LLM_API_KEY`, fields stay empty (Unknown) and the run still succeeds. `metadata.enabled: false` skips extraction.

The console is a **histogram + sample of tagged chunks**, not one line per chunk:

```text
document-metadata
  enabled: true  batch_size: 50
  records: 519  with_any_field: 480  llm_failed: 2

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             records: 519  with_any_field: 480  llm_failed: 2
             topic:        housing (41), income (28), diabetes (6)
             geography:    Kenya (12), Brazil (9), global (80)
             population:   adults (22), children (11)
             time_period:  2020 (18), 2021 (15), 2015 (7)
             origins:      explicit=612 inherited=88 inferred=40 unknown=0
             sample (tagged):
               c41  topic=[housing instability]  geo=[Kenya]  pop=[]  time=[2022]
```

Sample size is `preview_blocks` when set, otherwise 5 **tagged** chunks (original `cN`). Empty leading chunks from a failed batch are skipped in the sample. Histograms are top 10 terms, case-insensitive. If a large batch hits `max_tokens` or bad JSON, it is split and retried. Recovered splits print `llm_retried: N`, not `llm_error:`. `llm_error:` is only for chunks that still failed after retries.

#### Console (embed step)

After metadata, the same command encodes each chunk’s `contextual_text` with local MiniLM (`all-MiniLM-L6-v2`, 384-dim). Metadata lists are not concatenated into the vector. There are no embedding settings in `config.yaml` or `.env`. `metadata.enabled: false` still embeds those chunks. Encode is batched with `processing.batch_size`.

The console is **counts + a small sample**, not one vector per chunk:

```text
document-embed
  model: all-MiniLM-L6-v2  dim: 384  batch_size: 50
  records: 519  embedded: 519  failed: 0

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             records: 519  dim: 384  failed: 0
             sample:
               c1   chars=842
               c41  chars=1204
```

Sample size is `preview_blocks` when set, otherwise 5. Do not print vector components. Preview adds truncated `contextual_text` on the sample.

#### Console (store step)

After embed, the same command writes successful chunks to local Chroma (`metadata_store.persist_path`, default `./data/metadata-store`; collection `knowledge`). Failed embeds are skipped. Re-running a document **replaces** its records. There is no extra Compose service and no store API key.

The console is **counts + a small sample**, not one record per chunk:

```text
document-store
  provider: chroma  collection: knowledge  path: data/metadata-store
  records: 519  upserted: 519  failed: 0

  processed  documents/World report on social determinants of health equity, WHO 2025.pdf
             records: 519  upserted: 519  replaced: 519
             sample:
               c1   topic=[housing instability]  geo=[Kenya]  time=[2020, 2021]
               c41  topic=[]  geo=[]  time=[]
```

Sample size is `preview_blocks` when set, otherwise 5. Do not print vector components.

By default the console does **not** print block text. To sample the tree, set `preview_blocks` / `PREVIEW_BLOCKS` / `--preview-blocks N` (first N blocks of each loaded document, one line each, text truncated). Metadata, embed, and store preview also include truncated `contextual_text` on the sample.

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

### Inspection

Operators should be able to inspect, at minimum:

1. Original document structure (the load block tree)
2. Excluded / preprocessed sections
3. Retained structure
4. Generated chunks
5. Extracted metadata
6. Embeddings
7. Final metadata-store records

---

## Client Usage

An agent retrieves knowledge records with **`search()`** (semantic search plus optional **metadata filters**). It does not query the section tree. Headings already sit in each chunk’s `contextual_text` (that is what was embedded).

How to install the library (public GitHub pip, no token, or a clone), place `data/metadata-store`, and set `METADATA_STORE_PERSIST_PATH`: [installation.md](installation.md) **Client Usage**. A client is not Chroma-only: query vectors must use the same MiniLM as ingest.

Always put the user’s question in `query`. Add a filter only for axes you are willing to treat as **hard requirements**. Filters match stored tags, not a mention in the prose: a chunk that says “2020” but has an empty `time_period` list is dropped by `time_period: ["2020"]`.

`k` is how many hits to return (default 8). You may get fewer if filters are strict.

```python
from document_metadata_store import search

query = "Did housing instability among adults in Kenya change after 2020?"

# 1. Query + the filter you trust most (often place, with synonyms)
hits = search(query, filters={"geography": ["Kenya", "Kenyan"]}, k=8)

# 2. Too many / noisy hits → add another filter (time, then topic or population)
hits = search(
    query,
    filters={"geography": ["Kenya", "Kenyan"], "time_period": ["2020"]},
    k=8,
)

# 3. Zero hits → drop the last filter and search again (drop time first)
if not hits:
    hits = search(query, filters={"geography": ["Kenya", "Kenyan"]}, k=8)

# each hit: text, metadata, provenance, score — cite document, section, page
for hit in hits:
    print(hit.score, hit.provenance.document_title, hit.provenance.section, hit.provenance.pages)
```

Run step 2 only when step 1 is too broad. Do **not** start with all four fields ANDed. Empty tags on any required field exclude the chunk. Time is the first filter to drop.

Use the **same** embedding model as ingest (`all-MiniLM-L6-v2`, 384-dim). Do not embed metadata tag strings or cosine them against the chunk vector.

`search()`:

1. Embeds `query`.
2. Retrieves a similarity candidate pool, then keeps records whose lists **overlap** the filter values (see OR/AND below).
3. Ranks remaining hits by similarity to the query vector.
4. Returns `{text, metadata, provenance, score}` — not raw vectors. Cite document, section, and page from provenance.

Omit a filter field (or pass an empty list) to leave that axis unconstrained. Empty / Unknown tags on a chunk do **not** satisfy a required filter.

### OR within a field, AND across fields

Values in **one** filter list are **OR**. Different fields are **AND**.

`geography: ["Ohio", "OH"]` matches a chunk tagged `Ohio` **or** `OH`.  
`geography: ["Ohio", "OH"]` plus `time_period: ["2020"]` means (Ohio **or** OH) **and** 2020.

Do not OR across fields (Ohio **or** 2020).

### Synonyms (query-side)

Tags are free-text. Exact string overlap is brittle (`"Ohio"` ≠ `"OH"`). Until a store vocabulary exists (`doc/architecture.md` Futures), the **agent that builds the query** should expand names into a synonym list for each filter field it sets.

**Geography (most useful).** Always expand places:

- Country: `United States`, `USA`, `US`, `U.S.`
- Subdivision: `Ohio`, `OH` (and official name if known)
- City: `New York City`, `NYC`, `New York`
- Informal region only if the user meant it: `Midwest` — do not add it automatically for every Ohio query

**Topic.** Expand **abbreviations and equivalent names**, not looser related ideas:

- `tuberculosis`, `TB`
- `HIV`, `HIV/AIDS`
- `maternal mortality`, `MMR` (only if that abbreviation is used in the corpus)

Do **not** treat `housing` as interchangeable with every housing-related phrase. Prefer the user’s wording plus 1–2 close aliases from the metadata histogram, not a long related-term list.

**Population.** Expand grammatical and clinical variants:

- `adults`, `adult`
- `children`, `child`, `pediatric`
- `women`, `female`, `females`

Avoid loading extra groups the user did not ask for (`elderly` is not a synonym of `adults`).

**Time period.** Extraction stores **calendar years** (`2019`, `2020`), expanding spans such as `2019-2022`. A filter of `["2020"]` therefore overlaps a 2019–2022 chunk. On the query, still expand a user span to a year list. Equivalent writings: `2020`, `FY2020` (ingestion maps FY2020 → `2020`). Do not add neighboring years the user did not ask for. Vague phrases (`2020s`) are omitted at extraction.

**What the vector is for.** Synonym lists fix **filters**. US / USA / United States in **prose** can still match via cosine on `contextual_text` even when tags differ. Use both: a specific query string, plus expanded filters when the agent is sure of place, time, population, or topic.
