from __future__ import annotations

import re

from document_metadata_store.config import LlmConfig, PreprocessingConfig
from document_metadata_store.models import (
    AnnotatedBlock,
    AnnotatedPage,
    Block,
    ExcludedSection,
    NormalizedDocument,
    PreprocessedDocument,
)
from document_metadata_store.preprocess.aliases import (
    is_retained_heading,
    match_alias,
    normalize_heading,
)
from document_metadata_store.preprocess.llm import classify_headings_with_llm
from document_metadata_store.preprocess.rules import (
    is_heading_like,
    is_roman_folio,
    is_toc_leader,
    running_header_texts,
)


def preprocess_document(
    document: NormalizedDocument,
    config: PreprocessingConfig,
    llm: LlmConfig | None = None,
) -> PreprocessedDocument:
    blocks = document.iter_blocks()
    annotations = [AnnotatedBlock(block=block, disposition="keep") for block in blocks]
    excluded_sections: list[ExcludedSection] = []
    llm = llm or LlmConfig()

    if not config.enabled or not blocks:
        return _assemble(document, annotations, excluded_sections)

    headers = running_header_texts(blocks)
    toc_pages = _toc_pages(blocks, config)
    heading_indexes = _heading_indexes(blocks, config, headers, toc_pages)
    classified: dict[int, tuple[str, str]] = {}
    pending: list[int] = []
    for index in heading_indexes:
        alias = match_alias(blocks[index].text, config.exclude_sections, config.aliases)
        if alias:
            classified[index] = (alias, f"alias:{alias}")
        elif is_retained_heading(blocks[index].text, config.exclude_sections):
            continue
        else:
            pending.append(index)

    llm_map = classify_headings_with_llm(
        [blocks[index].text.strip() for index in pending],
        config.exclude_sections,
        llm,
    )
    for index in pending:
        label = llm_map.get(blocks[index].text.strip())
        if label:
            classified[index] = (label, f"llm:{label}")

    cover_end_page = min(toc_pages) if toc_pages else None

    if "cover" in config.exclude_sections and cover_end_page is not None:
        cover_indexes = [
            index
            for index, block in enumerate(blocks)
            if block.location.page < cover_end_page
        ]
        if cover_indexes:
            title = document.metadata.title or _first_page_text(blocks) or "cover"
            start = blocks[cover_indexes[0]]
            excluded_sections.append(
                ExcludedSection(
                    section_type="cover",
                    title=title,
                    start_block_id=start.block_id,
                    page=start.location.page,
                )
            )
            for index in cover_indexes:
                annotations[index] = AnnotatedBlock(
                    block=blocks[index],
                    disposition="exclude",
                    section_type="cover",
                    classifier="rule:cover_until_contents",
                )

    if toc_pages and "table_of_contents" in config.exclude_sections:
        toc_indexes = [
            index
            for index, block in enumerate(blocks)
            if block.location.page in toc_pages
            and annotations[index].section_type != "cover"
        ]
        if toc_indexes:
            start = next(
                (
                    blocks[index]
                    for index in toc_indexes
                    if match_alias(
                        blocks[index].text, ("table_of_contents",), config.aliases
                    )
                ),
                blocks[toc_indexes[0]],
            )
            excluded_sections.append(
                ExcludedSection(
                    section_type="table_of_contents",
                    title=_one_line(start.text) if start else "Contents",
                    start_block_id=start.block_id,
                    page=start.location.page,
                )
            )
            for index in toc_indexes:
                annotations[index] = AnnotatedBlock(
                    block=blocks[index],
                    disposition="exclude",
                    section_type="table_of_contents",
                    classifier="rule:toc_pages",
                )

    for position, start_index in enumerate(heading_indexes):
        if start_index not in classified:
            continue
        section_type, classifier = classified[start_index]
        if section_type not in config.exclude_sections:
            continue
        if section_type in {"cover", "table_of_contents"}:
            continue
        if annotations[start_index].section_type in {"cover", "table_of_contents"}:
            continue
        previous = heading_indexes[position - 1] if position else None
        if (
            previous is not None
            and previous in classified
            and classified[previous][0] == section_type
        ):
            continue
        end_index = _span_end(heading_indexes, position, classified, section_type, len(blocks))
        start_block = blocks[start_index]
        excluded_sections.append(
            ExcludedSection(
                section_type=section_type,
                title=_one_line(start_block.text),
                start_block_id=start_block.block_id,
                page=start_block.location.page,
            )
        )
        for index in range(start_index, end_index):
            if annotations[index].section_type in {"cover", "table_of_contents"}:
                continue
            annotations[index] = AnnotatedBlock(
                block=blocks[index],
                disposition="exclude",
                section_type=section_type,
                classifier=classifier,
            )

    seen_running: set[str] = set()
    for index, block in enumerate(blocks):
        if annotations[index].disposition == "exclude":
            continue
        if config.tables_preserve and block.kind == "table":
            continue
        text = block.text.strip()
        if is_roman_folio(text):
            annotations[index] = AnnotatedBlock(
                block=block,
                disposition="exclude",
                classifier="rule:roman_folio",
            )
        elif is_toc_leader(text):
            annotations[index] = AnnotatedBlock(
                block=block,
                disposition="exclude",
                classifier="rule:toc_leaders",
            )
        elif normalize_heading(text) in headers:
            normalized = normalize_heading(text)
            if normalized not in seen_running:
                seen_running.add(normalized)
                continue
            annotations[index] = AnnotatedBlock(
                block=block,
                disposition="exclude",
                classifier="rule:running_header",
            )

    return _assemble(document, annotations, excluded_sections)


