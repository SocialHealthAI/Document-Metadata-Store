from __future__ import annotations

import re
from pathlib import Path

import pytest

from document_metadata_store.config import LlmConfig, load_app_config
from document_metadata_store.pipeline.chunker import chunk_documents
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


def _chunk_run(repo: Path):
    struct_run, app = _prep_run(repo)
    return chunk_documents(struct_run, app.chunking), struct_run, app


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


def test_who_chunks_inherit_nested_headings() -> None:
    repo = Path(__file__).resolve().parents[1]
    pdf = repo / "documents" / WHO_NAME
    if not pdf.is_file():
        pytest.skip(f"WHO fixture not present: {WHO_NAME}")

    chunk_run, _struct, _app = _chunk_run(repo)
    item = next(outcome for outcome in chunk_run.outcomes if outcome.path.endswith(WHO_NAME))
    assert item.chunks > 3
    headings = " ".join(chunk.section_heading.lower() for chunk in item.document.chunks)
    assert "chapter" in headings or "recommendation" in headings or "executive summary" in headings
    assert all("Section:" in chunk.contextual_text for chunk in item.document.chunks)
    assert not any(len(chunk.original_text) > 200_000 for chunk in item.document.chunks)


def test_healthy_people_chunks_under_implicit_title() -> None:
    repo = Path(__file__).resolve().parents[1]
    matches = sorted((repo / "documents").rglob("Healthy People 2030*.pdf"))
    if not matches:
        pytest.skip("Healthy People scrape PDF not present")

    chunk_run, struct_run, app = _chunk_run(repo)
    target = matches[0].name
    structured = next(outcome for outcome in struct_run.outcomes if outcome.path.endswith(target))
    item = next(outcome for outcome in chunk_run.outcomes if outcome.path.endswith(target))
    first = structured.document.sections[0]
    body_chars = sum(len(block.text) for unit in first.body for block in unit.blocks)
    assert item.chunks >= 1
    assert all(chunk.section_heading == first.heading for chunk in item.document.chunks)
    if body_chars > app.chunking.target_size:
        assert item.chunks >= 2
