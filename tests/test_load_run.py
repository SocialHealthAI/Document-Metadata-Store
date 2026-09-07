from __future__ import annotations

from pathlib import Path

from document_metadata_store.config import DocumentsConfig
from document_metadata_store.console import format_load_run
from document_metadata_store.pipeline.loader import load_documents
from tests.helpers import write_blank_pdf, write_broken_pdf, write_text_pdf


def test_discovers_pdfs_and_skips_others(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    write_text_pdf(documents / "report.pdf", title="World Report Fixture")
    write_blank_pdf(documents / "scan.pdf")
    write_broken_pdf(documents / "broken.pdf")
    (documents / "notes.txt").write_text("not a pdf", encoding="utf-8")
    nested = documents / "sub"
    nested.mkdir()
    write_text_pdf(nested / "nested.pdf", title=None)

    run = load_documents(
        DocumentsConfig(input_path=documents, recursive=True),
        cwd=tmp_path,
        display_root=tmp_path,
    )
    counts = run.counts()
    assert counts["discovered"] == 5
    assert counts["loaded"] == 2
    assert counts["skipped_unsupported"] == 1
    assert counts["skipped_image_only"] == 1
    assert counts["failed"] == 1

    by_path = {item.path: item for item in run.outcomes}
    assert by_path["documents/notes.txt"].reason.startswith("unsupported_format")
    assert by_path["documents/scan.pdf"].reason == "image_only"
    assert by_path["documents/broken.pdf"].status == "failed"
    loaded = by_path["documents/report.pdf"]
    assert loaded.status == "loaded"
    assert loaded.title == "World Report Fixture"
    assert loaded.pages == 1
    assert loaded.blocks >= 1
    assert loaded.text_chars and loaded.text_chars > 0
    assert loaded.document is not None
    assert loaded.document.source.endswith("report.pdf")


def test_console_omits_block_text(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    write_text_pdf(documents / "report.pdf", title="Console Title")
    (documents / "notes.txt").write_text("x", encoding="utf-8")

    run = load_documents(
        DocumentsConfig(input_path=documents, recursive=True),
        cwd=tmp_path,
        display_root=tmp_path,
    )
    text = format_load_run(run, cwd=tmp_path)
    assert "document-load" in text
    assert "input_path: ./documents" in text
    assert "recursive: true" in text
    assert "preview_blocks:" not in text
    assert "loaded  documents/report.pdf" in text
    assert "title: Console Title" in text
    assert "pages:" in text and "blocks:" in text and "text_chars:" in text
    assert "skipped documents/notes.txt" in text
    assert "unsupported_format (txt)" in text
    assert "summary:" in text
    assert "Body paragraph text for the loader." not in text
    assert "Heading Line" not in text


def test_console_preview_blocks(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    write_text_pdf(documents / "report.pdf", title="Preview Title")

    run = load_documents(
        DocumentsConfig(input_path=documents, recursive=True),
        cwd=tmp_path,
        display_root=tmp_path,
    )
    text = format_load_run(run, cwd=tmp_path, preview_blocks=2)
    assert "preview_blocks: 2" in text
    assert "preview (" in text
    assert "p1-b1" in text
    assert "Heading Line" in text
    loaded = run.outcomes[0]
    assert loaded.document is not None
    kinds = {block.kind for block in loaded.document.iter_blocks()[:2]}
    assert kinds <= {"text", "heading_candidate", "paragraph", "list_item", "table", "caption"}


def test_non_recursive_skips_nested(tmp_path: Path) -> None:
    documents = tmp_path / "documents"
    documents.mkdir()
    write_text_pdf(documents / "top.pdf")
    nested = documents / "sub"
    nested.mkdir()
    write_text_pdf(nested / "nested.pdf")

    run = load_documents(
        DocumentsConfig(input_path=documents, recursive=False),
        cwd=tmp_path,
        display_root=tmp_path,
    )
    assert run.counts()["loaded"] == 1
    assert run.outcomes[0].path == "documents/top.pdf"
