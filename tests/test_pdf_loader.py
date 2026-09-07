from __future__ import annotations

from pathlib import Path

from document_metadata_store.loaders.pdf import document_id_for, is_image_only, load_pdf
from tests.helpers import write_blank_pdf, write_text_pdf


def test_load_pdf_emits_blocks_not_page_strings(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "sample.pdf")
    before = pdf.read_bytes()
    document = load_pdf(pdf)

    assert document.metadata.document_type == "pdf"
    assert document.metadata.id == document_id_for(pdf)
    assert document.metadata.title == "Test Document"
    assert document.metadata.author == "Unit Test"
    assert len(document.pages) == 1
    texts = [block.text for block in document.pages[0].blocks]
    assert texts
    assert any("Heading Line" in text or "Body paragraph" in text for text in texts)
    assert all(block.location.page == 1 for block in document.pages[0].blocks)
    assert all(block.block_id.startswith("p1-b") for block in document.pages[0].blocks)
    # Must not collapse the page to a single undifferentiated string-only payload.
    assert document.block_count() >= 1
    assert pdf.read_bytes() == before


def test_blank_pdf_is_image_only(tmp_path: Path) -> None:
    pdf = write_blank_pdf(tmp_path / "blank.pdf")
    document = load_pdf(pdf)
    assert is_image_only(document)
    assert document.text_chars() == 0


def test_document_id_is_path_hash(tmp_path: Path) -> None:
    pdf = write_text_pdf(tmp_path / "a.pdf")
    first = document_id_for(pdf)
    second = document_id_for(pdf)
    assert first == second
    assert len(first) == 64
