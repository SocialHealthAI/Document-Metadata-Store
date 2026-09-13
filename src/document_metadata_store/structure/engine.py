from __future__ import annotations

import re
from collections import Counter

from document_metadata_store.config import LlmConfig, PreprocessingConfig
from document_metadata_store.models import (
    AnnotatedBlock,
    BodyUnit,
    PreprocessedDocument,
    SectionNode,
    StructuredDocument,
)
from document_metadata_store.preprocess.aliases import normalize_heading
from document_metadata_store.preprocess.rules import running_header_texts
from document_metadata_store.structure.headings import (
    cheap_heading_level,
    compact_stylized_label,
    heading_collapse_key,
    is_citation_section,
    is_leftover_heading_candidate,
    weak_numbered_level,
)
from document_metadata_store.structure.llm import classify_structure_headings_with_llm

_STRUCTURAL_KINDS = {"table", "list_item", "caption"}


def extract_structure(
    document: PreprocessedDocument,
    config: PreprocessingConfig,
    llm: LlmConfig | None = None,
) -> StructuredDocument:
    llm = llm or LlmConfig()
    kept = [block for block in document.iter_blocks() if block.disposition == "keep"]
    if not kept:
        return StructuredDocument(
            metadata=document.metadata,
            source=document.source,
            sections=[],
            implicit_title=False,
        )

    headers = running_header_texts([block.block for block in kept])
    levels: dict[int, int] = {}
    weak: dict[int, int] = {}
    leftovers: list[int] = []
    for index, block in enumerate(kept):
        if normalize_heading(block.text) in headers:
            continue
        cheap = cheap_heading_level(block, config.exclude_sections)
        if cheap is not None:
            levels[index] = cheap
            continue
        numbered = weak_numbered_level(block)
        if numbered is not None:
            weak[index] = numbered
        elif is_leftover_heading_candidate(block, config.exclude_sections):
            leftovers.append(index)

    if not levels:
        return _implicit_document(document, kept)

    in_refs = False
    leftover_ok: list[int] = []
    for index, block in enumerate(kept):
        if index in levels and is_citation_section(block.text):
            in_refs = True
        if in_refs:
            continue
        if index in weak:
            levels[index] = weak[index]
        elif index in leftovers:
            leftover_ok.append(index)

    llm_map = classify_structure_headings_with_llm(
        [kept[index].text.strip() for index in leftover_ok],
        llm,
    )
    for index in leftover_ok:
        level = llm_map.get(kept[index].text.strip())
        if level:
            levels[index] = level

    _drop_repeated_headings(kept, levels)

    if not levels:
        return _implicit_document(document, kept)

    roots = _nest_and_fill(kept, levels, document)
    return StructuredDocument(
        metadata=document.metadata,
        source=document.source,
        sections=roots,
        implicit_title=any(node.implicit for node in roots),
    )


def _drop_repeated_headings(
    kept: list[AnnotatedBlock],
    levels: dict[int, int],
    *,
    min_repeats: int = 2,
) -> None:
    """Keep the first copy of a heading that repeats across many pages."""
    counts = Counter(heading_collapse_key(kept[index].text) for index in levels)
    seen: set[str] = set()
    for index in sorted(levels):
        key = heading_collapse_key(kept[index].text)
        if counts[key] < min_repeats:
            continue
        if key in seen:
            del levels[index]
        else:
            seen.add(key)


def _implicit_document(
    document: PreprocessedDocument,
    kept: list[AnnotatedBlock],
) -> StructuredDocument:
    title = document.metadata.title or _first_page_text(kept) or "untitled"
    start = kept[0]
    node = SectionNode(
        section_id="s1",
        heading=_one_line(title),
        level=1,
        start_block_id=start.block_id,
        implicit=True,
    )
    node.body = _body_units(kept)
    return StructuredDocument(
        metadata=document.metadata,
        source=document.source,
        sections=[node],
        implicit_title=True,
    )


