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


Disposition = Literal["keep", "exclude"]


@dataclass(frozen=True)
class AnnotatedBlock:
    block: Block
    disposition: Disposition = "keep"
    section_type: str | None = None
    classifier: str | None = None

    @property
    def block_id(self) -> str:
        return self.block.block_id

    @property
    def kind(self) -> BlockKind:
        return self.block.kind

    @property
    def text(self) -> str:
        return self.block.text

    @property
    def location(self) -> Location:
        return self.block.location

    @property
    def style_hints(self) -> StyleHints | None:
        return self.block.style_hints


@dataclass(frozen=True)
class AnnotatedPage:
    page_number: int
    blocks: list[AnnotatedBlock] = field(default_factory=list)


@dataclass(frozen=True)
class ExcludedSection:
    section_type: str
    title: str
    start_block_id: str
    page: int


@dataclass(frozen=True)
class PreprocessedDocument:
    metadata: DocumentMetadata
    source: str
    pages: list[AnnotatedPage] = field(default_factory=list)
    excluded_sections: list[ExcludedSection] = field(default_factory=list)

    def iter_blocks(self) -> list[AnnotatedBlock]:
        return [block for page in self.pages for block in page.blocks]

    def kept_count(self) -> int:
        return sum(1 for block in self.iter_blocks() if block.disposition == "keep")

    def excluded_count(self) -> int:
        return sum(1 for block in self.iter_blocks() if block.disposition == "exclude")

    def classifier_counts(self) -> dict[str, int]:
        by_rule = by_alias = by_llm = 0
        for block in self.iter_blocks():
            if block.disposition != "exclude" or not block.classifier:
                continue
            if block.classifier.startswith("rule:"):
                by_rule += 1
            elif block.classifier.startswith("alias:"):
                by_alias += 1
            elif block.classifier.startswith("llm:"):
                by_llm += 1
        return {"by_rule": by_rule, "by_alias": by_alias, "by_llm": by_llm}


BodyKind = Literal["paragraph", "table", "list_item", "caption", "text"]


@dataclass(frozen=True)
class BodyUnit:
    kind: BodyKind
    blocks: list[AnnotatedBlock] = field(default_factory=list)


@dataclass
class SectionNode:
    section_id: str
    heading: str
    level: int
    start_block_id: str
    implicit: bool = False
    body: list[BodyUnit] = field(default_factory=list)
    children: list["SectionNode"] = field(default_factory=list)


@dataclass(frozen=True)
class StructuredDocument:
    metadata: DocumentMetadata
    source: str
    sections: list[SectionNode] = field(default_factory=list)
    implicit_title: bool = False

    def iter_sections(self) -> list[SectionNode]:
        nodes: list[SectionNode] = []

        def walk(node: SectionNode) -> None:
            nodes.append(node)
            for child in node.children:
                walk(child)

        for root in self.sections:
            walk(root)
        return nodes

    def section_count(self) -> int:
        return len(self.sections)

    def subsection_count(self) -> int:
        return sum(1 for node in self.iter_sections() if node.level > 1)

    def node_count(self) -> int:
        return len(self.iter_sections())

    def max_depth(self) -> int:
        nodes = self.iter_sections()
        return max((node.level for node in nodes), default=0)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    document_id: str
    section_id: str
    section_heading: str
    parent_heading: str | None
    original_text: str
    contextual_text: str
    start_block_id: str
    end_block_id: str
    pages: tuple[int, ...] = ()
    oversized_atomic: bool = False


@dataclass(frozen=True)
class ChunkedDocument:
    metadata: DocumentMetadata
    source: str
    chunks: list[Chunk] = field(default_factory=list)

    def chunk_count(self) -> int:
        return len(self.chunks)

    def oversized_atomic_count(self) -> int:
        return sum(1 for chunk in self.chunks if chunk.oversized_atomic)

    def max_original_chars(self) -> int:
        return max((len(chunk.original_text) for chunk in self.chunks), default=0)


MetadataOrigin = Literal["explicit", "inherited", "inferred", "unknown"]


@dataclass(frozen=True)
class MetadataValue:
    value: str
    origin: MetadataOrigin = "explicit"
    confidence: float | None = None


@dataclass(frozen=True)
class ChunkMetadata:
    fields: dict[str, tuple[MetadataValue, ...]] = field(default_factory=dict)

    def values_for(self, name: str) -> tuple[MetadataValue, ...]:
        return self.fields.get(name, ())

    def texts_for(self, name: str) -> tuple[str, ...]:
        return tuple(item.value for item in self.values_for(name))

    def has_any(self) -> bool:
        return any(self.fields.values())


@dataclass(frozen=True)
class EnrichedChunk:
    chunk: Chunk
    metadata: ChunkMetadata
    llm_failed: bool = False
    llm_error: str | None = None

    @property
    def chunk_id(self) -> str:
        return self.chunk.chunk_id

    @property
    def section_heading(self) -> str:
        return self.chunk.section_heading


@dataclass(frozen=True)
class EnrichedDocument:
    metadata: DocumentMetadata
    source: str
    chunks: list[EnrichedChunk] = field(default_factory=list)
    skipped: bool = False
    field_names: tuple[str, ...] = ()
    llm_errors: tuple[str, ...] = ()
    llm_retries: int = 0

    def chunk_count(self) -> int:
        return len(self.chunks)

    def with_any_field_count(self) -> int:
        return sum(1 for item in self.chunks if item.metadata.has_any())

    def llm_failed_count(self) -> int:
        return sum(1 for item in self.chunks if item.llm_failed)


@dataclass(frozen=True)
class EmbeddedChunk:
    item: EnrichedChunk
    embedding: tuple[float, ...] = ()
    dim: int = 0
    model: str = ""
    embed_failed: bool = False
    embed_error: str | None = None

    @property
    def chunk(self) -> Chunk:
        return self.item.chunk

    @property
    def chunk_id(self) -> str:
        return self.item.chunk_id

    @property
    def metadata(self) -> ChunkMetadata:
        return self.item.metadata

    @property
    def section_heading(self) -> str:
        return self.item.section_heading


@dataclass(frozen=True)
class EmbeddedDocument:
    metadata: DocumentMetadata
    source: str
    chunks: list[EmbeddedChunk] = field(default_factory=list)
    model: str = ""
    dim: int = 0
    embed_errors: tuple[str, ...] = ()

    def chunk_count(self) -> int:
        return len(self.chunks)

    def embedded_count(self) -> int:
        return sum(1 for item in self.chunks if not item.embed_failed and item.dim > 0)

    def embed_failed_count(self) -> int:
        return sum(1 for item in self.chunks if item.embed_failed)
