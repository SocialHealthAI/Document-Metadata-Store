from __future__ import annotations

import re
from dataclasses import dataclass

from document_metadata_store.config import ChunkingConfig
from document_metadata_store.models import (
    AnnotatedBlock,
    BodyUnit,
    Chunk,
    ChunkedDocument,
    SectionNode,
    StructuredDocument,
)

_ATOMIC = frozenset({"table", "list_item", "caption"})
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass
class _Span:
    start: int
    end: int
    block: AnnotatedBlock


@dataclass
class _Piece:
    text: str
    blocks: list[AnnotatedBlock]
    atomic: bool


def chunk_document(
    document: StructuredDocument,
    config: ChunkingConfig | None = None,
) -> ChunkedDocument:
    config = config or ChunkingConfig()
    chunks: list[Chunk] = []
    sequence = 1
    for node in document.sections:
        sequence = _walk(node, [], document, config, chunks, sequence)
    return ChunkedDocument(
        metadata=document.metadata,
        source=document.source,
        chunks=chunks,
    )


def _walk(
    node: SectionNode,
    ancestors: list[str],
    document: StructuredDocument,
    config: ChunkingConfig,
    chunks: list[Chunk],
    sequence: int,
) -> int:
    headings = [*ancestors, node.heading]
    parent = ancestors[-1] if ancestors else None
    sequence = _pack_section(node, headings, parent, document, config, chunks, sequence)
    for child in node.children:
        sequence = _walk(child, headings, document, config, chunks, sequence)
    return sequence


def _pack_section(
    node: SectionNode,
    headings: list[str],
    parent: str | None,
    document: StructuredDocument,
    config: ChunkingConfig,
    chunks: list[Chunk],
    sequence: int,
) -> int:
    pieces: list[_Piece] = []
    for unit in node.body:
        pieces.extend(_pieces_from_unit(unit, config.max_size))
    if not pieces:
        return sequence

    buffer: list[_Piece] = []
    previous_original = ""
    local = 1

    def flush() -> None:
        nonlocal sequence, previous_original, buffer, local
        if not buffer:
            return
        original = _join(buffer)
        overlap = _overlap_text(previous_original, config.overlap)
        start = buffer[0].blocks[0].block_id if buffer[0].blocks else node.start_block_id
        last_blocks = buffer[-1].blocks or buffer[0].blocks
        end = last_blocks[-1].block_id if last_blocks else start
        pages = tuple(
            dict.fromkeys(block.location.page for piece in buffer for block in piece.blocks)
        )
        atomic = all(piece.atomic for piece in buffer) and len(buffer) == 1
        chunks.append(
            Chunk(
                chunk_id=f"{document.metadata.id}:{node.section_id}:c{local}",
                document_id=document.metadata.id,
                section_id=node.section_id,
                section_heading=node.heading,
                parent_heading=parent,
                original_text=original,
                contextual_text=_contextual_text(headings, original, overlap),
                start_block_id=start,
                end_block_id=end,
                pages=pages,
                oversized_atomic=atomic and len(original) > config.max_size,
            )
        )
        sequence += 1
        local += 1
        previous_original = original
        buffer = []

    for piece in pieces:
        if piece.atomic:
            flush()
            buffer = [piece]
            flush()
            continue
        if not buffer:
            buffer = [piece]
            if len(piece.text) >= config.target_size:
                flush()
            continue
        candidate = _join([*buffer, piece])
        if len(candidate) <= config.max_size:
            buffer.append(piece)
            packed = len(candidate)
            if packed >= config.target_size and packed >= config.min_size:
                flush()
            continue
        flush()
        buffer = [piece]
        if len(piece.text) >= config.target_size:
            flush()
    flush()
    return sequence


def _pieces_from_unit(unit: BodyUnit, max_size: int) -> list[_Piece]:
    text, spans = _unit_text_and_spans(unit)
    if not text:
        return []
    if unit.kind in _ATOMIC:
        return [_Piece(text=text, blocks=[span.block for span in spans], atomic=True)]
    pieces: list[_Piece] = []
    for start, end in _split_ranges(text, max_size):
        fragment = text[start:end].strip()
        if not fragment:
            continue
        pieces.append(
            _Piece(text=fragment, blocks=_blocks_covering(spans, start, end), atomic=False)
        )
    return pieces


def _split_ranges(text: str, max_size: int) -> list[tuple[int, int]]:
    if len(text) <= max_size:
        return [(0, len(text))]
    sentences = [part.strip() for part in _SENTENCE.split(text) if part.strip()]
    if len(sentences) <= 1:
        return _wrap_ranges(text, max_size)
    ranges: list[tuple[int, int]] = []
    current: list[tuple[int, int]] = []
    cursor = 0
    for sentence in sentences:
        found = text.find(sentence, cursor)
        if found < 0:
            found = cursor
        span = (found, found + len(sentence))
        cursor = span[1]
        candidate_len = (span[1] - current[0][0]) if current else len(sentence)
        if current and candidate_len > max_size:
            ranges.extend(_wrap_ranges(text[current[0][0] : current[-1][1]], max_size, current[0][0]))
            current = [span]
        else:
            current.append(span)
    if current:
        ranges.extend(_wrap_ranges(text[current[0][0] : current[-1][1]], max_size, current[0][0]))
    return ranges


def _wrap_ranges(text: str, max_size: int, offset: int = 0) -> list[tuple[int, int]]:
    if len(text) <= max_size:
        return [(offset, offset + len(text))] if text else []
    ranges: list[tuple[int, int]] = []
    index = 0
    length = len(text)
    while index < length:
        if length - index <= max_size:
            ranges.append((offset + index, offset + length))
            break
        window_end = index + max_size
        cut = text.rfind(" ", index, window_end + 1)
        if cut <= index + max_size // 2:
            cut = window_end
        ranges.append((offset + index, offset + cut))
        index = cut
        while index < length and text[index] == " ":
            index += 1
    return ranges


def _unit_text_and_spans(unit: BodyUnit) -> tuple[str, list[_Span]]:
    parts: list[str] = []
    spans: list[_Span] = []
    cursor = 0
    for block in unit.blocks:
        text = re.sub(r"\s+", " ", block.text).strip()
        if not text:
            continue
        if parts:
            cursor += 1
        start = cursor
        cursor += len(text)
        spans.append(_Span(start=start, end=cursor, block=block))
        parts.append(text)
    return " ".join(parts), spans


def _blocks_covering(spans: list[_Span], start: int, end: int) -> list[AnnotatedBlock]:
    found = [span.block for span in spans if span.end > start and span.start < end]
    if found:
        return found
    return [spans[0].block] if spans else []


def _join(pieces: list[_Piece]) -> str:
    return "\n\n".join(piece.text for piece in pieces)


def _overlap_text(previous: str, overlap: int) -> str:
    if overlap <= 0 or not previous:
        return ""
    if len(previous) <= overlap:
        return previous
    return previous[-overlap:]


def _contextual_text(headings: list[str], original: str, overlap: str) -> str:
    lines: list[str] = []
    for index, heading in enumerate(headings):
        label = "Section" if index == 0 else "Subsection"
        lines.append(f"{label}: {heading}")
    body = original if not overlap else f"{overlap}\n\n{original}"
    return "\n".join(lines) + "\n\n" + body
