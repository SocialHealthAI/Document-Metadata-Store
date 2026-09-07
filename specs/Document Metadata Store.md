# Document Metadata Store

## Requirements Specification

### 1. Purpose

The **Document Metadata Store** is a generalized tool for converting documents into searchable, context-aware knowledge records.

The tool is intended to support knowledge bases across different subject areas. It should not contain subject-specific logic. Subject-specific behavior should be provided through configuration, metadata schemas, controlled vocabularies, and prompts.

The primary objectives are to:

1. Remove document content that is not useful for knowledge retrieval.

2. Preserve document structure and context.

3. Divide documents into meaningful knowledge units.

4. Attach structured metadata describing each knowledge unit.

5. Generate vector embeddings for semantic retrieval.

6. Preserve provenance so information can be traced to the original document.

7. Support reliable reprocessing as processing rules and models evolve.

***

# 2. Processing Pipeline

The processing pipeline is:

**Document → Preprocessing → Structure Extraction → Context-Aware Chunking → Metadata Extraction → Metadata Validation → Embedding Generation → Metadata Store**

Each stage should have a defined responsibility and should be independently configurable.

***

# 3. Document Loading

The Document Metadata Store should initially support:

* PDF

* DOCX

* TXT

* Markdown

* HTML

The Document Loader should convert each document into a **block-level** normalized internal representation while preserving available document-level metadata. It must not flatten the document to a single string or a list of page strings. Layout and style signals that later stages need cannot be recovered after flattening.

Document metadata may include:

* Document ID

* Title

* Author

* Organization

* Publication date

* Source

* Source URL

* Document type

* Language

* Version

The locked load contract is:

```text
NormalizedDocument
  metadata          # id, title, author, organization, publication_date,
                    # source, source_url, document_type, language, version
  source            # original path; read-only; never written back
  pages[]
    page_number
    blocks[]        # reading order
      block_id
      kind          # text | heading_candidate | paragraph | list_item | table | caption
      text
      style_hints   # font size, bold, indent — when available
      location      # page, optional bbox
```

`kind` values are observables from the source format, not a finished outline. Load does not assign sections or exclude content. Preprocessing marks keep/exclude on blocks without deleting them. Structure Extraction promotes heading candidates and order into a section tree. Metadata extraction and chunking walk that tree and inherit document-level metadata from `NormalizedDocument.metadata`.

The original source document must never be modified.

***

# 4. Document Preprocessing

Preprocessing determines which portions of a document should be retained for knowledge retrieval and which should be excluded.

Many documents contain administrative or navigational content that has little value as searchable knowledge. Removing this material can improve retrieval quality and reduce unnecessary vector-store content.

## 4.1 Sections Commonly Excluded

The preprocessing stage should support configurable exclusion of sections such as:

* Cover/title pages

* Foreword

* Forward/message sections

* Acknowledgments

* Table of contents

* List of figures

* List of tables

* Abbreviations/acronyms

* References/bibliography

* Index

The system must **not assume that every document should exclude all of these sections**. Inclusion and exclusion should be configurable.

## 4.2 Sections Normally Retained

The default configuration should generally retain substantive sections such as:

* Executive summary

* Introduction

* Main chapters/sections

* Methods

* Findings/results

* Conclusions

* Recommendations

Executive summaries should not be automatically removed because they can contain valuable high-level knowledge.

## 4.3 Figures

Figures should not automatically be discarded.

The initial implementation should support:

1. Decorative figures — may be discarded.

2. Figures containing substantive information — preserve captions and associated text.

3. Figures requiring visual interpretation — image interpretation may be treated as a future capability.

The initial version should therefore preserve figure captions and relevant associated text while leaving detailed image interpretation out of scope.

## 4.4 Tables

Tables containing substantive information should be preserved where practical.

The system should convert tables into a representation that can subsequently be chunked, embedded, and retrieved.

## 4.5 Section Detection

Section identification should not depend solely on exact section names.

The system should support a combination of:

* Document structure

* Heading styles

* Pattern matching

* Configurable rules

* Section names

* LLM-based classification when necessary

For example, "References," "Bibliography," and "Sources and Notes" may represent the same functional section.

LLM classification should be used when deterministic methods cannot reliably identify the section.

## 4.6 Reversible Processing

Preprocessing must not destroy source information.

The system should record:

* Content that was excluded

* Reason for exclusion

* Rule or classification responsible

* Location in the original document

This allows preprocessing rules to be changed and the document reprocessed.

***

# 5. Structure Extraction

After preprocessing, the document should be converted into a structured representation.

Where available, the system should identify:

* Sections

* Subsections

* Headings

* Paragraphs

* Tables

* Figure captions

* Lists

* Other meaningful structural elements

Relationships between sections and subsections should be preserved.

Example:

