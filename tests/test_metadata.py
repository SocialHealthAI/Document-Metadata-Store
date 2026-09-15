from __future__ import annotations

from pathlib import Path

from document_metadata_store.config import LlmConfig, MetadataConfig
from document_metadata_store.console import format_metadata_run
from document_metadata_store.metadata.engine import extract_document
from document_metadata_store.metadata.llm import LlmBatchOutcome, _parse_batch, empty_metadata
from document_metadata_store.metadata.schema import default_schema, load_metadata_schema
from document_metadata_store.models import (
    Chunk,
    ChunkedDocument,
    ChunkMetadata,
    DocumentMetadata,
    MetadataValue,
)
from document_metadata_store.pipeline.chunker import ChunkOutcome, ChunkRun
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


def test_schema_lists_four_fields() -> None:
    schema = load_metadata_schema(Path(__file__).resolve().parents[1] / "metadata_schema.yaml")
    assert schema.field_names == ("topic", "geography", "population", "time_period")


def test_disabled_skips_llm() -> None:
    calls: list[int] = []

    def completer(chunks, schema, llm):
        calls.append(len(chunks))
        return {}

    doc = extract_document(
        _chunked(_chunk(1, "Kenya saw housing gains in 2022.")),
        default_schema(),
        _config(enabled=False),
        _llm(),
        complete_batch=completer,
    )
    assert doc.skipped
    assert calls == []
    assert not doc.chunks[0].metadata.has_any()


def test_no_llm_key_leaves_unknown() -> None:
    doc = extract_document(
        _chunked(_chunk(1, "Kenya saw housing gains in 2022.")),
        default_schema(),
        _config(),
        LlmConfig(),
    )
    assert not doc.skipped
    assert doc.chunks[0].metadata.texts_for("topic") == ()
    assert not doc.chunks[0].llm_failed


def test_lists_and_mixed_topic() -> None:
    schema = default_schema()

    def completer(chunks, _schema, llm):
        assert len(chunks) == 1
        return {
            chunks[0].chunk_id: ChunkMetadata(
                fields={
                    "topic": (
                        MetadataValue("housing instability", origin="explicit"),
                        MetadataValue("diabetes", origin="inferred"),
                    ),
                    "geography": (MetadataValue("Kenya", origin="explicit"),),
                    "population": (),
                    "time_period": (
                        MetadataValue("2022", origin="explicit"),
                        MetadataValue("2020-2023", origin="inferred"),
                    ),
                }
            )
        }

    doc = extract_document(
        _chunked(_chunk(1, "In Kenya, housing instability rose in 2022 as diabetes treatment lagged.")),
        schema,
        _config(),
        _llm(),
        complete_batch=completer,
    )
    meta = doc.chunks[0].metadata
    assert meta.texts_for("topic") == ("housing instability", "diabetes")
    assert meta.texts_for("geography") == ("Kenya",)
    assert meta.texts_for("time_period") == ("2022", "2020-2023")
    assert meta.texts_for("population") == ()


def test_batches_chunks_to_llm() -> None:
    calls: list[int] = []

    def completer(chunks, schema, llm):
        calls.append(len(chunks))
        return {chunk.chunk_id: empty_metadata(schema) for chunk in chunks}

    chunks = [_chunk(i, f"Paragraph number {i} about living conditions.") for i in range(1, 6)]
    extract_document(
        _chunked(*chunks),
        default_schema(),
        _config(batch_size=2),
        _llm(),
        complete_batch=completer,
    )
    assert calls == [2, 2, 1]


def test_batch_parse_failure_marks_unknown() -> None:
    def completer(chunks, schema, llm):
        return None

    doc = extract_document(
        _chunked(_chunk(1, "Text."), _chunk(2, "More text.")),
        default_schema(),
        _config(batch_size=10),
        _llm(),
        complete_batch=completer,
    )
    assert all(item.llm_failed for item in doc.chunks)
    assert all(not item.metadata.has_any() for item in doc.chunks)
    assert doc.llm_errors == ("llm_batch_failed",)


