from __future__ import annotations

import re
from pathlib import Path

from document_metadata_store.models import AnnotatedBlock, Block, Chunk, SectionNode
from document_metadata_store.pipeline.chunker import ChunkRun
from document_metadata_store.pipeline.loader import LoadRun
from document_metadata_store.pipeline.preprocessor import PreprocessOutcome, PreprocessRun
from document_metadata_store.pipeline.structure import StructureRun

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


def format_preprocess_run(
    run: PreprocessRun,
    *,
    preview_blocks: int = 0,
) -> str:
    lines = [
        "document-preprocess",
        f"  enabled: {str(run.enabled).lower()}",
        f"  exclude_sections: {', '.join(run.exclude_sections)}",
        "",
    ]
    for item in run.outcomes:
        lines.append(f"  processed  {item.path}")
        lines.append(
            f"             kept: {item.kept}  excluded: {item.excluded}  "
            f"by_rule: {item.by_rule}  by_alias: {item.by_alias}  by_llm: {item.by_llm}"
        )
        lines.extend(_excluded_section_lines(item))
        if preview_blocks > 0:
            lines.extend(
                _annotated_preview_lines(item.document.iter_blocks(), preview_blocks)
            )
        lines.append("")
    for path, error in run.failed:
        lines.append(f"  failed  {path}")
        lines.append(f"          error: {error}")
        lines.append("")
    counts = run.counts()
    lines.append(
        "summary: "
        f"processed={counts['processed']} "
        f"kept_blocks={counts['kept_blocks']} "
        f"excluded_blocks={counts['excluded_blocks']} "
        f"failed={counts['failed']}"
    )
    recap = _named_exclude_recap(run)
    if recap:
        lines.append("named_excludes:")
        lines.extend(recap)
    return "\n".join(lines) + "\n"


def format_structure_run(
    run: StructureRun,
    *,
    preview_blocks: int = 0,
) -> str:
    counts = run.counts()
    lines = [
        "document-structure",
        f"  sections: {counts['sections']}  subsections: {counts['subsections']}  "
        f"implicit_title_sections: {counts['implicit_title_sections']}",
        "",
    ]
    for item in run.outcomes:
        implicit = "  implicit: true" if item.implicit else ""
        lines.append(f"  processed  {item.path}")
        lines.append(
            f"             sections: {item.sections}  max_depth: {item.max_depth}{implicit}"
        )
        outline = item.document.iter_sections()
        if outline:
            lines.append("             outline:")
            for node in outline:
                indent = "  " * max(node.level - 1, 0)
                title = node.heading.replace('"', "'")
                lines.append(
                    f"               {node.level}  {indent}\"{title}\"  {node.start_block_id}"
                )
        else:
            lines.append("             outline: (none)")
        if preview_blocks > 0:
            lines.extend(_structure_preview_lines(outline, preview_blocks))
        lines.append("")
    for path, error in run.failed:
        lines.append(f"  failed  {path}")
        lines.append(f"          error: {error}")
        lines.append("")
    lines.append(
        "summary: "
        f"processed={counts['processed']} "
        f"sections={counts['sections']} "
        f"subsections={counts['subsections']} "
        f"failed={counts['failed']}"
    )
    return "\n".join(lines) + "\n"


def format_chunk_run(
    run: ChunkRun,
    *,
    preview_blocks: int = 0,
) -> str:
    counts = run.counts()
    lines = [
        "document-chunk",
        f"  chunks: {counts['chunks']}  oversized_atomic: {counts['oversized_atomic']}",
        "",
    ]
    for item in run.outcomes:
        lines.append(f"  processed  {item.path}")
        lines.append(
            f"             chunks: {item.chunks}  max_chars: {item.max_chars}"
        )
        if item.document.chunks:
            lines.append("             chunks:")
            for index, chunk in enumerate(item.document.chunks, start=1):
                title = chunk.section_heading.replace('"', "'")
                lines.append(
                    f'               c{index}  "{title}"  '
                    f"{len(chunk.original_text)}  {chunk.start_block_id}"
                )
        else:
            lines.append("             chunks: (none)")
        if preview_blocks > 0:
            lines.extend(_chunk_preview_lines(item.document.chunks, preview_blocks))
        lines.append("")
    for path, error in run.failed:
        lines.append(f"  failed  {path}")
        lines.append(f"          error: {error}")
        lines.append("")
    lines.append(
        "summary: "
        f"processed={counts['processed']} "
        f"chunks={counts['chunks']} "
        f"oversized_atomic={counts['oversized_atomic']} "
        f"failed={counts['failed']}"
    )
    return "\n".join(lines) + "\n"


def _chunk_preview_lines(chunks: list[Chunk], limit: int) -> list[str]:
    total = len(chunks)
    shown = chunks[:limit]
    if total <= limit:
        header = f"             preview (all {total}):"
    else:
        header = f"             preview (first {limit} of {total}):"
    lines = [header]
    for chunk in shown:
        text = _one_line(chunk.contextual_text, _PREVIEW_TEXT_WIDTH)
        lines.append(f"               {chunk.chunk_id}  {text}")
    return lines


def _structure_preview_lines(nodes: list[SectionNode], limit: int) -> list[str]:
    total = len(nodes)
    shown = nodes[:limit]
    if total <= limit:
        header = f"             preview (all {total}):"
    else:
        header = f"             preview (first {limit} of {total}):"
    lines = [header]
    for node in shown:
        body_blocks = sum(len(unit.blocks) for unit in node.body)
        lines.append(
            f"               {node.section_id}  L{node.level}  "
            f"children={len(node.children)}  body_blocks={body_blocks}  {node.heading[:80]}"
        )
    return lines


def _excluded_section_lines(item: PreprocessOutcome) -> list[str]:
    sections = item.document.excluded_sections
    if not sections:
        if item.excluded:
            return [
                "             excluded_sections: (none)",
                "             note: blocks excluded by rules only "
                "(running headers, TOC leaders, or roman folios)",
            ]
        return ["             excluded_sections: (none)"]
    width = max(len(section.section_type) for section in sections)
    lines = ["             excluded_sections:"]
    for section in sections:
        title = section.title.replace('"', "'")
        lines.append(
            f"               {section.section_type:<{width}}  "
            f'"{title}"  {section.start_block_id}'
        )
    return lines


def _named_exclude_recap(run: PreprocessRun) -> list[str]:
    lines: list[str] = []
    for item in run.outcomes:
        if not item.document.excluded_sections:
            continue
        lines.append(f"  {item.path}")
        width = max(len(section.section_type) for section in item.document.excluded_sections)
        for section in item.document.excluded_sections:
            title = section.title.replace('"', "'")
            lines.append(
                f"    {section.section_type:<{width}}  "
                f'"{title}"  {section.start_block_id}'
            )
    return lines


def _annotated_preview_lines(blocks: list[AnnotatedBlock], limit: int) -> list[str]:
    total = len(blocks)
    shown = blocks[:limit]
    if total <= limit:
        header = f"             preview (all {total}):"
    else:
        header = f"             preview (first {limit} of {total}):"
    lines = [header]
    for item in shown:
        text = _one_line(item.text, _PREVIEW_TEXT_WIDTH)
        section = item.section_type or "-"
        lines.append(
            f"               {item.block_id}  {item.kind}  {item.disposition}  "
            f"{section}  {text}"
        )
    return lines


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
