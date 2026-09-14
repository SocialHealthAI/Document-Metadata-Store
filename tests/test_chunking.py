from __future__ import annotations

from document_metadata_store.chunking.engine import chunk_document
from document_metadata_store.config import ChunkingConfig, LlmConfig, PreprocessingConfig
from document_metadata_store.console import format_chunk_run
from document_metadata_store.models import (
    AnnotatedBlock,
    Block,
    BodyUnit,
    DocumentMetadata,
    Location,
    SectionNode,
    StructuredDocument,
)
from document_metadata_store.pipeline.chunker import chunk_documents
from document_metadata_store.pipeline.structure import StructureOutcome, StructureRun
from document_metadata_store.preprocess.engine import preprocess_document
from document_metadata_store.structure.engine import extract_structure
from document_metadata_store.models import NormalizedDocument, Page


def _block(text: str, *, page: int = 1, index: int = 1, kind: str = "text") -> Block:
    return Block(
        block_id=f"p{page}-b{index}",
        kind=kind,  # type: ignore[arg-type]
        text=text,
        location=Location(page=page),
    )


def _annotated(text: str, *, page: int = 1, index: int = 1, kind: str = "text") -> AnnotatedBlock:
    return AnnotatedBlock(block=_block(text, page=page, index=index, kind=kind))


def _doc(rows: list[tuple[int, str]], *, title: str | None = "Report") -> NormalizedDocument:
    pages: dict[int, list[Block]] = {}
    for page_number, text in rows:
        blocks = pages.setdefault(page_number, [])
        index = len(blocks) + 1
        blocks.append(_block(text, page=page_number, index=index))
    page_list = [Page(page_number=number, blocks=pages[number]) for number in sorted(pages)]
    return NormalizedDocument(
        metadata=DocumentMetadata(id="test", title=title, document_type="pdf"),
        source="/tmp/test.pdf",
        pages=page_list,
    )


def _prep(rows: list[tuple[int, str]], *, title: str | None = "Report"):
    config = PreprocessingConfig()
    return preprocess_document(_doc(rows, title=title), config, LlmConfig()), config


def _chunking(**overrides) -> ChunkingConfig:
    return ChunkingConfig(
        target_size=overrides.get("target_size", 80),
        max_size=overrides.get("max_size", 120),
        min_size=overrides.get("min_size", 20),
        overlap=overrides.get("overlap", 10),
    )


def test_nested_headings_appear_in_contextual_text() -> None:
    processed, prep = _prep(
        [
            (1, "Chapter 1 Methods"),
            (1, "This chapter explains the main argument in several words of prose."),
            (1, "1.2 Updates since the Commission"),
            (1, "The following paragraphs describe progress against earlier targets."),
        ]
    )
    structured = extract_structure(processed, prep, LlmConfig())
    chunked = chunk_document(structured, _chunking())
    child = next(c for c in chunked.chunks if c.section_heading.startswith("1.2"))
    assert child.parent_heading and "Chapter 1" in child.parent_heading
    assert "Section: Chapter 1 Methods" in child.contextual_text
    assert "Subsection: 1.2" in child.contextual_text
    assert "progress against earlier targets" in child.original_text
    assert child.original_text.startswith("The following") or "progress" in child.original_text


def test_oversized_paragraph_splits_on_sentences() -> None:
    sentence = "This finding is supported by multiple independent studies of housing policy."
    body = " ".join([sentence] * 8)
    node = SectionNode(
        section_id="s1",
        heading="Recent Trends",
        level=1,
        start_block_id="p1-b1",
        body=[BodyUnit(kind="paragraph", blocks=[_annotated(body)])],
    )
    structured = StructuredDocument(
        metadata=DocumentMetadata(id="doc", title="Report"),
        source="/tmp/t.pdf",
        sections=[node],
    )
    chunked = chunk_document(structured, _chunking(target_size=80, max_size=120))
    assert chunked.chunk_count() >= 2
    assert all(len(chunk.original_text) <= 200 for chunk in chunked.chunks)
    assert all("Recent Trends" in chunk.contextual_text for chunk in chunked.chunks)
    combined = " ".join(chunk.original_text for chunk in chunked.chunks)
    assert "housing policy" in combined


def test_atomic_table_is_not_split() -> None:
    table = "A" * 400
    node = SectionNode(
        section_id="s1",
        heading="Results",
        level=1,
        start_block_id="p1-b1",
        body=[
            BodyUnit(kind="table", blocks=[_annotated(table, kind="table")]),
        ],
    )
    structured = StructuredDocument(
        metadata=DocumentMetadata(id="doc", title="Report"),
        source="/tmp/t.pdf",
        sections=[node],
    )
    chunked = chunk_document(structured, _chunking(max_size=120))
    assert chunked.chunk_count() == 1
    assert chunked.chunks[0].original_text == table
    assert chunked.chunks[0].oversized_atomic


