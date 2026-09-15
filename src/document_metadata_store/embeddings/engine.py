from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from document_metadata_store.embeddings.model import EMBEDDING_DIM, EMBEDDING_MODEL, encode_texts
from document_metadata_store.models import EmbeddedChunk, EmbeddedDocument, EnrichedChunk, EnrichedDocument

EmbedBatchFn = Callable[[list[EnrichedChunk]], "EmbedBatchOutcome | dict[str, tuple[float, ...]] | None"]


@dataclass(frozen=True)
class EmbedBatchOutcome:
    parsed: dict[str, tuple[float, ...]] = field(default_factory=dict)
    error: str | None = None


def embed_document(
    document: EnrichedDocument,
    batch_size: int,
    *,
    embed_batch: EmbedBatchFn | None = None,
) -> EmbeddedDocument:
    completer = embed_batch or encode_enriched_batch
    items: list[EmbeddedChunk] = []
    size = max(batch_size, 1)
    for start in range(0, len(document.chunks), size):
        items.extend(_embed_batch(document.chunks[start : start + size], completer))
    return EmbeddedDocument(
        metadata=document.metadata,
        source=document.source,
        chunks=items,
        model=EMBEDDING_MODEL,
        dim=EMBEDDING_DIM,
        embed_errors=_unique_errors(
            [item.embed_error for item in items if item.embed_failed]
        ),
    )


def encode_enriched_batch(chunks: list[EnrichedChunk]) -> EmbedBatchOutcome:
    if not chunks:
        return EmbedBatchOutcome()
    try:
        vectors = encode_texts([item.chunk.contextual_text for item in chunks])
    except Exception as exc:  # noqa: BLE001 — fail-soft per batch
        return EmbedBatchOutcome(error=f"embed_failed: {exc}")
    parsed: dict[str, tuple[float, ...]] = {}
    for chunk, vector in zip(chunks, vectors, strict=True):
        parsed[chunk.chunk_id] = tuple(float(value) for value in vector)
    return EmbedBatchOutcome(parsed=parsed)


def _invoke(
    completer: EmbedBatchFn,
    batch: list[EnrichedChunk],
) -> EmbedBatchOutcome:
    result = completer(batch)
    if isinstance(result, EmbedBatchOutcome):
        return result
    if result is None:
        return EmbedBatchOutcome(error="embed_batch_failed")
    return EmbedBatchOutcome(parsed=result)


def _embed_batch(
    batch: list[EnrichedChunk],
    completer: EmbedBatchFn,
) -> list[EmbeddedChunk]:
    outcome = _invoke(completer, batch)
    parsed = outcome.parsed or {}
    matched = {
        chunk.chunk_id: parsed[chunk.chunk_id]
        for chunk in batch
        if chunk.chunk_id in parsed
    }
    if matched and len(matched) == len(batch):
        return [_ok(chunk, matched[chunk.chunk_id]) for chunk in batch]
    if matched:
        missing = [chunk for chunk in batch if chunk.chunk_id not in matched]
        kept = [_ok(chunk, matched[chunk.chunk_id]) for chunk in batch if chunk.chunk_id in matched]
        rest = _embed_batch(missing, completer)
        return _merge_in_order(batch, kept + rest)
    if len(batch) == 1:
        return [_failed(batch[0], outcome.error)]
    mid = max(len(batch) // 2, 1)
    return _embed_batch(batch[:mid], completer) + _embed_batch(batch[mid:], completer)


def _ok(chunk: EnrichedChunk, vector: tuple[float, ...]) -> EmbeddedChunk:
    return EmbeddedChunk(
        item=chunk,
        embedding=vector,
        dim=len(vector),
        model=EMBEDDING_MODEL,
        embed_failed=False,
    )


def _failed(chunk: EnrichedChunk, error: str | None) -> EmbeddedChunk:
    return EmbeddedChunk(
        item=chunk,
        embedding=(),
        dim=0,
        model=EMBEDDING_MODEL,
        embed_failed=True,
        embed_error=error or "embed_batch_failed",
    )


def _merge_in_order(
    batch: list[EnrichedChunk],
    items: list[EmbeddedChunk],
) -> list[EmbeddedChunk]:
    by_id = {item.chunk_id: item for item in items}
    return [by_id[chunk.chunk_id] for chunk in batch]


def _unique_errors(items: list[str | None]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return tuple(ordered)
