from __future__ import annotations

import re
from pathlib import Path

from document_metadata_store.config import LlmConfig, PreprocessingConfig
from document_metadata_store.console import format_structure_run
from document_metadata_store.models import (
    Block,
    DocumentMetadata,
    Location,
    NormalizedDocument,
    Page,
)
from document_metadata_store.pipeline.preprocessor import preprocess_documents
from document_metadata_store.pipeline.loader import FileOutcome, LoadRun
from document_metadata_store.pipeline.structure import extract_structures
from document_metadata_store.preprocess.engine import preprocess_document
from document_metadata_store.models import AnnotatedBlock
from document_metadata_store.structure.engine import extract_structure
from document_metadata_store.structure.headings import cheap_heading_level


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


def _prep(rows: list[tuple[int, str]], *, title: str | None = "Report", **config_overrides):
    base = PreprocessingConfig()
    config = PreprocessingConfig(
        enabled=config_overrides.get("enabled", base.enabled),
        exclude_sections=config_overrides.get("exclude_sections", base.exclude_sections),
        aliases=config_overrides.get("aliases", base.aliases),
    )
    return preprocess_document(_doc(rows, title=title), config, LlmConfig()), config


def test_numbered_headings_nest_under_chapter() -> None:
    processed, config = _prep(
        [
            (1, "Chapter 1 Methods"),
            (1, "This chapter explains the main argument in several words of prose."),
            (1, "1.2 Updates since the Commission"),
            (1, "The following paragraphs describe progress against earlier targets."),
        ]
    )
    structured = extract_structure(processed, config, LlmConfig())
    assert structured.section_count() == 1
    chapter = structured.sections[0]
    assert "Chapter 1" in chapter.heading
    assert chapter.level == 2
    assert len(chapter.children) == 1
    assert chapter.children[0].heading.startswith("1.2")
    assert chapter.children[0].level == 3
    headings = [node.heading for node in structured.iter_sections()]
    assert "Contents" not in headings


def test_no_headings_uses_implicit_title() -> None:
    processed, config = _prep(
        [
            (1, "This report presents evidence-based strategies for governments worldwide."),
            (1, "Another paragraph continues the argument without a heading line."),
        ],
        title="Poverty",
    )
    structured = extract_structure(processed, config, LlmConfig())
    assert structured.implicit_title
    assert structured.section_count() == 1
    assert structured.sections[0].heading == "Poverty"
    assert structured.sections[0].implicit
    body_blocks = [block for unit in structured.sections[0].body for block in unit.blocks]
    assert len(body_blocks) == 2


def test_excluded_blocks_are_omitted_from_tree() -> None:
    processed, config = _prep(
        [
            (1, "Title page"),
            (2, "Contents"),
            (3, "Chapter 1 Methods"),
            (3, "Findings are discussed in the following paragraphs of the report."),
        ]
    )
    structured = extract_structure(processed, config, LlmConfig())
    headings = [node.heading.lower() for node in structured.iter_sections()]
    assert not any("contents" == item for item in headings)
    assert not any("title page" == item for item in headings)
    assert any("chapter 1" in item for item in headings)
    start_ids = {node.start_block_id for node in structured.iter_sections()}
    excluded_ids = {
        block.block_id
        for block in processed.iter_blocks()
        if block.disposition == "exclude"
    }
    assert start_ids.isdisjoint(excluded_ids)


def _annotated(text: str) -> AnnotatedBlock:
    return AnnotatedBlock(
        block=Block(
            block_id="p1-b1",
            kind="text",
            text=text,
            location=Location(page=1),
        )
    )


def test_who_false_positives_are_not_headings() -> None:
    exclude = PreprocessingConfig().exclude_sections
    rejected = [
        "Part 1: Chapter 1",
        "Part 1 comprises two chapters which provide the rationale for the",
        "Chapter 8 sets out recommendations for stronger governance to facilitate",
        "Annex 1 for further description of the approach and the methods used for",
        "(Part 2, Chapter 3)",
        "1. World Health Organization. GHE: Life 9. Marmot MG, Wilkinson RG, editors. Social",
        "2 May 2024).",
        "3.0 IGO.",
        "42 /m.ss01/i.ss01ll/i.ss01o/n.ss01",
        "1. Addressing economic inequality and investing in social",
        "recommendations.",
        "PART 1: The state of social determinants of health equity PART 3: Bringing about change",
        "PaRT 1:",
        "CHAPTER 2.2",
        "6 , 7",
        "1 , 2 , 3 , 4",
        "1",
        "domains:",
        "54. United Nations Maternal Mortality Estimation",
        "8 deaths per",
        "2 billion more are expected",
        "2.1 describes the pathways and mechanisms through which these",
    ]
    for text in rejected:
        assert cheap_heading_level(_annotated(text), exclude) is None, text

    accepted = {
        "Executive summary": 1,
        "Chapter 1 Methods": 2,
        "ReCOMMeNDaTiON 3.1": 3,
        "1.1.1 Definitions": 4,
        "3.1.1 Use progressive taxation to expand fiscal space for income transfers and": 4,
        "ChaPTeR 3:": 2,
        "Cha PTeR 1:": 2,
        "Re COMMeNDa Ti ON 3.1": 3,
        "aNNeX 1:": 1,
        "aNNe X 2:": 1,
    }
    for text, level in accepted.items():
        assert cheap_heading_level(_annotated(text), exclude) == level, text


