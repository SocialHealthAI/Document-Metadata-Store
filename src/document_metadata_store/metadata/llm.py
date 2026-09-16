from __future__ import annotations

import json
import re
from dataclasses import dataclass

from document_metadata_store.config import LlmConfig
from document_metadata_store.metadata.schema import MetadataSchema
from document_metadata_store.metadata.time import TIME_FIELD, expand_time_values
from document_metadata_store.models import (
    Chunk,
    ChunkMetadata,
    MetadataOrigin,
    MetadataValue,
)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)
_ORIGINS = {"explicit", "inherited", "inferred", "unknown"}
_MAX_TOKENS = 16384
_ERROR_BODY_CHARS = 180


@dataclass(frozen=True)
class LlmBatchOutcome:
    parsed: dict[str, ChunkMetadata] | None = None
    error: str | None = None


def complete_metadata_batch(
    chunks: list[Chunk],
    schema: MetadataSchema,
    llm: LlmConfig,
) -> LlmBatchOutcome:
    """Return parsed metadata, or an error string if the batch HTTP/parse failed."""
    if not chunks or not llm.enabled():
        return LlmBatchOutcome(parsed={})
    provider = (llm.provider or "").lower()
    if provider != "anthropic":
        return LlmBatchOutcome(error=f"unsupported_provider: {provider or '(none)'}")
    try:
        import anthropic
    except ImportError as exc:
        return LlmBatchOutcome(error=f"anthropic_import_failed: {exc}")
    prompt = _batch_prompt(chunks, schema)
    try:
        client = anthropic.Anthropic(api_key=llm.api_key)
        response = _messages_create(client, llm, prompt)
        raw, diag = _response_payload(response)
        if not raw.strip():
            response = _messages_create(client, llm, prompt)
            raw, diag = _response_payload(response)
    except Exception as exc:
        return LlmBatchOutcome(error=_format_llm_exception(exc))
    parsed = _parse_batch(raw, chunks, schema)
    if parsed is None:
        return LlmBatchOutcome(error=_json_parse_error(raw, diag))
    if "max_tokens" in diag and len(parsed) < len(chunks):
        return LlmBatchOutcome(
            error=f"max_tokens: parsed {len(parsed)}/{len(chunks)} chunks; {diag}"
        )
    if not parsed:
        return LlmBatchOutcome(error=f"json_keys_unmatched; {diag}")
    return LlmBatchOutcome(parsed=parsed)


