from __future__ import annotations

from pathlib import Path

from document_metadata_store.config import LlmConfig, PreprocessingConfig, load_app_config
from document_metadata_store.console import format_preprocess_run
from document_metadata_store.models import (
    Block,
    DocumentMetadata,
    Location,
    NormalizedDocument,
    Page,
)
from document_metadata_store.pipeline.loader import FileOutcome, LoadRun
from document_metadata_store.pipeline.preprocessor import preprocess_documents
from document_metadata_store.preprocess.engine import preprocess_document


def _doc(rows: list[tuple[int, str]], *, title: str | None = "Report") -> NormalizedDocument:
    pages: dict[int, list[Block]] = {}
    for page_number, text in rows:
        blocks = pages.setdefault(page_number, [])
        index = len(blocks) + 1
        blocks.append(
            Block(
                block_id=f"p{page_number}-b{index}",
                kind="text",
                text=text,
                location=Location(page=page_number),
            )
        )
    page_list = [
        Page(page_number=number, blocks=pages[number]) for number in sorted(pages)
    ]
    return NormalizedDocument(
        metadata=DocumentMetadata(id="test", title=title, document_type="pdf"),
        source="/tmp/test.pdf",
        pages=page_list,
    )


def _config(**overrides) -> PreprocessingConfig:
    base = PreprocessingConfig()
    return PreprocessingConfig(
        enabled=overrides.get("enabled", base.enabled),
        exclude_sections=overrides.get("exclude_sections", base.exclude_sections),
        aliases=overrides.get("aliases", base.aliases),
    )


def test_disabled_keeps_all() -> None:
    document = _doc([(1, "Contents"), (1, "Foreword"), (2, "Body")])
    processed = preprocess_document(document, _config(enabled=False), LlmConfig())
    assert processed.excluded_count() == 0
    assert processed.excluded_sections == []


def test_cover_until_contents_and_front_matter() -> None:
    document = _doc(
        [
            (1, "World report on health equity"),
            (2, "ISBN 978-92-4-010758-8"),
            (3, "Contents"),
            (3, "Foreword ............... v"),
            (3, "Chapter 1 Inequities"),
            (4, "Foreword"),
            (4, "Our world is an unequal one."),
            (5, "Executive summary"),
            (5, "This report presents evidence-based strategies for governments worldwide."),
        ],
        title="World report on health equity",
    )
    processed = preprocess_document(document, _config(), LlmConfig())
    types = [section.section_type for section in processed.excluded_sections]
    assert "cover" in types
    assert "table_of_contents" in types
    assert "foreword" in types
    assert "executive_summary" not in types

    by_id = {item.block_id: item for item in processed.iter_blocks()}
    assert by_id["p1-b1"].disposition == "exclude"
    assert by_id["p1-b1"].section_type == "cover"
    assert by_id["p2-b1"].section_type == "cover"
    assert by_id["p3-b1"].section_type == "table_of_contents"
    assert by_id["p3-b3"].section_type == "table_of_contents"
    assert by_id["p4-b1"].section_type == "foreword"
    assert by_id["p5-b1"].disposition == "keep"
    assert by_id["p5-b2"].disposition == "keep"
    assert by_id["p4-b2"].disposition == "exclude"


def test_lowercase_body_stays_in_exclude_span() -> None:
    document = _doc(
        [
            (1, "Contents"),
            (2, "Foreword"),
            (2, "our world is an unequal one without ending punctuation"),
            (3, "Executive summary"),
            (3, "This report presents evidence-based strategies for governments worldwide."),
        ]
    )
    processed = preprocess_document(document, _config(), LlmConfig())
    by_id = {item.block_id: item for item in processed.iter_blocks()}
    assert by_id["p2-b2"].disposition == "exclude"
    assert by_id["p2-b2"].section_type == "foreword"
    assert by_id["p3-b1"].disposition == "keep"


def test_preserved_table_blocks_skip_cheap_rules() -> None:
    document = NormalizedDocument(
        metadata=DocumentMetadata(id="t", title="T", document_type="pdf"),
        source="/tmp/t.pdf",
        pages=[
            Page(
                page_number=1,
                blocks=[
                    Block(
                        block_id="p1-b1",
                        kind="text",
                        text="Chapter 1 Methods",
                        location=Location(page=1),
                    ),
                    Block(
                        block_id="p1-b2",
                        kind="table",
                        text="iv",
                        location=Location(page=1),
                    ),
                ],
            )
        ],
    )
    processed = preprocess_document(document, _config(), LlmConfig())
    by_id = {item.block_id: item for item in processed.iter_blocks()}
    assert by_id["p1-b2"].disposition == "keep"


