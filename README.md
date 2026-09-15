# Document Metadata Store

A generalized tool for converting documents into searchable, context-aware knowledge records. Subject-specific behavior is supplied through configuration, metadata schemas, controlled vocabularies, and prompts — not application code.

**Status:** Document load (text PDFs), preprocessing (keep/exclude), structure extraction, context-aware chunking, metadata extraction, and embedding generation are implemented. The metadata store is not.

## Canonical documents

Read and keep these current whenever behavior, deployment, or requirements change:

| Document | Role |
|----------|------|
| [specs/Document Metadata Store.md](specs/Document%20Metadata%20Store.md) | Product requirements |
| [doc/architecture.md](doc/architecture.md) | System shape and pipeline |
| [doc/installation.md](doc/installation.md) | Docker install and configuration |
| [doc/usage.md](doc/usage.md) | How to run and inspect processing |

## Quick start

```bash
python -m pip install -e .
python -m document_metadata_store
```

Or with Docker: `docker compose up --build`. See [doc/installation.md](doc/installation.md).

## Repository layout (scaffolding)

```text
src/document_metadata_store/   # Load through embedding generation
config.yaml                    # Processing configuration (exclude_sections, aliases, chunking, metadata)
metadata_schema.yaml           # Extracted field names (this version: four list fields)
documents/                     # Source documents (never modified in place)
doc/                           # Architecture, installation, usage
specs/                         # Product spec and SDD artifacts
```

## Spec-kit

This repository is set up so spec-kit commands can start from a Docker-oriented skeleton. Fill constitution and feature specs before implementing the pipeline.
