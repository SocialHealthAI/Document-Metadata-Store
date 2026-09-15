from __future__ import annotations

from collections.abc import Callable

from document_metadata_store.config import LlmConfig, MetadataConfig
from document_metadata_store.metadata.llm import (
    LlmBatchOutcome,
    complete_metadata_batch,
    empty_metadata,
)
from document_metadata_store.metadata.schema import MetadataSchema
from document_metadata_store.models import (
    Chunk,
    ChunkedDocument,
    ChunkMetadata,
    EnrichedChunk,
    EnrichedDocument,
)

BatchCompleter = Callable[[list[Chunk], MetadataSchema, LlmConfig], dict[str, ChunkMetadata] | None]


def extract_document(
    document: ChunkedDocument,
    schema: MetadataSchema,
    config: MetadataConfig,
    llm: LlmConfig,
    *,
    complete_batch: BatchCompleter | None = None,
) -> EnrichedDocument:
    names = schema.field_names
    if not config.enabled:
        return EnrichedDocument(
            metadata=document.metadata,
            source=document.source,
            chunks=[
                EnrichedChunk(chunk=chunk, metadata=empty_metadata(schema))
                for chunk in document.chunks
            ],
            skipped=True,
            field_names=names,
        )
    completer = complete_batch or complete_metadata_batch
    use_llm = llm.enabled()
    enriched: list[EnrichedChunk] = []
    retries = 0
    batch_size = max(config.batch_size, 1)
    for start in range(0, len(document.chunks), batch_size):
        batch = document.chunks[start : start + batch_size]
        if use_llm:
            items, extra = _extract_batch(batch, schema, llm, completer)
            enriched.extend(items)
            retries += extra
        else:
            enriched.extend(
                EnrichedChunk(chunk=chunk, metadata=empty_metadata(schema))
                for chunk in batch
            )
    return EnrichedDocument(
        metadata=document.metadata,
        source=document.source,
        chunks=enriched,
        skipped=False,
        field_names=names,
        llm_errors=_unique_errors(
            [item.llm_error for item in enriched if item.llm_failed]
        ),
        llm_retries=retries,
    )


def _invoke(
    completer: BatchCompleter,
    batch: list[Chunk],
    schema: MetadataSchema,
    llm: LlmConfig,
) -> LlmBatchOutcome:
    result = completer(batch, schema, llm)
    if isinstance(result, LlmBatchOutcome):
        return result
    if result is None:
        return LlmBatchOutcome(error="llm_batch_failed")
    return LlmBatchOutcome(parsed=result)


def _extract_batch(
    batch: list[Chunk],
    schema: MetadataSchema,
    llm: LlmConfig,
    completer: BatchCompleter,
) -> tuple[list[EnrichedChunk], int]:
    outcome = _invoke(completer, batch, schema, llm)
    parsed = outcome.parsed
    matched: dict[str, ChunkMetadata] = {}
    if parsed:
        matched = {
            chunk.chunk_id: parsed[chunk.chunk_id]
            for chunk in batch
            if chunk.chunk_id in parsed
        }
    if matched and len(matched) == len(batch):
        return (
            [
                EnrichedChunk(chunk=chunk, metadata=matched[chunk.chunk_id])
                for chunk in batch
            ],
            0,
        )
    if matched:
        missing = [chunk for chunk in batch if chunk.chunk_id not in matched]
        kept = [
            EnrichedChunk(chunk=chunk, metadata=matched[chunk.chunk_id])
            for chunk in batch
            if chunk.chunk_id in matched
        ]
        rest, retries = _extract_batch(missing, schema, llm, completer)
        return _merge_in_order(batch, kept + rest), retries + 1
    if len(batch) == 1:
        return (
            [
                EnrichedChunk(
                    chunk=batch[0],
                    metadata=empty_metadata(schema),
                    llm_failed=True,
                    llm_error=outcome.error,
                )
            ],
            0,
        )
    mid = max(len(batch) // 2, 1)
    left, left_retries = _extract_batch(batch[:mid], schema, llm, completer)
    right, right_retries = _extract_batch(batch[mid:], schema, llm, completer)
    return left + right, left_retries + right_retries + 1


def _unique_errors(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            ordered.append(item)
    return tuple(ordered)


def _merge_in_order(batch: list[Chunk], items: list[EnrichedChunk]) -> list[EnrichedChunk]:
    by_id = {item.chunk_id: item for item in items}
    return [by_id[chunk.chunk_id] for chunk in batch]
