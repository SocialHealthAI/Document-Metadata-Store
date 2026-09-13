from __future__ import annotations

import json
import re

from document_metadata_store.config import LlmConfig

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def classify_headings_with_llm(
    headings: list[str],
    exclude_sections: tuple[str, ...],
    llm: LlmConfig,
) -> dict[str, str]:
    """Map heading text -> exclude section type. Empty if LLM unavailable or fails."""
    if not headings or not llm.enabled():
        return {}
    provider = (llm.provider or "").lower()
    if provider != "anthropic":
        return {}
    try:
        import anthropic
    except ImportError:
        return {}

    prompt = (
        "Classify each heading as one of these functional section types, or none.\n"
        f"Allowed types: {', '.join(exclude_sections)}\n"
        "Return only JSON object mapping the exact heading string to a type or the string none.\n\n"
        "Headings:\n"
        + "\n".join(f"- {item}" for item in headings)
    )
    try:
        client = anthropic.Anthropic(api_key=llm.api_key)
        response = client.messages.create(
            model=llm.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else ""
    except Exception:
        return {}
    return _parse_mapping(raw, headings, exclude_sections)


def _parse_mapping(
    raw: str,
    headings: list[str],
    exclude_sections: tuple[str, ...],
) -> dict[str, str]:
    text = raw.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    allowed = set(exclude_sections)
    result: dict[str, str] = {}
    known = set(headings)
    for key, value in data.items():
        heading = str(key)
        label = str(value).strip().lower().replace(" ", "_")
        if heading not in known:
            continue
        if label in {"none", "null", ""}:
            continue
        if label in allowed:
            result[heading] = label
    return result
