from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from document_metadata_store.config import LlmConfig, PreprocessingConfig
from document_metadata_store.models import NormalizedDocument, PreprocessedDocument
from document_metadata_store.pipeline.loader import LoadRun
from document_metadata_store.preprocess.engine import preprocess_document


class Preprocessor(Protocol):
    def preprocess(
        self,
        document: NormalizedDocument,
        config: PreprocessingConfig,
        llm: LlmConfig | None = None,
    ) -> PreprocessedDocument:
        ...


@dataclass
class PreprocessOutcome:
    path: str
    document: PreprocessedDocument
    kept: int
    excluded: int
    by_rule: int
    by_alias: int
    by_llm: int


@dataclass
class PreprocessRun:
    enabled: bool
    exclude_sections: tuple[str, ...]
    outcomes: list[PreprocessOutcome] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "processed": len(self.outcomes),
            "kept_blocks": sum(item.kept for item in self.outcomes),
            "excluded_blocks": sum(item.excluded for item in self.outcomes),
            "failed": len(self.failed),
        }


def preprocess_documents(
    load_run: LoadRun,
    config: PreprocessingConfig,
    llm: LlmConfig | None = None,
) -> PreprocessRun:
    run = PreprocessRun(enabled=config.enabled, exclude_sections=config.exclude_sections)
    for item in load_run.outcomes:
        if item.status != "loaded" or item.document is None:
            continue
        try:
            processed = preprocess_document(item.document, config, llm)
        except Exception as exc:  # noqa: BLE001 — continue batch
            run.failed.append((item.path, str(exc)))
            continue
        classifiers = processed.classifier_counts()
        run.outcomes.append(
            PreprocessOutcome(
                path=item.path,
                document=processed,
                kept=processed.kept_count(),
                excluded=processed.excluded_count(),
                by_rule=classifiers["by_rule"],
                by_alias=classifiers["by_alias"],
                by_llm=classifiers["by_llm"],
            )
        )
    return run