def _messages_create(client, llm: LlmConfig, prompt: str):
    kwargs = {
        "model": llm.model,
        "max_tokens": _MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        return client.messages.create(**kwargs, thinking={"type": "disabled"})
    except TypeError:
        return client.messages.create(**kwargs)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        if status in {400, 422}:
            return client.messages.create(**kwargs)
        raise


def _format_llm_exception(exc: BaseException) -> str:
    status = getattr(exc, "status_code", None)
    body = getattr(exc, "body", None)
    message = getattr(exc, "message", None) or str(exc)
    detail = ""
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        if isinstance(err, dict):
            detail = str(err.get("message") or err.get("type") or "")
    if status is not None:
        return f"anthropic {status}: {detail or message}"
    return f"{type(exc).__name__}: {message}"


def _response_payload(response) -> tuple[str, str]:
    """Join every text block; first block may be thinking, not JSON."""
    blocks = list(getattr(response, "content", None) or [])
    kinds: list[str] = []
    texts: list[str] = []
    for block in blocks:
        kind = str(getattr(block, "type", None) or type(block).__name__)
        kinds.append(kind)
        text = getattr(block, "text", None)
        if text:
            texts.append(str(text))
        thinking = getattr(block, "thinking", None)
        if thinking and not text:
            kinds[-1] = f"{kind}(thinking)"
    raw = "\n".join(texts)
    stop = getattr(response, "stop_reason", None) or "-"
    usage = getattr(response, "usage", None)
    in_tok = getattr(usage, "input_tokens", None)
    out_tok = getattr(usage, "output_tokens", None)
    diag = (
        f"stop={stop} blocks={','.join(kinds) or '(none)'} "
        f"in={in_tok} out={out_tok}"
    )
    return raw, diag


def _json_parse_error(raw: str, diag: str = "") -> str:
    snippet = re.sub(r"\s+", " ", (raw or "").strip())[:_ERROR_BODY_CHARS]
    suffix = f"; {diag}" if diag else ""
    if not snippet:
        return f"empty_response{suffix}"
    return f"json_parse: {snippet}{suffix}"


def empty_metadata(schema: MetadataSchema) -> ChunkMetadata:
    return ChunkMetadata(fields={name: () for name in schema.field_names})


def _batch_prompt(chunks: list[Chunk], schema: MetadataSchema) -> str:
    names = ", ".join(schema.field_names)
    parts = [
        "Extract structured metadata for each chunk independently.",
        f"Fields (each a list): {names}.",
        "topic values may be social factors (housing, income, discrimination, …) "
        "and/or health conditions (diabetes, maternal mortality, …).",
        "Each list item is {\"value\": string, \"origin\": explicit|inherited|inferred|unknown, "
        "\"confidence\": optional 0-1 number}.",
        "origin=inherited only when the value comes from Section:/Subsection: heading lines.",
        "origin=explicit when stated in the body. origin=inferred when clearly implied. "
        "Use an empty list when unknown. Do not invent values that are not grounded in that chunk.",
        "time_period values are calendar years only (2019, 2020). Expand a span such as "
        "2019-2022 or 2019 to 2022 into each year. Do not emit range strings. "
        "FY2020 is 2020. Omit vague phrases (2020s, last decade) and spans longer than 25 years.",
        "Return only compact JSON keyed by the integer index shown before each chunk (0, 1, 2, …). "
        "No markdown fences, no commentary, no preamble.",
        "",
        "Chunks:",
    ]
    for index, chunk in enumerate(chunks):
        parts.append(f"### {index}")
        parts.append(chunk.contextual_text)
        parts.append("")
    return "\n".join(parts)


def _parse_batch(
    raw: str,
    chunks: list[Chunk],
    schema: MetadataSchema,
) -> dict[str, ChunkMetadata] | None:
    text = raw.strip()
    fenced = _FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    elif text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    brace = text.find("{")
    if brace > 0:
        text = text[brace:]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    known_ids = {chunk.chunk_id for chunk in chunks}
    aliases: dict[str, str] = {}
    for index, chunk in enumerate(chunks):
        aliases[str(index)] = chunk.chunk_id
        aliases[f"c{index + 1}"] = chunk.chunk_id
        aliases[chunk.chunk_id] = chunk.chunk_id
        tail = chunk.chunk_id.rsplit(":", 1)[-1]
        aliases[tail] = chunk.chunk_id
    result: dict[str, ChunkMetadata] = {}
    for key, payload in data.items():
        chunk_id = aliases.get(str(key).strip(), "")
        if chunk_id not in known_ids:
            continue
        if not isinstance(payload, dict):
            result[chunk_id] = empty_metadata(schema)
            continue
        result[chunk_id] = _chunk_metadata(payload, schema)
    return result


def _chunk_metadata(payload: dict, schema: MetadataSchema) -> ChunkMetadata:
    fields: dict[str, tuple[MetadataValue, ...]] = {}
    for name in schema.field_names:
        parsed = _parse_values(payload.get(name))
        if name == TIME_FIELD:
            parsed = expand_time_values(parsed)
        fields[name] = parsed
    return ChunkMetadata(fields=fields)


def _parse_values(raw) -> tuple[MetadataValue, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        items = [raw] if raw.strip() else []
    elif isinstance(raw, list):
        items = list(raw)
    else:
        return ()
    seen: set[str] = set()
    values: list[MetadataValue] = []
    for item in items:
        parsed = _parse_value(item)
        if parsed is None:
            continue
        key = parsed.value.casefold()
        if key in seen:
            continue
        seen.add(key)
        values.append(parsed)
    return tuple(values)


def _parse_value(item) -> MetadataValue | None:
    if isinstance(item, str):
        text = item.strip()
        if not text:
            return None
        return MetadataValue(value=text, origin="explicit")
    if not isinstance(item, dict):
        return None
    text = str(item.get("value") or "").strip()
    if not text:
        return None
    origin_raw = str(item.get("origin") or "explicit").strip().lower()
    origin: MetadataOrigin = origin_raw if origin_raw in _ORIGINS else "explicit"
    confidence = item.get("confidence")
    score: float | None
    try:
        score = float(confidence) if confidence is not None and confidence != "" else None
    except (TypeError, ValueError):
        score = None
    if score is not None and not 0.0 <= score <= 1.0:
        score = None
    return MetadataValue(value=text, origin=origin, confidence=score)