```text
Document
  └── Section: Housing Instability
        └── Subsection: Recent Trends
              └── Paragraphs
```

***

# 6. Context-Aware Chunking

The Chunker divides the processed document into meaningful knowledge units.

Chunking should use logical document boundaries whenever possible rather than simply splitting text at fixed character positions.

The system should support configurable:

* Target chunk size

* Maximum chunk size

* Minimum chunk size

* Chunk overlap

* Paragraph boundaries

* Sentence boundaries

* Section boundaries

* Subsection boundaries

## 6.1 Context Preservation

Each chunk must retain the structural context necessary to understand it independently.

For example, rather than storing only:

> "This increased to 23% in 2022."

the stored text could contain:

> **Section: Housing Instability**\
> **Subsection: Recent Trends**\
> This increased to 23% in 2022.

The system should preserve existing document context rather than use an LLM to generate new contextual prose.

## 6.2 Chunk Information

Each chunk should retain:

* Chunk ID

* Document ID

* Section ID

* Section heading

* Parent heading/context

* Original text

* Source location

***

# 7. Metadata Extraction

Metadata provides structured information that can be used to determine the applicability of a knowledge record during retrieval.

Metadata extraction must be configurable and independent of any particular subject area.

Possible metadata fields include:

* Topic

* Geography

* Population

* Time period

* Evidence type

* Organization

* Technology

* Version

* Platform

The metadata schema should be supplied through configuration.

## 7.1 Metadata Inheritance

Metadata should support hierarchical inheritance.

For example:

```text
Document
  Geography = United States
  Population = Adults

    Section
      Topic = Food Insecurity

        Chunk
          Time Period = 2023
```

The chunk inherits applicable metadata from the document and section.

More specific metadata should override broader inherited metadata when appropriate.

## 7.2 Metadata Classification

Metadata values should be classified as:

* **Explicit** — directly stated in the document

* **Inherited** — obtained from document or section context

* **Inferred** — determined from the content

* **Unknown** — not available

The system must not invent metadata simply to populate a field.

Where practical, metadata should include confidence and the level at which the value was established.

***

# 8. Metadata Validation

Metadata must be validated before being stored.

Validation should check:

* Required fields

* Data types

* Valid dates

* Controlled vocabulary values

* Geographic consistency

* Conflicting metadata

* Unsupported values

* Missing required information

Validation errors should be reported rather than silently changing source information.

Non-critical issues may be recorded as warnings.

***

# 9. Embedding Generation

The Embedding stage converts each knowledge unit into a vector representation.

Embedding providers and models must be configurable.

The text supplied to the embedding model should contain the context necessary to understand the knowledge unit.

Structured metadata should remain separately available for filtering and ranking.

The embedding implementation should not be tied to a specific vendor or model.

***

# 10. Metadata Store

The Metadata Store provides persistent storage for processed knowledge records.

Each record should contain, at minimum:

* Chunk ID

* Document ID

* Text

* Embedding

* Metadata

* Provenance

The store should support:

* Semantic similarity search

* Metadata filtering

* Metadata-based ranking

* Document updates

* Document removal

* Re-indexing

The storage implementation should use an abstraction that allows different vector-store technologies to be substituted.

***

# 11. Provenance

Every knowledge record must retain sufficient provenance to identify its original source.

Provenance should include, where available:

* Document ID

* Document title

* Source

* Source URL

* Section

* Subsection

* Page

* Heading

* Paragraph or source location

* Document version

The purpose is to allow retrieved information to be traced back to the original document.

***

# 12. Processing Modes

The system should support at least two processing modes.

### Standard Processing

```text
Load
→ Preprocess
→ Structure
→ Chunk
→ Extract Metadata
→ Validate Metadata
→ Embed
→ Store
```

### Metadata-Disabled Processing

```text
Load
→ Preprocess
→ Structure
→ Chunk
→ Embed
→ Store
```

Preprocessing and context preservation should remain available even when metadata extraction is disabled.

***

# 13. Configuration

The behavior of the Document Metadata Store should be controlled through configuration rather than subject-specific code.

Example:

```yaml
documents:
  input_path: ./documents
  recursive: true

preprocessing:
  enabled: true

  exclude_sections:
    - foreword
    - acknowledgements
    - table_of_contents
    - list_of_figures
    - list_of_tables
    - abbreviations
    - references
    - index

  figures:
    mode: captions_only

  tables:
    preserve: true

chunking:
  strategy: structural
  target_size: 1000
  max_size: 1500
  min_size: 300
  overlap: 100

metadata:
  enabled: true
  schema: ./metadata_schema.yaml

embeddings:
  provider: ...
  model: ...

metadata_store:
  provider: ...
  collection: ...

processing:
  force: false
  overwrite: true
  batch_size: 50
```

The values shown are examples and are not fixed requirements.

***

