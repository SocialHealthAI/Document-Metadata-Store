from __future__ import annotations

import math
from pathlib import Path

from document_metadata_store.config import StoreConfig, load_app_config
from document_metadata_store.console import format_store_run
from document_metadata_store.embeddings.model import EMBEDDING_DIM
from document_metadata_store.models import (
    Chunk,
    ChunkMetadata,
    DocumentMetadata,
    EmbeddedChunk,
    EmbeddedDocument,
    EnrichedChunk,
    MetadataValue,
    SearchHit,
)
from document_metadata_store.pipeline.embedder import EmbedOutcome, EmbedRun
from document_metadata_store.pipeline.storer import store_documents
from document_metadata_store.store.filter import matches_filters
from document_metadata_store.store.protocol import StoreCandidate, StoredRecord
from document_metadata_store.store.records import persist_document, to_stored_record
from document_metadata_store.store.search import search


def _chunk(index: int, text: str, *, heading: str = "Housing Instability") -> Chunk:
    return Chunk(
        chunk_id=f"doc:s1:c{index}",
        document_id="doc",
        section_id="s1",
        section_heading=heading,
        parent_heading=None,
        original_text=text,
        contextual_text=f"Section: {heading}\n{text}",
        start_block_id=f"p1-b{index}",
        end_block_id=f"p1-b{index}",
        pages=(1,),
    )


def _vector(seed: int) -> tuple[float, ...]:
    return tuple(float((seed + i) % 17) for i in range(EMBEDDING_DIM))


def _unit(index: int) -> tuple[float, ...]:
    values = [0.0] * EMBEDDING_DIM
    values[index % EMBEDDING_DIM] = 1.0
    return tuple(values)


def _meta(**fields) -> ChunkMetadata:
    parsed: dict[str, tuple[MetadataValue, ...]] = {
        "topic": (),
        "geography": (),
        "population": (),
        "time_period": (),
    }
    for name, texts in fields.items():
        parsed[name] = tuple(MetadataValue(text, origin="explicit") for text in texts)
    return ChunkMetadata(fields=parsed)


def _embedded(
    *chunks: EmbeddedChunk,
    document_id: str = "doc",
    source: str = "/tmp/test.pdf",
) -> EmbeddedDocument:
    return EmbeddedDocument(
        metadata=DocumentMetadata(id=document_id, title="Report", source=source),
        source=source,
        chunks=list(chunks),
        model="all-MiniLM-L6-v2",
        dim=EMBEDDING_DIM,
    )


def _ok(
    index: int,
    text: str,
    embedding: tuple[float, ...],
    metadata: ChunkMetadata | None = None,
) -> EmbeddedChunk:
    chunk = _chunk(index, text)
    return EmbeddedChunk(
        item=EnrichedChunk(chunk=chunk, metadata=metadata or _meta()),
        embedding=embedding,
        dim=len(embedding),
        model="all-MiniLM-L6-v2",
    )


def _failed(index: int, text: str) -> EmbeddedChunk:
    chunk = _chunk(index, text)
    return EmbeddedChunk(
        item=EnrichedChunk(chunk=chunk, metadata=_meta()),
        embedding=(),
        dim=0,
        model="all-MiniLM-L6-v2",
        embed_failed=True,
        embed_error="embed_batch_failed",
    )


class MemoryStore:
    def __init__(self) -> None:
        self.records: list[StoredRecord] = []

    def delete_document(self, document_id: str) -> int:
        before = len(self.records)
        self.records = [item for item in self.records if item.document_id != document_id]
        return before - len(self.records)

    def upsert(self, records: list[StoredRecord]) -> int:
        self.records.extend(records)
        return len(records)

    def query_candidates(self, embedding, n: int) -> list[StoreCandidate]:
        scored = [
            StoreCandidate(record=record, distance=_cosine_distance(embedding, record.embedding))
            for record in self.records
            if record.embedding
        ]
        scored.sort(key=lambda item: item.distance)
        return scored[:n]


def _cosine_distance(left, right) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    na = math.sqrt(sum(a * a for a in left))
    nb = math.sqrt(sum(b * b for b in right))
    if na == 0 or nb == 0:
        return 1.0
    similarity = max(-1.0, min(1.0, dot / (na * nb)))
    return 1.0 - similarity


def test_load_app_config_store_defaults() -> None:
    app = load_app_config(cwd=Path(__file__).resolve().parents[1])
    assert app.store.provider == "chroma"
    assert app.store.collection == "knowledge"
    assert app.store.persist_path.name == "metadata-store"


def test_skips_failed_embeds() -> None:
    store = MemoryStore()
    document = _embedded(
        _ok(1, "Kenya housing 2020.", _unit(0), _meta(time_period=["2020"])),
        _failed(2, "broken"),
    )
    stats = persist_document(document, store)
    assert stats.upserted == 1
    assert stats.skipped == 1
    assert len(store.records) == 1
    assert store.records[0].chunk_id.endswith("c1")
    assert to_stored_record(document, document.chunks[1]) is None


def test_replace_on_rerun_does_not_duplicate() -> None:
    store = MemoryStore()
    first = _embedded(_ok(1, "First version.", _unit(0), _meta(geography=["Kenya"])))
    second = _embedded(
        _ok(1, "Second version.", _unit(1), _meta(geography=["Brazil"])),
        _ok(2, "New chunk.", _unit(2), _meta(geography=["Kenya"])),
    )
    persist_document(first, store)
    persist_document(second, store)
    assert [item.chunk_id for item in store.records] == ["doc:s1:c1", "doc:s1:c2"]
    assert store.records[0].metadata.texts_for("geography") == ("Brazil",)


