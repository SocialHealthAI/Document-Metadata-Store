from __future__ import annotations

from dataclasses import dataclass, field

from document_metadata_store.config import LlmConfig, MetadataConfig
from document_metadata_store.metadata.engine import BatchCompleter, extract_document
from document_metadata_store.metadata.schema import MetadataSchema, load_metadata_schema
from document_metadata_store.models import EnrichedDocument
from document_metadata_store.pipeline.chunker import ChunkRun


@dataclass
class MetadataOutcome:
    path: str
    document: EnrichedDocument
    records: int
    with_any_field: int
    llm_failed: int
    skipped: bool


@dataclass
class MetadataRun:
    enabled: bool
    field_names: tuple[str, ...]
    batch_size: int
    outcomes: list[MetadataOutcome] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "processed": len(self.outcomes),
            "records": sum(item.records for item in self.outcomes),
            "with_any_field": sum(item.with_any_field for item in self.outcomes),
            "llm_failed": sum(item.llm_failed for item in self.outcomes),
            "skipped": sum(1 for item in self.outcomes if item.skipped),
            "failed": len(self.failed),
        }


def extract_metadata_documents(
    chunk_run: ChunkRun,
    config: MetadataConfig,
    llm: LlmConfig,
    *,
    schema: MetadataSchema | None = None,
    complete_batch: BatchCompleter | None = None,
) -> MetadataRun:
    loaded = schema or load_metadata_schema(config.schema_path)
    run = MetadataRun(
        enabled=config.enabled,
        field_names=loaded.field_names,
        batch_size=config.batch_size,
    )
    for item in chunk_run.outcomes:
        try:
            enriched = extract_document(
                item.document, loaded, config, llm, complete_batch=complete_batch
            )
        except Exception as exc:  # noqa: BLE001 — continue batch
            run.failed.append((item.path, str(exc)))
            continue
        run.outcomes.append(
            MetadataOutcome(
                path=item.path,
                document=enriched,
                records=enriched.chunk_count(),
                with_any_field=enriched.with_any_field_count(),
                llm_failed=enriched.llm_failed_count(),
                skipped=enriched.skipped,
            )
        )
    return run
