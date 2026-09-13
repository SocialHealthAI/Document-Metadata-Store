from __future__ import annotations

import re
from pathlib import Path

import pytest

from document_metadata_store.config import LlmConfig, load_app_config
from document_metadata_store.pipeline.loader import load_documents
from document_metadata_store.pipeline.preprocessor import preprocess_documents
from document_metadata_store.pipeline.structure import extract_structures

WHO_NAME = "World report on social determinants of health equity, WHO 2025.pdf"
HP_GLOB = "Healthy People 2030*.pdf"


def _prep_run(repo: Path):
    app = load_app_config(cwd=repo)
    load_run = load_documents(app.documents, cwd=repo, display_root=repo)
    prep = preprocess_documents(load_run, app.preprocessing, LlmConfig())
    return extract_structures(prep, app.preprocessing, LlmConfig()), app


def test_who_structure_when_present() -> None:
    repo = Path(__file__).resolve().parents[1]
    pdf = repo / "documents" / WHO_NAME
    if not pdf.is_file():
        pytest.skip(f"WHO fixture not present: {WHO_NAME}")

    run, _app = _prep_run(repo)
    item = next(outcome for outcome in run.outcomes if outcome.path.endswith(WHO_NAME))
    nodes = list(item.document.iter_sections())
    headings = [node.heading for node in nodes]
    joined = " ".join(heading.lower() for heading in headings)
    assert 8 <= item.document.node_count() < 90
    assert item.max_depth >= 3
    assert "chapter" in joined or "part" in joined
    assert "executive summary" in joined
    assert not any(re.fullmatch(r"Part \d+: Chapter \d+", heading) for heading in headings)
    assert not any(heading.startswith("1. World Health") for heading in headings)
    assert not any(".ss01" in heading for heading in headings)
    assert not any(re.fullmatch(r"Part \d+\s*:", heading, flags=re.I) for heading in headings)
    assert not any(re.match(r"^\d+\s*,\s*\d+", heading) for heading in headings)


def test_healthy_people_implicit_or_title_section() -> None:
    repo = Path(__file__).resolve().parents[1]
    matches = sorted((repo / "documents").rglob("Healthy People 2030*.pdf"))
    if not matches:
        pytest.skip("Healthy People scrape PDF not present")

    run, _app = _prep_run(repo)
    target = matches[0].name
    item = next(outcome for outcome in run.outcomes if outcome.path.endswith(target))
    assert item.implicit
    assert item.sections == 1
    assert item.document.node_count() == 1
    first = item.document.sections[0]
    assert first.level == 1
    assert first.implicit
    assert first.heading