def test_short_sections_do_not_merge() -> None:
    first = SectionNode(
        section_id="s1",
        heading="Chapter 1 Methods",
        level=2,
        start_block_id="p1-b1",
        body=[BodyUnit(kind="paragraph", blocks=[_annotated("Short methods note.")])],
    )
    second = SectionNode(
        section_id="s2",
        heading="Chapter 2 Findings",
        level=2,
        start_block_id="p2-b1",
        body=[BodyUnit(kind="paragraph", blocks=[_annotated("Short findings note.")])],
    )
    structured = StructuredDocument(
        metadata=DocumentMetadata(id="doc", title="Report"),
        source="/tmp/t.pdf",
        sections=[first, second],
    )
    chunked = chunk_document(structured, _chunking(min_size=300, target_size=1000, max_size=1500))
    assert chunked.chunk_count() == 2
    assert chunked.chunks[0].section_id == "s1"
    assert chunked.chunks[1].section_id == "s2"
    assert "findings" not in chunked.chunks[0].original_text.lower()


def test_same_section_overlap_is_in_contextual_text_only() -> None:
    sentences = [
        f"Sentence number {index} adds enough characters to force a split here."
        for index in range(1, 12)
    ]
    node = SectionNode(
        section_id="s1",
        heading="Housing",
        level=1,
        start_block_id="p1-b1",
        body=[BodyUnit(kind="paragraph", blocks=[_annotated(" ".join(sentences))])],
    )
    structured = StructuredDocument(
        metadata=DocumentMetadata(id="doc", title="Report"),
        source="/tmp/t.pdf",
        sections=[node],
    )
    chunked = chunk_document(structured, _chunking(target_size=80, max_size=120, overlap=15))
    assert chunked.chunk_count() >= 2
    first, second = chunked.chunks[0], chunked.chunks[1]
    tail = first.original_text[-15:]
    assert tail in second.contextual_text
    assert not second.original_text.startswith(tail)
    assert f"{first.document_id}:{first.section_id}:c1" == first.chunk_id


def test_later_chunks_advance_start_block_id() -> None:
    blocks = [
        _annotated(f"Block {index} continues the evidence discussion with enough words.", page=index, index=1)
        for index in range(1, 8)
    ]
    node = SectionNode(
        section_id="s1",
        heading="Housing",
        level=1,
        start_block_id="p1-b1",
        body=[BodyUnit(kind="paragraph", blocks=blocks)],
    )
    structured = StructuredDocument(
        metadata=DocumentMetadata(id="doc", title="Report"),
        source="/tmp/t.pdf",
        sections=[node],
    )
    chunked = chunk_document(structured, _chunking(target_size=80, max_size=120))
    starts = [chunk.start_block_id for chunk in chunked.chunks]
    assert chunked.chunk_count() >= 2
    assert len(set(starts)) >= 2


def test_text_without_sentences_wraps_at_max_size() -> None:
    body = " ".join(["word"] * 400)
    node = SectionNode(
        section_id="s1",
        heading="Notes",
        level=1,
        start_block_id="p1-b1",
        body=[BodyUnit(kind="paragraph", blocks=[_annotated(body)])],
    )
    structured = StructuredDocument(
        metadata=DocumentMetadata(id="doc", title="Report"),
        source="/tmp/t.pdf",
        sections=[node],
    )
    chunked = chunk_document(structured, _chunking(target_size=80, max_size=120))
    assert chunked.chunk_count() >= 2
    assert all(len(chunk.original_text) <= 120 for chunk in chunked.chunks)
    assert not any(chunk.oversized_atomic for chunk in chunked.chunks)


def test_console_prints_chunk_list() -> None:
    processed, prep = _prep(
        [
            (1, "Chapter 1 Methods"),
            (1, "This chapter explains the main argument in several words of prose."),
        ]
    )
    structured = extract_structure(processed, prep, LlmConfig())
    run = StructureRun()
    run.outcomes.append(
        StructureOutcome(
            path="documents/sample.pdf",
            document=structured,
            sections=structured.section_count(),
            subsections=structured.subsection_count(),
            max_depth=structured.max_depth(),
            implicit=structured.implicit_title,
        )
    )
    chunked = chunk_documents(run, _chunking())
    text = format_chunk_run(chunked)
    assert "document-chunk" in text
    assert "chunks:" in text
    assert "Chapter 1 Methods" in text
    assert "This chapter explains" not in text
