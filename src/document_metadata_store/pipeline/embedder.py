from __future__ import annotations

from dataclasses import dataclass, field

from document_metadata_store.embeddings.engine import EmbedBatchFn, embed_document
from document_metadata_store.embeddings.model import EMBEDDING_DIM, EMBEDDING_MODEL
from document_metadata_store.models import EmbeddedDocument
from document_metadata_store.pipeline.extractor import MetadataRun


@dataclass
class EmbedOutcome:
    path: str
    document: EmbeddedDocument
    records: int
    embedded: int
    embed_failed: int


@dataclass
class EmbedRun:
    model: str
    dim: int
    batch_size: int
    outcomes: list[EmbedOutcome] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "processed": len(self.outcomes),
            "records": sum(item.records for item in self.outcomes),
            "embedded": sum(item.embedded for item in self.outcomes),
            "embed_failed": sum(item.embed_failed for item in self.outcomes),
            "failed": len(self.failed),
        }


def embed_documents(
    metadata_run: MetadataRun,
    batch_size: int,
    *,
    embed_batch: EmbedBatchFn | None = None,
) -> EmbedRun:
    run = EmbedRun(model=EMBEDDING_MODEL, dim=EMBEDDING_DIM, batch_size=batch_size)
    for item in metadata_run.outcomes:
        try:
            embedded = embed_document(
                item.document, batch_size, embed_batch=embed_batch
            )
        except Exception as exc:  # noqa: BLE001 — continue batch
            run.failed.append((item.path, str(exc)))
            continue
        run.outcomes.append(
            EmbedOutcome(
                path=item.path,
                document=embedded,
                records=embedded.chunk_count(),
                embedded=embedded.embedded_count(),
                embed_failed=embedded.embed_failed_count(),
            )
        )
    return run