def test_toc_entry_does_not_steal_later_section() -> None:
    document = _doc(
        [
            (1, "Contents"),
            (1, "Acknowledgements ............... iv"),
            (1, "Chapter 1 Inequities"),
            (2, "Acknowledgements"),
            (2, "the team thanks reviewers for comments without a period"),
            (3, "Executive summary"),
            (3, "This report presents evidence-based strategies for governments worldwide."),
        ]
    )
    processed = preprocess_document(document, _config(), LlmConfig())
    types = [section.section_type for section in processed.excluded_sections]
    assert "acknowledgements" in types
    by_id = {item.block_id: item for item in processed.iter_blocks()}
    assert by_id["p1-b2"].section_type == "table_of_contents"
    assert by_id["p2-b1"].section_type == "acknowledgements"
    assert by_id["p2-b2"].disposition == "exclude"
    assert by_id["p3-b1"].disposition == "keep"


def test_forward_in_prose_is_not_foreword() -> None:
    document = _doc(
        [
            (1, "Contents"),
            (2, "Chapter 1 Methods"),
            (2, "Countries moving forward. Seizing on their example helps policy."),
        ]
    )
    processed = preprocess_document(document, _config(), LlmConfig())
    types = [section.section_type for section in processed.excluded_sections]
    assert "foreword" not in types
    by_id = {item.block_id: item for item in processed.iter_blocks()}
    assert by_id["p2-b2"].disposition == "keep"


def test_no_toc_skips_cover() -> None:
    document = _doc(
        [
            (1, "A short title"),
            (2, "Chapter 1 Inequities"),
            (2, "This chapter explains the main argument in several words of prose."),
        ]
    )
    processed = preprocess_document(document, _config(), LlmConfig())
    assert all(section.section_type != "cover" for section in processed.excluded_sections)
    by_id = {item.block_id: item for item in processed.iter_blocks()}
    assert by_id["p1-b1"].disposition == "keep"
    assert by_id["p2-b2"].disposition == "keep"


def test_bibliography_kept_by_default() -> None:
    document = _doc(
        [
            (1, "Chapter 1 Methods"),
            (1, "Findings are discussed in the following paragraphs of the report."),
            (2, "Bibliography"),
            (2, "Smith 2020. A book."),
        ]
    )
    processed = preprocess_document(document, _config(), LlmConfig())
    types = [section.section_type for section in processed.excluded_sections]
    assert "references" not in types
    by_id = {item.block_id: item for item in processed.iter_blocks()}
    assert by_id["p2-b1"].disposition == "keep"
    assert by_id["p2-b2"].disposition == "keep"


def test_bibliography_excluded_when_configured() -> None:
    document = _doc(
        [
            (1, "Chapter 1 Methods"),
            (1, "Findings are discussed in the following paragraphs of the report."),
            (2, "Bibliography"),
            (2, "Smith 2020. A book."),
        ]
    )
    exclude = tuple(_config().exclude_sections) + ("references",)
    processed = preprocess_document(document, _config(exclude_sections=exclude), LlmConfig())
    types = [section.section_type for section in processed.excluded_sections]
    assert "references" in types
    by_id = {item.block_id: item for item in processed.iter_blocks()}
    assert by_id["p2-b1"].disposition == "exclude"
    assert by_id["p2-b1"].classifier == "alias:references"


def test_console_lists_excluded_section_titles() -> None:
    document = _doc([(1, "Title page"), (2, "Contents"), (2, "Intro")])
    load_run = LoadRun(input_path=Path("documents"), recursive=True)
    load_run.outcomes.append(
        FileOutcome(
            path="documents/sample.pdf",
            status="loaded",
            document=document,
            pages=2,
            blocks=3,
            text_chars=20,
        )
    )
    prep = preprocess_documents(load_run, _config(), LlmConfig())
    text = format_preprocess_run(prep)
    assert "document-preprocess" in text
    assert "excluded_sections:" in text
    assert "table_of_contents" in text
    assert "Contents" in text
    assert "cover" in text
    assert "named_excludes:" in text


def test_console_prints_none_when_no_named_sections() -> None:
    document = _doc(
        [
            (1, "Chapter 1 Methods"),
            (1, "Findings are discussed in the following paragraphs of the report."),
        ]
    )
    load_run = LoadRun(input_path=Path("documents"), recursive=True)
    load_run.outcomes.append(
        FileOutcome(
            path="documents/plain.pdf",
            status="loaded",
            document=document,
            pages=1,
            blocks=2,
            text_chars=20,
        )
    )
    prep = preprocess_documents(load_run, _config(), LlmConfig())
    text = format_preprocess_run(prep)
    assert "excluded_sections: (none)" in text
    assert "named_excludes:" not in text


def test_load_app_config_reads_cover_and_aliases() -> None:
    app = load_app_config(cwd=Path(__file__).resolve().parents[1])
    assert "cover" in app.preprocessing.exclude_sections
    assert "executive_summary" not in app.preprocessing.exclude_sections
    assert "references" not in app.preprocessing.exclude_sections
    assert "bibliography" in app.preprocessing.aliases["references"]
    assert app.llm.model
