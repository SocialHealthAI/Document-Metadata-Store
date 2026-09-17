from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from document_metadata_store.models import ChunkMetadata, Provenance


@dataclass(frozen=True)
class StoredRecord:
    chunk_id: str
    document_id: str
    text: str
    embedding: tuple[float, ...]
    metadata: ChunkMetadata
    provenance: Provenance
    model: str
    dim: int


@dataclass(frozen=True)
class StoreCandidate:
    record: StoredRecord
    distance: float


@dataclass(frozen=True)
class PersistStats:
    records: int
    upserted: int
    skipped: int
    replaced: int


class MetadataStore(Protocol):
    def delete_document(self, document_id: str) -> int:
        """Remove existing records for this document. Return how many were deleted."""

    def upsert(self, records: list[StoredRecord]) -> int:
        """Insert records. Return how many were written."""

    def query_candidates(
        self, embedding: list[float] | tuple[float, ...], n: int
    ) -> list[StoreCandidate]:
        """Nearest neighbors by vector distance (cosine). Does not apply tag filters."""
