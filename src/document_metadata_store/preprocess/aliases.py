from __future__ import annotations

import re
from collections.abc import Mapping

_PUNCT = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE = re.compile(r"\s+")

# Prefix match is safe for these; one-word labels must be exact (see below).
RETAINED_PREFIXES = (
    "executive summary",
    "annex",
    "appendix",
)
RETAINED_EXACT = (
    "introduction",
    "methods",
    "findings",
    "results",
    "conclusions",
    "recommendations",
)
RETAINED_CITATION = (
    "references",
    "bibliography",
    "works cited",
    "sources and notes",
)
# Standalone words that are also common in prose or body titles.
_EXACT_ALIAS_KEYS = {
    "index",
    "toc",
    "tables",
    "figures",
    "notes",
    "sources",
    "forward",
}


def normalize_heading(text: str) -> str:
    collapsed = _SPACE.sub(" ", _PUNCT.sub(" ", text.lower())).strip()
    return collapsed


def match_alias(
    text: str,
    exclude_sections: tuple[str, ...],
    aliases: Mapping[str, tuple[str, ...]],
) -> str | None:
    normalized = normalize_heading(text)
    if not normalized:
        return None
    for section in exclude_sections:
        phrases = aliases.get(section, (section.replace("_", " "),))
        for phrase in phrases:
            key = normalize_heading(phrase)
            if not key:
                continue
            if normalized == key:
                return section
            if not normalized.startswith(key + " "):
                continue
            if " " not in key and key in _EXACT_ALIAS_KEYS:
                continue
            return section
    return None


def is_retained_heading(text: str, exclude_sections: tuple[str, ...]) -> bool:
    normalized = normalize_heading(text)
    if not normalized:
        return False
    if not _is_excluded("chapter", exclude_sections) and re.match(
        r"^(chapter|recommendation)\s+\d", normalized
    ):
        return True
    if not _is_excluded("part", exclude_sections) and re.match(r"^part\s+\d", normalized):
        return True
    for name in RETAINED_PREFIXES:
        if _is_excluded(name, exclude_sections):
            continue
        if normalized == name or normalized.startswith(name + " "):
            return True
    for name in RETAINED_EXACT:
        if _is_excluded(name, exclude_sections):
            continue
        if normalized == name:
            return True
    if not _is_excluded("references", exclude_sections):
        for name in RETAINED_CITATION:
            if normalized == name or normalized.startswith(name + " "):
                return True
    return False


def _is_excluded(name: str, exclude_sections: tuple[str, ...]) -> bool:
    slug = name.replace(" ", "_")
    return slug in exclude_sections or name in exclude_sections