def test_time_filter_2020_matches_expanded_years() -> None:
    store = MemoryStore()
    document = _embedded(
        _ok(
            1,
            "Programs ran 2019 to 2022.",
            _unit(0),
            _meta(time_period=["2019", "2020", "2021", "2022"], geography=["Kenya"]),
        ),
        _ok(2, "Unrelated 2010 note.", _unit(1), _meta(time_period=["2010"])),
    )
    persist_document(document, store)
    hits = search(
        "housing programs",
        filters={"time_period": ["2020"]},
        k=8,
        store=store,
        encode=lambda texts: [_unit(0) for _ in texts],
    )
    assert [hit.chunk_id for hit in hits] == ["doc:s1:c1"]
    assert hits[0].metadata["time_period"] == ("2019", "2020", "2021", "2022")
    assert hits[0].provenance.section == "Housing Instability"
    assert hits[0].provenance.pages == (1,)
    assert isinstance(hits[0], SearchHit)
    assert hits[0].text.startswith("Section:")
    assert not hasattr(hits[0], "embedding") or getattr(hits[0], "embedding", None) is None


def test_empty_tags_do_not_satisfy_required_filter() -> None:
    store = MemoryStore()
    persist_document(
        _embedded(_ok(1, "No geography tagged.", _unit(0), _meta(topic=["housing"]))),
        store,
    )
    hits = search(
        "housing",
        filters={"geography": ["Kenya"]},
        k=8,
        store=store,
        encode=lambda texts: [_unit(0) for _ in texts],
    )
    assert hits == []


def test_or_within_field_and_across_fields() -> None:
    kenya = _ok(1, "Kenya 2020.", _unit(0), _meta(geography=["Kenya"], time_period=["2020"]))
    ohio = _ok(2, "Ohio 2020.", _unit(1), _meta(geography=["OH"], time_period=["2020"]))
    kenya_old = _ok(3, "Kenya 2010.", _unit(2), _meta(geography=["Kenya"], time_period=["2010"]))
    store = MemoryStore()
    persist_document(_embedded(kenya, ohio, kenya_old), store)
    hits = search(
        "query",
        filters={"geography": ["Kenya", "OH"], "time_period": ["2020"]},
        k=8,
        store=store,
        encode=lambda texts: [_unit(0) for _ in texts],
    )
    assert {hit.chunk_id for hit in hits} == {"doc:s1:c1", "doc:s1:c2"}


def test_matches_filters_empty_list_unconstrained() -> None:
    meta = _meta(geography=["Kenya"])
    assert matches_filters(meta, {"geography": []})
    assert matches_filters(meta, None)


def test_console_samples_not_every_record_or_vector() -> None:
    chunks = [
        _ok(i, f"Housing paragraph {i}.", _vector(i), _meta(topic=["housing"]))
        for i in range(1, 8)
    ]
    run = store_documents(
        EmbedRun(
            model="all-MiniLM-L6-v2",
            dim=EMBEDDING_DIM,
            batch_size=50,
            outcomes=[
                EmbedOutcome(
                    path="documents/example.pdf",
                    document=_embedded(*chunks),
                    records=7,
                    embedded=7,
                    embed_failed=0,
                )
            ],
        ),
        StoreConfig(persist_path=Path("/tmp/unused")),
        store=MemoryStore(),
    )
    text = format_store_run(run)
    assert "document-store" in text
    assert "provider: chroma" in text
    assert "collection: knowledge" in text
    assert "c1   topic=[housing]" in text
    assert "c5   topic=[housing]" in text
    assert "c7   topic=[housing]" not in text
    sample = text.split("sample:")[-1]
    assert "topic=" in sample
    vector = run.outcomes[0].document.chunks[0].embedding
    assert f"{vector[0]}," not in text


def test_pipeline_failure_continues() -> None:
    class Boom:
        def delete_document(self, document_id: str) -> int:
            raise RuntimeError("disk full")

        def upsert(self, records):
            return 0

        def query_candidates(self, embedding, n: int):
            return []

    run = store_documents(
        EmbedRun(
            model="all-MiniLM-L6-v2",
            dim=EMBEDDING_DIM,
            batch_size=50,
            outcomes=[
                EmbedOutcome(
                    path="documents/a.pdf",
                    document=_embedded(_ok(1, "a", _unit(0))),
                    records=1,
                    embedded=1,
                    embed_failed=0,
                ),
                EmbedOutcome(
                    path="documents/b.pdf",
                    document=_embedded(_ok(1, "b", _unit(1))),
                    records=1,
                    embedded=1,
                    embed_failed=0,
                ),
            ],
        ),
        StoreConfig(),
        store=Boom(),
    )
    assert run.counts()["failed"] == 2
    assert run.outcomes == []


def test_chroma_roundtrip_replace_and_year_filter(tmp_path: Path) -> None:
    from document_metadata_store.store.chroma import ChromaMetadataStore

    store = ChromaMetadataStore(
        StoreConfig(persist_path=tmp_path / "chroma", collection="knowledge")
    )
    first = _embedded(
        _ok(
            1,
            "Programs ran 2019 to 2022.",
            _unit(0),
            _meta(time_period=["2019", "2020", "2021", "2022"], geography=["Kenya"]),
        )
    )
    persist_document(first, store)
    persist_document(first, store)
    hits = search(
        "housing programs",
        filters={"time_period": ["2020"]},
        k=8,
        store=store,
        encode=lambda texts: [_unit(0) for _ in texts],
    )
    assert len(hits) == 1
    assert hits[0].chunk_id.endswith("c1")
    assert hits[0].provenance.document_id == "doc"
    assert "embedding" not in hits[0].__dataclass_fields__
