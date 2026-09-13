from __future__ import annotations

import re

from document_metadata_store.models import AnnotatedBlock
from document_metadata_store.preprocess.aliases import RETAINED_CITATION, is_retained_heading, normalize_heading
from document_metadata_store.preprocess.rules import is_roman_folio, is_toc_leader

_NUMBERED = re.compile(
    r"^(?P<num>\d{1,2}(?:\.\d+){1,4})\.?\s+(?P<title>\S.{0,120})$"
)
_SINGLE_NUMBER = re.compile(
    r"^(?P<num>\d{1,2})\.?\s+(?P<title>\S.{0,80})$"
)
_YEAR = re.compile(r"^(19|20)\d{2}$")
_MONTH = re.compile(
    r"^(january|february|march|april|may|june|july|august|september|"
    r"october|november|december)\b",
    re.I,
)
_NAMED = re.compile(
    r"^(?P<label>part|chapter|recommendation|annex|appendix)\s+"
    r"(?P<num>\d+[a-z]?(?:\.\d+)*)"
    r"(?P<rest>.*)$",
    re.I,
)
_RUNNING_PART_CHAPTER = re.compile(
    r"^part\s+\d+\s*:\s*chapter\s+\d+\s*$",
    re.I,
)
_PAREN_CROSSREF = re.compile(
    r"^\(?\s*part\s+\d+\s*,\s*chapters?\s+",
    re.I,
)
_FONT_JUNK = re.compile(r"\.ss0\d|/m\.|/i\.|/n\.|/u\.")
_CITATION_HINT = re.compile(
    r"\b(accessed|doi\.org|https?://|et al|license:|isbn)\b",
    re.I,
)
_NAV_COUNT = re.compile(r"\(\d+\)\s*$")


def compact_stylized_label(text: str) -> str:
    """Join letter-spaced PDF labels ('Cha PTeR 1:' → 'ChaPTeR 1:')."""
    collapsed = re.sub(r"\s+", " ", text).strip()
    match = re.match(
        r"^(?P<label>(?:[A-Za-z]{1,12}\s+){1,8}[A-Za-z]{1,12})(?P<rest>\s+\d.*)$",
        collapsed,
    )
    if not match:
        return collapsed
    label = match.group("label").replace(" ", "")
    if not re.match(r"^(part|chapter|recommendation|annex|appendix)$", label, re.I):
        return collapsed
    return f"{label}{match.group('rest')}"


def cheap_heading_level(block: AnnotatedBlock, exclude_sections: tuple[str, ...]) -> int | None:
    """Strong outline cue: named title, dotted number, or retained heading."""
    text = compact_stylized_label(block.text)
    if not _eligible_text(text):
        return None
    named = _named_level(text)
    if named is not None:
        return named
    if _NAMED.match(text):
        return None
    numbered = _dotted_level(text)
    if numbered is not None:
        return numbered
    if is_retained_heading(text, exclude_sections):
        if text.endswith((".", "?", "!")) and len(text.split()) <= 2:
            return None
        if _NAMED.match(text):
            return None
        return 1
    return None


def weak_numbered_level(block: AnnotatedBlock) -> int | None:
    """Short '1. Title' line. Only used after a document already has a strong outline."""
    text = compact_stylized_label(block.text)
    if not _eligible_text(text):
        return None
    match = _SINGLE_NUMBER.match(text)
    if not match:
        return None
    num = match.group("num")
    title = match.group("title")
    if _YEAR.match(num) or _MONTH.match(title):
        return None
    if not _numbered_title_ok(title, dotted=False):
        return None
    return 2


def is_leftover_heading_candidate(block: AnnotatedBlock, exclude_sections: tuple[str, ...]) -> bool:
    """Short title-like line that cheap rules did not confirm."""
    if cheap_heading_level(block, exclude_sections) is not None:
        return False
    if weak_numbered_level(block) is not None:
        return False
    text = compact_stylized_label(block.text)
    if not _eligible_text(text):
        return False
    if text.endswith((".", "?", "!")):
        return False
    words = text.split()
    if len(text) > 60 or not (2 <= len(words) <= 6):
        return False
    if "," in text or _CITATION_HINT.search(text) or _NAV_COUNT.search(text):
        return False
    if any(ch.isdigit() for ch in text):
        return False
    if not text[:1].isupper():
        return False
    return True


def is_citation_section(text: str) -> bool:
    key = normalize_heading(text)
    return any(key == name or key.startswith(name + " ") for name in RETAINED_CITATION)


def _eligible_text(text: str) -> bool:
    if not text or is_roman_folio(text) or is_toc_leader(text):
        return False
    if re.fullmatch(r"\d+", text):
        return False
    if _FONT_JUNK.search(text) or text.count("/") >= 3:
        return False
    if _RUNNING_PART_CHAPTER.match(text) or _PAREN_CROSSREF.match(text):
        return False
    if _CITATION_HINT.search(text):
        return False
    return True


def _named_level(text: str) -> int | None:
    match = _NAMED.match(text)
    if not match:
        return None
    rest = match.group("rest").strip().lstrip(":").strip()
    label = match.group("label").lower()
    number = match.group("num")
    if label == "chapter" and "." in number:
        return None
    if not rest:
        if label == "part":
            return None
        return {"chapter": 2, "recommendation": 3, "annex": 1, "appendix": 1}[label]
    if re.search(r"\bparts?\s+\d|\bchapters?\s+\d", rest, re.I):
        return None
    if rest[:1].islower():
        return None
    if rest.endswith((".", "?", "!")) and len(rest.split()) > 6:
        return None
    if label == "part":
        return 1
    if label == "chapter":
        return 2
    if label == "recommendation":
        return 3
    return 1


def _dotted_level(text: str) -> int | None:
    match = _NUMBERED.match(text)
    if not match:
        return None
    num = match.group("num")
    title = match.group("title")
    if _YEAR.match(num.split(".")[0]):
        return None
    if not _numbered_title_ok(title, dotted=True):
        return None
    return min(1 + len(num.split(".")), 5)


def heading_collapse_key(text: str) -> str:
    """Identity for repeated chapter/annex crumbs vs distinct numbered titles."""
    compacted = compact_stylized_label(text)
    match = _NAMED.match(compacted)
    if match:
        return f"{match.group('label').lower()} {match.group('num')}"
    return normalize_heading(text)


def _numbered_title_ok(title: str, *, dotted: bool) -> bool:
    if not title[:1].isalpha() or title[:1].islower():
        return False
    if title.endswith((".", "?", "!")):
        return False
    if "." in title:
        return False
    words = title.split()
    if dotted:
        return 1 <= len(words) <= 14
    return 1 <= len(words) <= 5
