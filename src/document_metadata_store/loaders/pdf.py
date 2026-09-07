from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import median

from pypdf import PdfReader
from pypdf.generic import ByteStringObject, TextStringObject

from document_metadata_store.models import (
    Block,
    DocumentMetadata,
    Location,
    NormalizedDocument,
    Page,
    StyleHints,
)

_HEADING_SIZE_RATIO = 1.35
_HEADING_BOLD_SIZE_RATIO = 1.10
_HEADING_MAX_CHARS = 120
_LINE_Y_TOLERANCE_RATIO = 0.35


class PdfLoadError(Exception):
    """Raised when a PDF cannot be opened or parsed."""


@dataclass
class _Fragment:
    text: str
    x: float
    y: float
    font_size: float
    bold: bool


def document_id_for(path: Path) -> str:
    resolved = str(path.resolve())
    return hashlib.sha256(resolved.encode("utf-8")).hexdigest()


def load_pdf(path: Path, *, display_source: str | None = None) -> NormalizedDocument:
    source_path = path.resolve()
    try:
        reader = PdfReader(str(source_path), strict=False)
    except Exception as exc:  # noqa: BLE001 — surface any pypdf/OS failure
        raise PdfLoadError(f"unable to open PDF: {exc}") from exc

    if getattr(reader, "is_encrypted", False):
        try:
            if reader.decrypt("") == 0:
                raise PdfLoadError("encrypted PDF (password required)")
        except PdfLoadError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise PdfLoadError(f"encrypted PDF: {exc}") from exc

    pages = [_extract_page(page, page_number=index + 1) for index, page in enumerate(reader.pages)]
    source = display_source if display_source is not None else str(source_path)
    metadata = _document_metadata(reader, source_path, source)
    return NormalizedDocument(metadata=metadata, source=str(source_path), pages=pages)


def is_image_only(document: NormalizedDocument) -> bool:
    if not document.pages:
        return True
    return document.text_chars() == 0


def _extract_page(page, *, page_number: int) -> Page:
    fragments: list[_Fragment] = []

    def visitor_text(text, _cm, tm, font_dict, font_size) -> None:
        if not text or not str(text).strip():
            return
        try:
            x = float(tm[4])
            y = float(tm[5])
        except (TypeError, IndexError, ValueError):
            x, y = 0.0, 0.0
        try:
            size = float(font_size) if font_size else 0.0
        except (TypeError, ValueError):
            size = 0.0
        fragments.append(
            _Fragment(
                text=str(text),
                x=x,
                y=y,
                font_size=size,
                bold=_is_bold(font_dict),
            )
        )

    try:
        page.extract_text(visitor_text=visitor_text)
    except Exception:
        fallback = page.extract_text() or ""
        if fallback.strip():
            fragments.append(
                _Fragment(text=fallback, x=0.0, y=0.0, font_size=0.0, bold=False)
            )

    lines = _fragments_to_lines(fragments)
    sizes = [line.font_size for line in lines if line.font_size > 0]
    typical = median(sizes) if sizes else 0.0
    blocks = [
        _line_to_block(line, page_number=page_number, index=index, typical_size=typical)
        for index, line in enumerate(lines)
    ]
    return Page(page_number=page_number, blocks=blocks)


@dataclass
class _Line:
    text: str
    x: float
    y: float
    font_size: float
    bold: bool
    x1: float


def _fragments_to_lines(fragments: list[_Fragment]) -> list[_Line]:
    if not fragments:
        return []

    ordered = sorted(fragments, key=lambda item: (-round(item.y, 1), item.x))
    lines: list[list[_Fragment]] = []
    current: list[_Fragment] = [ordered[0]]

    for fragment in ordered[1:]:
        ref = current[0]
        tolerance = max(ref.font_size, fragment.font_size, 8.0) * _LINE_Y_TOLERANCE_RATIO
        if abs(fragment.y - ref.y) <= tolerance:
            current.append(fragment)
        else:
            lines.append(current)
            current = [fragment]
    lines.append(current)

    result: list[_Line] = []
    for group in lines:
        group.sort(key=lambda item: item.x)
        text = _join_fragments(group)
        if not text.strip():
            continue
        sizes = [item.font_size for item in group if item.font_size > 0]
        result.append(
            _Line(
                text=text,
                x=group[0].x,
                y=group[0].y,
                font_size=median(sizes) if sizes else 0.0,
                bold=all(item.bold for item in group) if group else False,
                x1=group[-1].x,
            )
        )
    return result


def _join_fragments(group: list[_Fragment]) -> str:
    parts: list[str] = []
    for item in group:
        piece = item.text
        if not parts:
            parts.append(piece)
            continue
        if parts[-1].endswith(" ") or piece.startswith(" ") or piece.startswith("\n"):
            parts.append(piece)
        else:
            parts.append(" " + piece)
    return re.sub(r"[ \t]+", " ", "".join(parts)).strip()


def _line_to_block(line: _Line, *, page_number: int, index: int, typical_size: float) -> Block:
    kind = "text"
    if _is_heading_candidate(line, typical_size=typical_size):
        kind = "heading_candidate"
    height = line.font_size if line.font_size > 0 else 10.0
    bbox = (line.x, line.y, max(line.x1, line.x), line.y + height)
    hints = StyleHints(
        font_size=line.font_size or None,
        bold=line.bold,
        indent=line.x if line.x else None,
    )
    return Block(
        block_id=f"p{page_number}-b{index + 1}",
        kind=kind,
        text=line.text,
        location=Location(page=page_number, bbox=bbox),
        style_hints=hints,
    )


def _is_heading_candidate(line: _Line, *, typical_size: float) -> bool:
    if not line.text or typical_size <= 0 or line.font_size <= 0:
        return False
    if len(line.text) > _HEADING_MAX_CHARS:
        return False
    if line.font_size >= typical_size * _HEADING_SIZE_RATIO:
        return True
    if line.bold and line.font_size >= typical_size * _HEADING_BOLD_SIZE_RATIO:
        return True
    return False


def _is_bold(font_dict) -> bool:
    name = _font_name(font_dict).lower()
    return "bold" in name or "black" in name or "heavy" in name


def _font_name(font_dict) -> str:
    if not font_dict:
        return ""
    try:
        base = font_dict.get("/BaseFont") or font_dict.get("BaseFont")
    except Exception:
        return ""
    return str(base) if base is not None else ""


def _document_metadata(reader: PdfReader, source_path: Path, display_source: str) -> DocumentMetadata:
    info = reader.metadata
    title = _clean_meta(getattr(info, "title", None) if info else None)
    author = _clean_meta(getattr(info, "author", None) if info else None)
    publication_date = _clean_meta(getattr(info, "creation_date", None) if info else None)
    if publication_date is None and info is not None:
        publication_date = _pdf_date(info.get("/CreationDate"))

    language = None
    try:
        raw_lang = reader.trailer.get("/Root", {}).get("/Lang")
        language = _clean_meta(raw_lang)
    except Exception:
        language = None

    return DocumentMetadata(
        id=document_id_for(source_path),
        title=title,
        author=author,
        organization=None,
        publication_date=_stringify_date(publication_date),
        source=display_source,
        source_url=None,
        document_type="pdf",
        language=language,
        version=None,
    )


def _clean_meta(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (TextStringObject, ByteStringObject)):
        value = str(value)
    text = str(value).strip()
    return text or None


def _pdf_date(value) -> str | None:
    cleaned = _clean_meta(value)
    if not cleaned:
        return None
    return cleaned


def _stringify_date(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return _clean_meta(value)
