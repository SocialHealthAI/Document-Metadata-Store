from __future__ import annotations

import json
import re

from document_metadata_store.config import LlmConfig

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def classify_structure_headings_with_llm(
    headings: list[str],
    llm: LlmConfig,
) -> dict[str, int]:
    """Map leftover line → outline level. Empty if LLM unavailable or fails."""
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
        "For each line, say whether it is a document section heading.\n"
        "Return only a JSON object mapping the exact line to an integer outline "
        "level 1-4, or the string none if it is body text.\n"
        "Prefer none when unsure. Do not invent subsections.\n\n"
        "Lines:\n" + "\n".join(f"- {item}" for item in headings)
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
    return _parse_levels(raw, headings)


def _parse_levels(raw: str, headings: list[str]) -> dict[str, int]:
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
    known = set(headings)
    result: dict[str, int] = {}
    for key, value in data.items():
        heading = str(key)
        if heading not in known:
            continue
        label = str(value).strip().lower()
        if label in {"none", "null", "", "body"}:
            continue
        try:
            level = int(label)
        except ValueError:
            continue
        if 1 <= level <= 4:
            result[heading] = level
    return result
