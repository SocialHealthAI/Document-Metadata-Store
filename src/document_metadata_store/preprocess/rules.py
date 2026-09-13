from __future__ import annotations

import re
from collections import Counter

from document_metadata_store.models import Block
from document_metadata_store.preprocess.aliases import (
    is_retained_heading,
    match_alias,
    normalize_heading,
)

_ROMAN = re.compile(r"^[ivxlcdm]+\.?$", re.IGNORECASE)
_LEADER_DOTS = re.compile(r"\.{6,}|…{2,}")


def is_heading_like(
    block: Block,
    *,
    exclude_sections: tuple[str, ...],
    aliases: dict[str, tuple[str, ...]],
) -> bool:
    """Conservative span boundaries: style, aliases, or retained section titles.

    Wrapped title-case body lines are not headings. Prefer missing an exclude
    heading over treating chapter body as a heading.
    """
    text = re.sub(r"\s+", " ", block.text).strip()
    if not text:
        return False
    if is_roman_folio(text) or is_toc_leader(text):
        return False
    if block.kind == "heading_candidate":
        return True
    if match_alias(text, exclude_sections, aliases):
        return True
    if is_retained_heading(text, exclude_sections):
        return True
    return False


def is_roman_folio(text: str) -> bool:
    collapsed = text.strip()
    return bool(collapsed) and len(collapsed) <= 8 and bool(_ROMAN.match(collapsed))


def is_toc_leader(text: str) -> bool:
    return bool(_LEADER_DOTS.search(text))


def running_header_texts(blocks: list[Block], *, min_pages: int = 3) -> set[str]:
    first_on_page: dict[int, str] = {}
    for block in blocks:
        page = block.location.page
        if page in first_on_page:
            continue
        normalized = normalize_heading(block.text)
        if not normalized or is_roman_folio(block.text.strip()):
            continue
        if len(normalized.split()) > 12:
            continue
        first_on_page[page] = normalized
    counts = Counter(first_on_page.values())
    return {text for text, count in counts.items() if count >= min_pages}
