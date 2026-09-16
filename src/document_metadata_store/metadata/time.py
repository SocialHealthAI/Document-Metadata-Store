from __future__ import annotations

import re

from document_metadata_store.models import ChunkMetadata, MetadataValue

TIME_FIELD = "time_period"
MAX_SPAN_YEARS = 25

_SINGLE = re.compile(r"^(?:FY\s*)?((?:1[89]|20)\d{2})$", re.IGNORECASE)
_RANGE = re.compile(
    r"^(?:FY\s*)?((?:1[89]|20)\d{2})\s*(?:[-–—]|to|through|/)\s*(?:FY\s*)?((?:1[89]|20)\d{2})$",
    re.IGNORECASE,
)


def expand_time_values(values: tuple[MetadataValue, ...]) -> tuple[MetadataValue, ...]:
    """Turn range strings into calendar years so a filter of 2020 matches 2019-2022."""
    seen: dict[str, MetadataValue] = {}
    for item in values:
        for year in years_from_text(item.value):
            if year not in seen:
                seen[year] = MetadataValue(
                    value=year, origin=item.origin, confidence=item.confidence
                )
    return tuple(seen[year] for year in sorted(seen, key=int))


def normalize_time_field(meta: ChunkMetadata) -> ChunkMetadata:
    if TIME_FIELD not in meta.fields:
        return meta
    fields = dict(meta.fields)
    fields[TIME_FIELD] = expand_time_values(fields[TIME_FIELD])
    return ChunkMetadata(fields=fields)


def years_from_text(text: str) -> tuple[str, ...]:
    raw = (text or "").strip()
    if not raw:
        return ()
    span = _RANGE.fullmatch(raw)
    if span:
        start = int(span.group(1))
        end = int(span.group(2))
        if start > end:
            start, end = end, start
        if end - start + 1 > MAX_SPAN_YEARS:
            return ()
        return tuple(str(year) for year in range(start, end + 1))
    lone = _SINGLE.fullmatch(raw)
    if lone:
        return (lone.group(1),)
    return ()
