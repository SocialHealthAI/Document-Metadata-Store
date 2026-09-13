from __future__ import annotations

from pathlib import Path

import pytest

from document_metadata_store.config import LlmConfig, load_app_config
from document_metadata_store.pipeline.loader import load_documents
from document_metadata_store.pipeline.preprocessor import preprocess_documents

WHO_NAME = "World report on social determinants of health equity, WHO 2025.pdf"


def test_who_preprocess_when_present() -> None:
    repo = Path(__file__).resolve().parents[1]
    pdf = repo / "documents" / WHO_NAME
    if not pdf.is_file():
        pytest.skip(f"WHO fixture not present: {WHO_NAME}")

    app = load_app_config(cwd=repo)
    load_run = load_documents(app.documents, cwd=repo, display_root=repo)
    prep = preprocess_documents(load_run, app.preprocessing, LlmConfig())
    assert prep.outcomes
    item = next(outcome for outcome in prep.outcomes if outcome.path.endswith(WHO_NAME))
    types = {section.section_type for section in item.document.excluded_sections}
    assert "cover" in types
    assert "table_of_contents" in types
    assert "foreword" in types
    titles = {section.section_type: section.title.lower() for section in item.document.excluded_sections}
    assert "contents" in titles.get("table_of_contents", "")
    assert "acknowledgements" in types
    assert not any("seizing" in section.title.lower() for section in item.document.excluded_sections)
    assert item.kept > 0
    assert item.excluded > 200
    exec_kept = any(
        "executive summary" in block.text.lower() and block.disposition == "keep"
        for block in item.document.iter_blocks()
    )
    assert exec_kept
    assert "references" not in types
    refs_kept = any(
        block.text.strip().lower() == "references" and block.disposition == "keep"
        for block in item.document.iter_blocks()
    )
    assert refs_kept