def _heading_indexes(
    blocks: list[Block],
    config: PreprocessingConfig,
    headers: set[str],
    toc_pages: set[int],
) -> list[int]:
    indexes: list[int] = []
    seen_header: set[str] = set()
    for index, block in enumerate(blocks):
        if block.location.page in toc_pages:
            if not match_alias(block.text, ("table_of_contents",), config.aliases):
                continue
        if not is_heading_like(
            block,
            exclude_sections=config.exclude_sections,
            aliases=config.aliases,
        ):
            continue
        normalized = normalize_heading(block.text)
        if normalized in headers:
            if normalized in seen_header:
                continue
            seen_header.add(normalized)
        indexes.append(index)
    return indexes


def _span_end(
    heading_indexes: list[int],
    position: int,
    classified: dict[int, tuple[str, str]],
    section_type: str,
    n_blocks: int,
) -> int:
    for later in heading_indexes[position + 1 :]:
        if later not in classified:
            return later
        if classified[later][0] != section_type:
            return later
    return n_blocks


def _toc_pages(blocks: list[Block], config: PreprocessingConfig) -> set[int]:
    start_page: int | None = None
    for block in blocks:
        if is_toc_leader(block.text) or is_roman_folio(block.text.strip()):
            continue
        if match_alias(block.text, ("table_of_contents",), config.aliases):
            start_page = block.location.page
            break
    if start_page is None:
        return set()
    leader_pages = {block.location.page for block in blocks if is_toc_leader(block.text)}
    pages = {start_page}
    page = start_page + 1
    max_page = max(block.location.page for block in blocks)
    while page <= max_page and page in leader_pages:
        pages.add(page)
        page += 1
    return pages


def _first_page_text(blocks: list[Block]) -> str | None:
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
    return re.sub(r"\s+", " ", text).strip()[:120]


def _assemble(
    document: NormalizedDocument,
    annotations: list[AnnotatedBlock],
    excluded_sections: list[ExcludedSection],
) -> PreprocessedDocument:
    by_page: dict[int, list[AnnotatedBlock]] = {}
    for item in annotations:
        by_page.setdefault(item.location.page, []).append(item)
    pages = [
        AnnotatedPage(
            page_number=page.page_number,
            blocks=by_page.get(page.page_number, []),
        )
        for page in document.pages
    ]
    unique: list[ExcludedSection] = []
    seen: set[tuple[str, str]] = set()
    for section in excluded_sections:
        key = (section.section_type, section.start_block_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(section)
    return PreprocessedDocument(
        metadata=document.metadata,
        source=document.source,
        pages=pages,
        excluded_sections=unique,
    )