def test_console_prints_llm_error_code() -> None:
    def completer(chunks, schema, llm):
        return LlmBatchOutcome(
            error="anthropic 404: model: claude-sonnet-5"
        )

    run = extract_metadata_documents(
        ChunkRun(
            outcomes=[
                ChunkOutcome(
                    path="documents/example.pdf",
                    document=_chunked(_chunk(1, "Text.")),
                    chunks=1,
                    max_chars=4,
                    oversized_atomic=0,
                )
            ]
        ),
        _config(),
        _llm(),
        schema=default_schema(),
        complete_batch=completer,
    )
    text = format_metadata_run(run)
    assert "llm_error: anthropic 404: model: claude-sonnet-5" in text
    assert "llm_failed: 1" in text


def test_response_payload_joins_text_after_thinking() -> None:
    from types import SimpleNamespace

    from document_metadata_store.metadata.llm import _response_payload

    response = SimpleNamespace(
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        content=[
            SimpleNamespace(type="thinking", text=None, thinking="plan"),
            SimpleNamespace(type="text", text='{"0": {"topic": []}}'),
        ],
    )
    raw, diag = _response_payload(response)
    assert '{"0": {"topic": []}}' in raw
    assert "thinking" in diag
    assert "text" in diag
    assert "stop=end_turn" in diag


def test_console_lists_ok_and_failed_chunk_sizes() -> None:
    def completer(chunks, schema, llm):
        if len(chunks) > 1:
            return None
        chunk = chunks[0]
        if chunk.chunk_id.endswith("c2"):
            return {
                chunk.chunk_id: ChunkMetadata(
                    fields={
                        "topic": (MetadataValue("housing", origin="explicit"),),
                        "geography": (),
                        "population": (),
                        "time_period": (),
                    }
                )
            }
        return LlmBatchOutcome(error="empty_response; stop=end_turn blocks=thinking in=12 out=0")

    run = extract_metadata_documents(
        ChunkRun(
            outcomes=[
                ChunkOutcome(
                    path="documents/example.pdf",
                    document=_chunked(_chunk(1, "A" * 40), _chunk(2, "B" * 80)),
                    chunks=2,
                    max_chars=80,
                    oversized_atomic=0,
                )
            ]
        ),
        _config(batch_size=2),
        _llm(),
        schema=default_schema(),
        complete_batch=completer,
    )
    text = format_metadata_run(run)
    assert "llm_ok:     1  c2" in text
    assert "llm_failed: 1" in text
    assert "c1  40 chars" in text
    assert "empty_response; stop=end_turn" in text


def test_parse_batch_json() -> None:
    schema = default_schema()
    chunk = _chunk(1, "Adults in Brazil faced food insecurity in 2015.")
    raw = """
    {
      "doc:s1:c1": {
        "topic": [{"value": "food insecurity", "origin": "explicit"}],
        "geography": [{"value": "Brazil", "origin": "explicit"}],
        "population": [{"value": "adults", "origin": "inherited"}],
        "time_period": ["2015"]
      }
    }
    """
    parsed = _parse_batch(raw, [chunk], schema)
    assert parsed is not None
    meta = parsed[chunk.chunk_id]
    assert meta.texts_for("topic") == ("food insecurity",)
    assert meta.texts_for("geography") == ("Brazil",)
    assert meta.values_for("population")[0].origin == "inherited"
    assert meta.texts_for("time_period") == ("2015",)


def test_failed_batch_splits_until_success() -> None:
    calls: list[int] = []

    def completer(chunks, schema, llm):
        calls.append(len(chunks))
        if len(chunks) > 1:
            return None
        chunk = chunks[0]
        return {
            chunk.chunk_id: ChunkMetadata(
                fields={
                    "topic": (MetadataValue("housing", origin="explicit"),),
                    "geography": (),
                    "population": (),
                    "time_period": (),
                }
            )
        }

    chunks = [_chunk(i, f"Paragraph {i} about housing.") for i in range(1, 5)]
    doc = extract_document(
        _chunked(*chunks),
        default_schema(),
        _config(batch_size=4),
        _llm(),
        complete_batch=completer,
    )
    assert all(item.metadata.texts_for("topic") == ("housing",) for item in doc.chunks)
    assert not any(item.llm_failed for item in doc.chunks)
    assert 4 in calls and 1 in calls
    assert doc.llm_errors == ()
    assert doc.llm_retries >= 1
    run = extract_metadata_documents(
        ChunkRun(
            outcomes=[
                ChunkOutcome(
                    path="documents/example.pdf",
                    document=_chunked(*chunks),
                    chunks=len(chunks),
                    max_chars=40,
                    oversized_atomic=0,
                )
            ]
        ),
        _config(batch_size=4),
        _llm(),
        schema=default_schema(),
        complete_batch=completer,
    )
    text = format_metadata_run(run)
    assert "llm_retried:" in text
    assert "llm_error:" not in text


