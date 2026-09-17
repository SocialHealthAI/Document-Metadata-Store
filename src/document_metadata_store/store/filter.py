from __future__ import annotations

from document_metadata_store.models import ChunkMetadata


def matches_filters(
    metadata: ChunkMetadata,
    filters: dict[str, list[str]] | None,
) -> bool:
    """OR within a field, AND across fields. Empty filter list = unconstrained.

    Empty / Unknown tags on a record do not satisfy a required filter.
    """
    if not filters:
        return True
    for field, wanted in filters.items():
        if not wanted:
            continue
        have = set(metadata.texts_for(field))
        if have.isdisjoint(wanted):
            return False
    return True


def candidate_pool_size(k: int) -> int:
    return max(k * 5, 50)