def _nest_and_fill(
    kept: list[AnnotatedBlock],
    levels: dict[int, int],
    document: PreprocessedDocument,
) -> list[SectionNode]:
    roots: list[SectionNode] = []
    stack: list[SectionNode] = []
    current: SectionNode | None = None
    preamble: list[AnnotatedBlock] = []
    body_buf: list[AnnotatedBlock] = []
    next_id = 1

    def flush_body(node: SectionNode | None) -> None:
        if node is None or not body_buf:
            return
        node.body.extend(_body_units(list(body_buf)))
        body_buf.clear()

    def attach(node: SectionNode) -> None:
        nonlocal next_id
        while stack and stack[-1].level >= node.level:
            stack.pop()
        if stack:
            stack[-1].children.append(node)
        else:
            roots.append(node)
        stack.append(node)

    consumed: set[int] = set()

    for index, block in enumerate(kept):
        if index in consumed:
            continue
        if index in levels:
            if preamble and current is None:
                title = document.metadata.title or _first_page_text(preamble) or "untitled"
                lead = SectionNode(
                    section_id=f"s{next_id}",
                    heading=_one_line(title),
                    level=1,
                    start_block_id=preamble[0].block_id,
                    implicit=True,
                    body=_body_units(preamble),
                )
                next_id += 1
                attach(lead)
                preamble = []
            flush_body(current)
            heading, extra = _heading_with_continuation(kept, index, levels)
            consumed.update(extra)
            node = SectionNode(
                section_id=f"s{next_id}",
                heading=heading,
                level=levels[index],
                start_block_id=block.block_id,
            )
            next_id += 1
            attach(node)
            current = node
            continue
        if current is None:
            preamble.append(block)
        else:
            body_buf.append(block)

    flush_body(current)
    return roots


def _body_units(blocks: list[AnnotatedBlock]) -> list[BodyUnit]:
    units: list[BodyUnit] = []
    paragraph: list[AnnotatedBlock] = []

    def flush_paragraph() -> None:
        if paragraph:
            units.append(BodyUnit(kind="paragraph", blocks=list(paragraph)))
            paragraph.clear()

    for block in blocks:
        kind = block.kind if block.kind in _STRUCTURAL_KINDS else "paragraph"
        if kind != "paragraph":
            flush_paragraph()
            units.append(BodyUnit(kind=kind, blocks=[block]))
        else:
            paragraph.append(block)
    flush_paragraph()
    return units


def _heading_with_continuation(
    kept: list[AnnotatedBlock],
    index: int,
    levels: dict[int, int],
) -> tuple[str, set[int]]:
    label = compact_stylized_label(kept[index].text)
    consumed: set[int] = set()
    if not _needs_title_continuation(label):
        return _one_line(label), consumed
    page = kept[index].location.page
    parts: list[str] = []
    for next_index in range(index + 1, min(index + 5, len(kept))):
        if next_index in levels:
            break
        nxt = compact_stylized_label(kept[next_index].text)
        if kept[next_index].location.page != page or not nxt:
            break
        if nxt.endswith((".", "?", "!")) or "," in nxt:
            break
        words = nxt.split()
        if len(words) > 8 or not nxt[:1].isupper():
            break
        parts.append(nxt)
        consumed.add(next_index)
        if sum(len(part.split()) for part in parts) >= 12:
            break
    if parts:
        gap = " " if label.endswith(":") else " "
        label = f"{label}{gap}{' '.join(parts)}"
    return _one_line(label), consumed


def _needs_title_continuation(text: str) -> bool:
    if re.fullmatch(r"\d{1,2}(?:\.\d+){1,4}\.?", text):
        return True
    match = re.match(
        r"^(part|chapter|recommendation|annex|appendix)\s+\d+[a-z]?(?:\.\d+)*\s*:?\s*$",
        text,
        re.I,
    )
    return match is not None


def _first_page_text(blocks: list[AnnotatedBlock]) -> str | None:
    parts: list[str] = []
    for block in blocks:
        if block.location.page != 1:
            if parts:
                break
            continue
        text = _one_line(block.text)
        if text:
            parts.append(text)
        if len(" ".join(parts)) >= 80:
            break
    return " ".join(parts) or None


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:160]
