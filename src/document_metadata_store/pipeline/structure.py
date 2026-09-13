from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from document_metadata_store.config import LlmConfig, PreprocessingConfig
from document_metadata_store.models import PreprocessedDocument, StructuredDocument
from document_metadata_store.pipeline.preprocessor import PreprocessRun
from document_metadata_store.structure.engine import extract_structure


class StructureExtractor(Protocol):
    def extract(
        self,
        document: PreprocessedDocument,
        config: PreprocessingConfig,
        llm: LlmConfig | None = None,
    ) -> StructuredDocument:
        ...


@dataclass
class StructureOutcome:
    path: str
    document: StructuredDocument
    sections: int
    subsections: int
    max_depth: int
    implicit: bool


@dataclass
class StructureRun:
    outcomes: list[StructureOutcome] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "processed": len(self.outcomes),
            "sections": sum(item.sections for item in self.outcomes),
            "subsections": sum(item.subsections for item in self.outcomes),
            "implicit_title_sections": sum(1 for item in self.outcomes if item.implicit),
            "failed": len(self.failed),
        }


def extract_structures(
    prep_run: PreprocessRun,
    config: PreprocessingConfig,
    llm: LlmConfig | None = None,
) -> StructureRun:
    run = StructureRun()
    for item in prep_run.outcomes:
        try:
            structured = extract_structure(item.document, config, llm)
        except Exception as exc:  # noqa: BLE001 — continue batch
            run.failed.append((item.path, str(exc)))
            continue
        run.outcomes.append(
            StructureOutcome(
                path=item.path,
                document=structured,
                sections=structured.section_count(),
                subsections=structured.subsection_count(),
                max_depth=structured.max_depth(),
                implicit=structured.implicit_title,
            )
        )
    return run
