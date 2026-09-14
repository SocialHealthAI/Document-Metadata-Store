from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from document_metadata_store.config import ChunkingConfig
from document_metadata_store.models import ChunkedDocument, StructuredDocument
from document_metadata_store.chunking.engine import chunk_document
from document_metadata_store.pipeline.structure import StructureRun


class Chunker(Protocol):
    def chunk(self, document: StructuredDocument, config: ChunkingConfig) -> ChunkedDocument:
        ...


@dataclass
class ChunkOutcome:
    path: str
    document: ChunkedDocument
    chunks: int
    max_chars: int
    oversized_atomic: int


@dataclass
class ChunkRun:
    outcomes: list[ChunkOutcome] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "processed": len(self.outcomes),
            "chunks": sum(item.chunks for item in self.outcomes),
            "oversized_atomic": sum(item.oversized_atomic for item in self.outcomes),
            "failed": len(self.failed),
        }


def chunk_documents(struct_run: StructureRun, config: ChunkingConfig) -> ChunkRun:
    run = ChunkRun()
    for item in struct_run.outcomes:
        try:
            chunked = chunk_document(item.document, config)
        except Exception as exc:  # noqa: BLE001 — continue batch
            run.failed.append((item.path, str(exc)))
            continue
        run.outcomes.append(
            ChunkOutcome(
                path=item.path,
                document=chunked,
                chunks=chunked.chunk_count(),
                max_chars=chunked.max_original_chars(),
                oversized_atomic=chunked.oversized_atomic_count(),
            )
        )
    return run
