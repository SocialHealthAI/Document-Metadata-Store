from __future__ import annotations

from collections.abc import Callable, Sequence

from document_metadata_store.config import StoreConfig, load_app_config
from document_metadata_store.embeddings.model import encode_texts
from document_metadata_store.models import SearchHit
from document_metadata_store.store.filter import candidate_pool_size, matches_filters
from document_metadata_store.store.protocol import MetadataStore

EncodeFn = Callable[[list[str]], list[Sequence[float]]]


def search(
    query: str,
    filters: dict[str, list[str]] | None = None,
    k: int = 8,
    *,
    store: MetadataStore | None = None,
    encode: EncodeFn | None = None,
    config: StoreConfig | None = None,
) -> list[SearchHit]:
    """Semantic search plus optional metadata filters. Agents import this function."""
    if k < 1:
        raise ValueError("k must be >= 1")
    backend = store or open_store(config)
    encode_fn = encode or encode_texts
    vectors = encode_fn([query])
    if not vectors:
        return []
    pool = candidate_pool_size(k)
    hits: list[SearchHit] = []
    for candidate in backend.query_candidates(tuple(float(v) for v in vectors[0]), pool):
        if not matches_filters(candidate.record.metadata, filters):
            continue
        record = candidate.record
        hits.append(
            SearchHit(
                text=record.text,
                metadata={name: record.metadata.texts_for(name) for name in record.metadata.fields},
                provenance=record.provenance,
                score=_similarity(candidate.distance),
                chunk_id=record.chunk_id,
                document_id=record.document_id,
            )
        )
        if len(hits) >= k:
            break
    return hits


def open_store(config: StoreConfig | None = None) -> MetadataStore:
    from document_metadata_store.store.chroma import ChromaMetadataStore

    cfg = config or load_app_config().store
    if cfg.provider != "chroma":
        raise ValueError(
            f"Unsupported metadata_store.provider {cfg.provider!r}; this slice implements chroma only"
        )
    return ChromaMetadataStore(cfg)


def _similarity(distance: float) -> float:
    return 1.0 - float(distance)
