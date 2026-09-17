from __future__ import annotations

from pathlib import Path

from document_metadata_store.config import StoreConfig
from document_metadata_store.store.protocol import MetadataStore, StoreCandidate, StoredRecord
from document_metadata_store.store.records import chroma_metadata, record_from_chroma


class ChromaMetadataStore:
    def __init__(self, config: StoreConfig) -> None:
        import chromadb

        path = Path(config.persist_path)
        path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(path))
        self._collection = client.get_or_create_collection(
            name=config.collection,
            metadata={"hnsw:space": "cosine"},
        )

    def delete_document(self, document_id: str) -> int:
        existing = self._collection.get(
            where={"document_id": document_id}, include=["metadatas"]
        )
        ids = existing.get("ids") or []
        if not ids:
            return 0
        self._collection.delete(ids=ids)
        return len(ids)

    def upsert(self, records: list[StoredRecord]) -> int:
        if not records:
            return 0
        self._collection.upsert(
            ids=[record.chunk_id for record in records],
            embeddings=[list(record.embedding) for record in records],
            documents=[record.text for record in records],
            metadatas=[chroma_metadata(record) for record in records],
        )
        return len(records)

    def query_candidates(
        self, embedding: list[float] | tuple[float, ...], n: int
    ) -> list[StoreCandidate]:
        count = self._collection.count()
        if count == 0 or n < 1:
            return []
        take = min(n, count)
        result = self._collection.query(
            query_embeddings=[list(map(float, embedding))],
            n_results=take,
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        candidates: list[StoreCandidate] = []
        for chunk_id, text, meta, distance in zip(ids, documents, metadatas, distances, strict=False):
            payload = dict(meta or {})
            record = record_from_chroma(str(chunk_id), str(text or ""), payload)
            candidates.append(StoreCandidate(record=record, distance=float(distance)))
        return candidates
