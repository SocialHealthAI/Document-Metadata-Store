from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

BlockKind = Literal[
    "text",
    "heading_candidate",
    "paragraph",
    "list_item",
    "table",
    "caption",
]


@dataclass(frozen=True)
class StyleHints:
    font_size: float | None = None
    bold: bool | None = None
    indent: float | None = None


@dataclass(frozen=True)
class Location:
    page: int
    bbox: tuple[float, float, float, float] | None = None


@dataclass(frozen=True)
class Block:
    block_id: str
    kind: BlockKind
    text: str
    location: Location
    style_hints: StyleHints | None = None


@dataclass(frozen=True)
class Page:
    page_number: int
    blocks: list[Block] = field(default_factory=list)


@dataclass(frozen=True)
class DocumentMetadata:
    id: str
    title: str | None = None
    author: str | None = None
    organization: str | None = None
    publication_date: str | None = None
    source: str | None = None
    source_url: str | None = None
    document_type: str | None = None
    language: str | None = None
    version: str | None = None


@dataclass(frozen=True)
class NormalizedDocument:
    metadata: DocumentMetadata
    source: str
    pages: list[Page] = field(default_factory=list)

    def block_count(self) -> int:
        return sum(len(page.blocks) for page in self.pages)

    def text_chars(self) -> int:
        return sum(len(block.text) for page in self.pages for block in page.blocks)

    def iter_blocks(self) -> list[Block]:
        return [block for page in self.pages for block in page.blocks]
