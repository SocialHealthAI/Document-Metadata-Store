from __future__ import annotations

from pathlib import Path

from document_metadata_store.config import DocumentsConfig
from document_metadata_store.pipeline.loader import load_documents

WHO_NAME = "World report on social determinants of health equity, WHO 2025.pdf"


def test_who_fixture_loads_when_present() -> None:
    repo = Path(__file__).resolve().parents[1]
    pdf = repo / "documents" / WHO_NAME
    if not pdf.is_file():
        return

    before = pdf.stat()
    run = load_documents(
        DocumentsConfig(input_path=repo / "documents", recursive=True),
        cwd=repo,
        display_root=repo,
    )
    after = pdf.stat()
    assert after.st_mtime_ns == before.st_mtime_ns
    assert after.st_size == before.st_size

    match = next((item for item in run.outcomes if item.path.endswith(WHO_NAME)), None)
    assert match is not None
    assert match.status == "loaded", match.error or match.reason
    assert match.pages and match.pages > 0
    assert match.blocks and match.blocks > 1
    assert match.text_chars and match.text_chars > 0
    assert match.document is not None
    assert match.document.pages[0].blocks
    assert match.document.metadata.document_type == "pdf"