# 14. Incremental Processing

The Document Metadata Store should support incremental processing.

When `force=false`:

* Unchanged documents should normally be skipped.

* New documents should be processed.

* Changed documents should be reprocessed.

The system should maintain a document fingerprint or equivalent mechanism for detecting changes.

Changes to processing configuration should also be capable of triggering reprocessing when necessary.

***

# 15. Forced Reprocessing

The system **must** support forced reprocessing.

When:

```text
force = true
```

the system should reprocess documents even when their source content has not changed.

Forced processing must rerun all applicable stages, including:

* Preprocessing

* Structure extraction

* Chunking

* Metadata extraction

* Metadata validation

* Embedding generation

* Metadata Store updates

This is important when testing changes to:

* Preprocessing rules

* Section classification

* Chunking strategy

* Metadata schemas

* Metadata prompts

* Embedding models

* Store configuration

When a document is reprocessed, obsolete records from the previous version must be removed or replaced.

***

# 16. Processing Manifest

Each processing run should produce a manifest containing:

* Run ID

* Timestamp

* Documents processed

* Documents skipped

* Documents failed

* Number of chunks created

* Number of sections excluded

* Preprocessing configuration

* Metadata extraction results

* Metadata validation warnings/errors

* Embedding model

* LLM model, if used

* Configuration version

* Metadata Store destination

The manifest provides an audit trail for the processing run.

***

# 17. Error Handling and Logging

The system should provide clear error handling and logging at each processing stage.

Errors should identify:

* Document

* Processing stage

* Error type

* Error message

* Relevant source location where available

A failure processing one document should not necessarily prevent processing of other documents.

Failed documents should be recorded in the processing manifest.

***

# 18. Inspection and Testing

The system should provide a means to inspect intermediate processing results before they are embedded and stored.

At minimum, users should be able to inspect:

1. Original document structure

2. Excluded/preprocessed sections

3. Retained document structure

4. Generated chunks

5. Extracted metadata

6. Validated metadata

7. Final Metadata Store records

Testing should include documents containing:

* Different section naming conventions

* Missing headings

* Long sections

* Nested sections

* Tables

* Figures

* References

* Appendices

* Executive summaries

* Poorly structured PDFs

* Repeated headers and footers

***

# 19. Component Interfaces

The system should separate the major processing components through defined interfaces:

```text
DocumentLoader
Preprocessor
StructureExtractor
Chunker
MetadataExtractor
MetadataValidator
EmbeddingProvider
MetadataStore
ManifestManager
```

Each component should be independently replaceable or configurable.

***

# 20. Subject Independence

The Document Metadata Store must remain subject-independent.

There should be no subject-specific logic such as:

```text
if subject == "SDoH":
    ...
```

Subject-specific behavior should instead be provided through:

* Metadata schemas

* Controlled vocabularies

* Preprocessing configuration

* Section classification rules

* Prompts

* Embedding configuration

* Metadata Store configuration

For example, an SDoH knowledge base might define:

```text
geography
population
SDoH domain
health outcome
evidence type
time period
```

A software knowledge base might instead define:

```text
technology
programming language
version
platform
API
```

The underlying Document Metadata Store remains unchanged.

***

# 21. Primary Requirements

The Document Metadata Store must:

1. Convert supported documents into searchable knowledge records.

2. Preserve original source documents.

3. Preprocess documents using configurable inclusion and exclusion rules.

4. Exclude configurable non-knowledge sections.

5. Preserve substantive sections such as executive summaries by default.

6. Preserve useful information from tables and figure captions.

7. Preserve document structure and context.

8. Create meaningful knowledge chunks.

9. Attach configurable structured metadata.

10. Support metadata inheritance.

11. Distinguish explicit, inherited, inferred, and unknown metadata.

12. Validate extracted metadata.

13. Preserve provenance.

14. Generate configurable embeddings.

15. Support semantic and metadata-based retrieval.

16. Support incremental processing.

17. Support forced reprocessing.

18. Replace obsolete records when documents are reprocessed.

19. Maintain a processing manifest.

20. Provide inspection of intermediate processing results.

21. Remain independent of any particular subject domain.

22. Avoid generating unnecessary contextual prose when document structure already provides the required context.

***

# 22. Architectural Principle

The central design principle is:

> **Remove irrelevant content, preserve document structure, create meaningful knowledge units, and attach structured metadata that describes their applicability.**

The Document Metadata Store should improve retrieval by preserving the information that gives a statement meaning and by providing structured information that allows retrieved knowledge to be evaluated for relevance and applicability.

***

# Changelog

| Date | Change |
|------|--------|
| 2026-09-06 | §3: locked block-level `NormalizedDocument` contract (pages → reading-order blocks) so preprocessing, section detection, and metadata can consume load output without reconstructing lost PDF layout. |
