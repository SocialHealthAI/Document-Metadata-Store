from __future__ import annotations

from document_metadata_store.config import LlmConfig, MetadataConfig
from document_metadata_store.console import format_embed_run
from document_metadata_store.embeddings.engine import embed_document
from document_metadata_store.embeddings.model import EMBEDDING_DIM, EMBEDDING_MODEL
from document_metadata_store.metadata.engine import extract_document
from document_metadata_store.metadata.llm import empty_metadata
from document_metadata_store.metadata.schema import default_schema
from document_metadata_store.models import (
    Chunk,
    ChunkedDocument,
    ChunkMetadata,
    DocumentMetadata,
    MetadataValue,
)
from document_metadata_store.pipeline.chunker import ChunkOutcome, ChunkRun
from document_metadata_store.pipeline.embedder import embed_documents
from document_metadata_store.pipeline.extractor import extract_metadata_documents


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


def _chunked(*chunks: Chunk) -> ChunkedDocument:
    return ChunkedDocument(
        metadata=DocumentMetadata(id="doc", title="Report"),
        source="/tmp/test.pdf",
        chunks=list(chunks),
    )


def _llm() -> LlmConfig:
    return LlmConfig(provider="anthropic", api_key="test-key")


def _config(**overrides) -> MetadataConfig:
    return MetadataConfig(
        enabled=overrides.get("enabled", True),
        batch_size=overrides.get("batch_size", 50),
    )


def _fake_vector(seed: int) -> tuple[float, ...]:
    return tuple(float((seed + i) % 17) for i in range(EMBEDDING_DIM))


def _encode_from_text(chunks):
    seen: list[str] = []
    parsed = {}
    for item in chunks:
        seen.append(item.chunk.contextual_text)
        parsed[item.chunk_id] = _fake_vector(len(item.chunk.contextual_text))
    _encode_from_text.seen = seen  # type: ignore[attr-defined]
    return parsed


def test_embeds_contextual_text_not_metadata_tags() -> None:
    schema = default_schema()

    def completer(chunks, _schema, llm):
        chunk = chunks[0]
        return {
            chunk.chunk_id: ChunkMetadata(
                fields={
                    "topic": (MetadataValue("diabetes", origin="inferred"),),
                    "geography": (MetadataValue("United States", origin="explicit"),),
                    "population": (),
                    "time_period": (),
                }
            )
        }

    enriched = extract_document(
        _chunked(_chunk(1, "Kenya saw housing gains in 2022.")),
        schema,
        _config(),
        _llm(),
        complete_batch=completer,
    )
    texts: list[str] = []

    def embedder(chunks):
        for item in chunks:
            texts.append(item.chunk.contextual_text)
            assert item.chunk.original_text in item.chunk.contextual_text
        return {item.chunk_id: _fake_vector(1) for item in chunks}

    embedded = embed_document(enriched, batch_size=50, embed_batch=embedder)
    assert texts == [enriched.chunks[0].chunk.contextual_text]
    encode_payload = texts[0]
    assert "diabetes" not in encode_payload
    assert "United States" not in encode_payload
    assert embedded.chunks[0].dim == EMBEDDING_DIM
    assert len(embedded.chunks[0].embedding) == EMBEDDING_DIM
    assert not embedded.chunks[0].embed_failed


def test_metadata_disabled_still_embeds() -> None:
    enriched = extract_document(
        _chunked(_chunk(1, "Adults in Brazil faced food insecurity in 2015.")),
        default_schema(),
        _config(enabled=False),
        _llm(),
        complete_batch=lambda chunks, schema, llm: (_ for _ in ()).throw(AssertionError("no llm")),
    )
    assert enriched.skipped
    embedded = embed_document(enriched, batch_size=10, embed_batch=_encode_from_text)
    assert embedded.embedded_count() == 1
    assert embedded.chunks[0].dim == EMBEDDING_DIM
    assert embedded.model == EMBEDDING_MODEL


def test_batches_encode_calls() -> None:
    calls: list[int] = []

    def embedder(chunks):
        calls.append(len(chunks))
        return {item.chunk_id: _fake_vector(len(chunks)) for item in chunks}

    chunks = [_chunk(i, f"Paragraph {i} about living conditions.") for i in range(1, 6)]
    enriched = extract_document(
        _chunked(*chunks),
        default_schema(),
        _config(enabled=False),
        LlmConfig(),
    )
    embed_document(enriched, batch_size=2, embed_batch=embedder)
    assert calls == [2, 2, 1]


def test_encode_failure_marks_chunk_and_continues() -> None:
    def embedder(chunks):
        if len(chunks) > 1:
            return None
        if chunks[0].chunk_id.endswith("c1"):
            return None
        return {chunks[0].chunk_id: _fake_vector(2)}

    chunks = [_chunk(1, "First."), _chunk(2, "Second.")]
    enriched = extract_document(
        _chunked(*chunks),
        default_schema(),
        _config(enabled=False),
        LlmConfig(),
    )
    embedded = embed_document(enriched, batch_size=2, embed_batch=embedder)
    assert embedded.chunks[0].embed_failed
    assert embedded.chunks[0].embedding == ()
    assert not embedded.chunks[1].embed_failed
    assert embedded.chunks[1].dim == EMBEDDING_DIM
    assert embedded.embed_failed_count() == 1


def test_console_samples_not_every_chunk_or_vector() -> None:
    chunks = [_chunk(i, f"Housing paragraph {i}.") for i in range(1, 8)]
    run = extract_metadata_documents(
        ChunkRun(
            outcomes=[
                ChunkOutcome(
                    path="documents/example.pdf",
                    document=_chunked(*chunks),
                    chunks=len(chunks),
                    max_chars=20,
                    oversized_atomic=0,
                )
            ]
        ),
        _config(enabled=False),
        LlmConfig(),
        schema=default_schema(),
    )
    embed_run = embed_documents(run, batch_size=50, embed_batch=_encode_from_text)
    text = format_embed_run(embed_run)
    assert "document-embed" in text
    assert "model: all-MiniLM-L6-v2" in text
    assert "dim: 384" in text
    assert "c1   chars=" in text
    assert "c5   chars=" in text
    assert "c7   chars=" not in text
    sample = text.split("sample:")[-1]
    assert "chars=" in sample
    for token in embed_run.outcomes[0].document.chunks[0].embedding[:8]:
        assert f"{token}," not in text


def test_console_preview_adds_contextual_text() -> None:
    chunks = [_chunk(1, "Kenya saw housing gains in 2022.")]
    run = extract_metadata_documents(
        ChunkRun(
            outcomes=[
                ChunkOutcome(
                    path="documents/example.pdf",
                    document=_chunked(*chunks),
                    chunks=1,
                    max_chars=40,
                    oversized_atomic=0,
                )
            ]
        ),
        _config(enabled=False),
        LlmConfig(),
        schema=default_schema(),
    )
    embed_run = embed_documents(run, batch_size=10, embed_batch=_encode_from_text)
    text = format_embed_run(embed_run, preview_blocks=5)
    assert "Section: Housing Instability" in text
    assert "Kenya saw housing gains" in text
    vector = embed_run.outcomes[0].document.chunks[0].embedding
    assert str(vector[0]) not in text
