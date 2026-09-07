from __future__ import annotations

import re
from pathlib import Path

from document_metadata_store.models import Block
from document_metadata_store.pipeline.loader import LoadRun

_PREVIEW_TEXT_WIDTH = 120


def format_load_run(
    run: LoadRun,
    *,
    cwd: Path | None = None,
    preview_blocks: int = 0,
) -> str:
    working = cwd or Path.cwd()
    input_display = _input_display(run.input_path, working)
    lines = [
        "document-load",
        f"  input_path: {input_display}",
        f"  recursive: {str(run.recursive).lower()}",
    ]
    if preview_blocks > 0:
        lines.append(f"  preview_blocks: {preview_blocks}")
    lines.append("")
    for item in run.outcomes:
        if item.status == "loaded":
            lines.append(f"  loaded  {item.path}")
            if item.title:
                lines.append(f"          title: {item.title}")
            lines.append(
                f"          pages: {item.pages}  blocks: {item.blocks}  "
                f"text_chars: {item.text_chars}"
            )
            if preview_blocks > 0 and item.document is not None:
                lines.extend(_preview_lines(item.document.iter_blocks(), preview_blocks))
        elif item.status == "skipped":
            lines.append(f"  skipped {item.path}")
            lines.append(f"          reason: {item.reason}")
        else:
            lines.append(f"  failed  {item.path}")
            lines.append(f"          error: {item.error}")
        lines.append("")

    counts = run.counts()
    lines.append(
        "summary: "
        f"discovered={counts['discovered']} "
        f"loaded={counts['loaded']} "
        f"skipped_unsupported={counts['skipped_unsupported']} "
        f"skipped_image_only={counts['skipped_image_only']} "
        f"failed={counts['failed']}"
    )
    return "\n".join(lines) + "\n"


def _preview_lines(blocks: list[Block], limit: int) -> list[str]:
    total = len(blocks)
    shown = blocks[:limit]
    if total <= limit:
        header = f"          preview (all {total}):"
    else:
        header = f"          preview (first {limit} of {total}):"
    lines = [header]
    for block in shown:
        text = _one_line(block.text, _PREVIEW_TEXT_WIDTH)
        lines.append(f"            {block.block_id}  {block.kind}  {text}")
    return lines


def _one_line(text: str, width: int) -> str:
    collapsed = re.sub(r"\s+", " ", text).strip()
    if len(collapsed) <= width:
        return collapsed
    return collapsed[: width - 3] + "..."


def _input_display(input_path: Path, cwd: Path) -> str:
    try:
        relative = input_path.resolve().relative_to(cwd.resolve()).as_posix()
        return relative if relative.startswith(".") else f"./{relative}"
    except ValueError:
        return input_path.resolve().as_posix()