def test_recovered_max_tokens_does_not_print_llm_error() -> None:
    """WHO-style truncated JSON on a large batch, then success after split."""

    def completer(chunks, schema, llm):
        if len(chunks) > 1:
            return LlmBatchOutcome(
                error=(
                    'json_parse: ```json { "0": { "topic": [ {"value":"housing" ; '
                    "stop=max_tokens blocks=thinking,text in=22351 out=16384"
                )
            )
        chunk = chunks[0]
        return {
            chunk.chunk_id: ChunkMetadata(
                fields={
                    "topic": (MetadataValue("housing", origin="explicit"),),
                    "geography": (),
                    "population": (),
                    "time_period": (),
                }
            )
        }

    run = extract_metadata_documents(
        ChunkRun(
            outcomes=[
                ChunkOutcome(
                    path="documents/WHO.pdf",
                    document=_chunked(*[_chunk(i, f"Chunk {i} housing text.") for i in range(1, 5)]),
                    chunks=4,
                    max_chars=20,
                    oversized_atomic=0,
                )
            ]
        ),
        _config(batch_size=4),
        _llm(),
        schema=default_schema(),
        complete_batch=completer,
    )
    text = format_metadata_run(run)
    assert run.outcomes[0].llm_failed == 0
    assert run.outcomes[0].document.llm_retries >= 1
    assert "llm_retried:" in text
    assert "llm_error:" not in text
    assert "json_parse:" not in text


def test_parse_batch_accepts_integer_keys() -> None:
    schema = default_schema()
    chunk = _chunk(1, "Adults in Brazil faced food insecurity in 2015.")
    raw = """
    {
      "0": {
        "topic": [{"value": "food insecurity", "origin": "explicit"}],
        "geography": [{"value": "Brazil", "origin": "explicit"}],
        "population": [],
        "time_period": ["2015"]
      }
    }
    """
    parsed = _parse_batch(raw, [chunk], schema)
    assert parsed is not None
    assert parsed[chunk.chunk_id].texts_for("geography") == ("Brazil",)


def test_histogram_console_samples_tagged_not_leading_empty() -> None:
    schema = default_schema()

    def completer(chunks, _schema, llm):
        out = {}
        for chunk in chunks:
            if chunk.chunk_id.endswith("c6"):
                out[chunk.chunk_id] = ChunkMetadata(
                    fields={
                        "topic": (MetadataValue("Housing", origin="explicit"),),
                        "geography": (MetadataValue("Kenya", origin="explicit"),),
                        "population": (),
                        "time_period": (),
                    }
                )
            else:
                out[chunk.chunk_id] = empty_metadata(_schema)
        return out

    chunks = [_chunk(i, f"Paragraph {i}.") for i in range(1, 8)]
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
        _config(),
        _llm(),
        schema=schema,
        complete_batch=completer,
    )
    text = format_metadata_run(run)
    assert "sample (tagged):" in text
    assert "c6   topic=[Housing]" in text
    assert "geo=[Kenya]" in text


def test_histogram_console_samples_not_every_chunk() -> None:
    schema = default_schema()

    def completer(chunks, _schema, llm):
        out = {}
        for chunk in chunks:
            out[chunk.chunk_id] = ChunkMetadata(
                fields={
                    "topic": (MetadataValue("Housing", origin="explicit"),),
                    "geography": (),
                    "population": (),
                    "time_period": (),
                }
            )
        return out

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
        _config(),
        _llm(),
        schema=schema,
        complete_batch=completer,
    )
    text = format_metadata_run(run)
    assert "document-metadata" in text
    assert "topic:" in text
    assert "Housing (7)" in text
    assert text.count("c1") >= 1
    assert "c7   topic" not in text
    assert "sample (tagged):" in text