def test_heading_light_web_pdf_is_one_implicit_section() -> None:
    processed, config = _prep(
        [
            (1, "1"),
            (1, "Beverages Provided by Schools"),
            (1, "Related Evidence-Based Resources (3)"),
            (1, "Related Objectives (4)"),
            (1, "About This Literature Summary"),
            (1, "Healthy People 2030 organizes the social determinants of health into 5"),
            (2, "4. Neighborhood and Built Environment"),
            (2, "1. Economic Stability"),
            (3, "6 , 7"),
            (3, "Literature Summary"),
            (5, "Citations"),
        ],
        title="Access to Foods That Support Healthy Dietary Patterns",
    )
    structured = extract_structure(processed, config, LlmConfig())
    assert structured.implicit_title
    assert structured.section_count() == 1
    assert structured.sections[0].heading == "Access to Foods That Support Healthy Dietary Patterns"
    assert structured.sections[0].implicit


def test_letter_spaced_chapter_stitches_wrapped_title() -> None:
    processed, config = _prep(
        [
            (1, "Cha PTeR 1:"),
            (1, "Inequities in"),
            (1, "today's world"),
            (1, "This chapter explains the main argument in several words of prose."),
        ]
    )
    structured = extract_structure(processed, config, LlmConfig())
    heading = structured.sections[0].heading.lower()
    assert "chapter 1" in heading
    assert "inequities" in heading
    assert structured.section_count() == 1


def test_annex_single_numbers_follow_named_heading() -> None:
    processed, config = _prep(
        [
            (1, "Annex 2:"),
            (1, "1. Introduction"),
            (1, "The annex describes how the expert groups were formed and consulted."),
            (1, "2. Formation of the expert groups"),
            (1, "Members were nominated by regional offices and partner institutions."),
        ]
    )
    structured = extract_structure(processed, config, LlmConfig())
    headings = [node.heading for node in structured.iter_sections()]
    assert headings[0].lower().startswith("annex 2")
    assert "1. Introduction" in headings
    assert "2. Formation of the expert groups" in headings


def test_references_do_not_promote_bibliography_lines() -> None:
    processed, config = _prep(
        [
            (1, "ChaPTeR 9:"),
            (1, "Closing remarks occupy this paragraph of the final chapter."),
            (2, "References"),
            (2, "54. United Nations Maternal Mortality Estimation"),
            (2, "Inter-agency Group. Trends in Maternal Mortality follow in this note."),
        ]
    )
    structured = extract_structure(processed, config, LlmConfig())
    headings = [node.heading for node in structured.iter_sections()]
    assert "References" in headings
    assert not any(item.startswith("54.") for item in headings)


def test_repeated_running_headers_are_not_sections() -> None:
    rows = []
    for page in range(1, 5):
        rows.append((page, "Part 1: Chapter 1"))
        rows.append((page, f"Body paragraph on page {page} continues the argument in prose."))
    rows.append((2, "1.1.1 Definitions"))
    rows.append((2, "Definitions of key terms follow in the next several sentences."))
    processed, config = _prep(rows)
    structured = extract_structure(processed, config, LlmConfig())
    headings = [node.heading for node in structured.iter_sections()]
    assert not any(re.fullmatch(r"Part \d+: Chapter \d+", item) for item in headings)
    assert any(item.startswith("1.1.1") for item in headings)


def test_console_prints_outline() -> None:
    processed, config = _prep(
        [
            (1, "Chapter 1 Methods"),
            (1, "This chapter explains the main argument in several words of prose."),
        ]
    )
    load_run = LoadRun(input_path=Path("documents"), recursive=True)
    load_run.outcomes.append(
        FileOutcome(
            path="documents/sample.pdf",
            status="loaded",
            document=_doc(
                [
                    (1, "Chapter 1 Methods"),
                    (1, "This chapter explains the main argument in several words of prose."),
                ]
            ),
            pages=1,
            blocks=2,
            text_chars=20,
        )
    )
    prep = preprocess_documents(load_run, config, LlmConfig())
    structured = extract_structures(prep, config, LlmConfig())
    text = format_structure_run(structured)
    assert "document-structure" in text
    assert "outline:" in text
    assert "Chapter 1 Methods" in text
