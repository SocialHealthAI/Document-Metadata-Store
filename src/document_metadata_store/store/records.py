from __future__ import annotations

import json

from document_metadata_store.embeddings.model import EMBEDDING_DIM
from document_metadata_store.models import (
    ChunkMetadata,
    EmbeddedChunk,
    EmbeddedDocument,
    MetadataValue,
    Provenance,
)
from document_metadata_store.store.protocol import PersistStats, StoredRecord

_TAGS_KEY = "tags_json"
_PROVENANCE_KEY = "provenance_json"
_ORIGIN_KEY = "origin"


def to_stored_record(document: EmbeddedDocument, item: EmbeddedChunk) -> StoredRecord | None:
    if item.embed_failed or item.dim != EMBEDDING_DIM or len(item.embedding) != EMBEDDING_DIM:
        return None
    chunk = item.chunk
    return StoredRecord(
        chunk_id=chunk.chunk_id,
        document_id=document.metadata.id,
        text=chunk.contextual_text,
        embedding=item.embedding,
        metadata=item.metadata,
        provenance=Provenance(
            document_id=document.metadata.id,
            document_title=document.metadata.title,
            source=document.metadata.source or document.source,
            source_url=document.metadata.source_url,
            version=document.metadata.version,
            section=chunk.section_heading,
            subsection=chunk.parent_heading,
            pages=chunk.pages,
            heading=chunk.section_heading,
            start_block_id=chunk.start_block_id,
        ),
        model=item.model,
        dim=item.dim,
    )


def persist_document(document: EmbeddedDocument, store) -> PersistStats:
    replaced = store.delete_document(document.metadata.id)
    records = []
    skipped = 0
    for item in document.chunks:
        record = to_stored_record(document, item)
        if record is None:
            skipped += 1
            continue
        records.append(record)
    upserted = store.upsert(records) if records else 0
    return PersistStats(
        records=len(document.chunks),
        upserted=upserted,
        skipped=skipped,
        replaced=replaced,
    )


def chroma_metadata(record: StoredRecord) -> dict[str, str | int]:
    tags: dict[str, list[dict[str, str | float | None]]] = {}
    for name, values in record.metadata.fields.items():
        tags[name] = [
            {"value": item.value, "origin": item.origin, "confidence": item.confidence}
            for item in values
        ]
    provenance = {
        "document_id": record.provenance.document_id,
        "document_title": record.provenance.document_title,
        "source": record.provenance.source,
        "source_url": record.provenance.source_url,
        "version": record.provenance.version,
        "section": record.provenance.section,
        "subsection": record.provenance.subsection,
        "pages": list(record.provenance.pages),
        "heading": record.provenance.heading,
        "start_block_id": record.provenance.start_block_id,
    }
    return {
        "document_id": record.document_id,
        "chunk_id": record.chunk_id,
        "model": record.model,
        "dim": record.dim,
        _TAGS_KEY: json.dumps(tags, separators=(",", ":")),
        _PROVENANCE_KEY: json.dumps(provenance, separators=(",", ":")),
    }


def record_from_chroma(
    chunk_id: str,
    text: str,
    meta: dict,
    embedding: tuple[float, ...] | None = None,
) -> StoredRecord:
    tags_raw = json.loads(str(meta.get(_TAGS_KEY) or "{}"))
    fields: dict[str, tuple[MetadataValue, ...]] = {}
    if isinstance(tags_raw, dict):
        for name, items in tags_raw.items():
            values: list[MetadataValue] = []
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    value = str(item.get("value") or "")
                    if not value:
                        continue
                    origin = item.get(_ORIGIN_KEY) or "unknown"
                    confidence = item.get("confidence")
                    values.append(
                        MetadataValue(
                            value=value,
                            origin=origin if origin in {"explicit", "inherited", "inferred", "unknown"} else "unknown",
                            confidence=float(confidence) if confidence is not None else None,
                        )
                    )
            fields[str(name)] = tuple(values)
    prov_raw = json.loads(str(meta.get(_PROVENANCE_KEY) or "{}"))
    if not isinstance(prov_raw, dict):
        prov_raw = {}
    pages = prov_raw.get("pages") or []
    page_tuple = tuple(int(p) for p in pages) if isinstance(pages, list) else ()
    provenance = Provenance(
        document_id=str(prov_raw.get("document_id") or meta.get("document_id") or ""),
        document_title=prov_raw.get("document_title"),
        source=prov_raw.get("source"),
        source_url=prov_raw.get("source_url"),
        version=prov_raw.get("version"),
        section=str(prov_raw.get("section") or ""),
        subsection=prov_raw.get("subsection"),
        pages=page_tuple,
        heading=str(prov_raw.get("heading") or ""),
        start_block_id=str(prov_raw.get("start_block_id") or ""),
    )
    return StoredRecord(
        chunk_id=chunk_id,
        document_id=str(meta.get("document_id") or provenance.document_id),
        text=text,
        embedding=embedding or (),
        metadata=ChunkMetadata(fields=fields),
        provenance=provenance,
        model=str(meta.get("model") or ""),
        dim=int(meta.get("dim") or 0),
    )
