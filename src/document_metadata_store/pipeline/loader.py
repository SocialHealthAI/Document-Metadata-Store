from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from document_metadata_store.config import DocumentsConfig, load_documents_config
from document_metadata_store.loaders.pdf import PdfLoadError, is_image_only, load_pdf
from document_metadata_store.models import NormalizedDocument

OutcomeStatus = Literal["loaded", "skipped", "failed"]


class DocumentLoader(Protocol):
    """Replaceable load stage. Callers depend on this, not a format-specific type."""

    def load(self, path: Path, *, display_source: str | None = None) -> NormalizedDocument:
        ...


@dataclass
class FileOutcome:
    path: str
    status: OutcomeStatus
    reason: str | None = None
    error: str | None = None
    title: str | None = None
    pages: int | None = None
    blocks: int | None = None
    text_chars: int | None = None
    document: NormalizedDocument | None = None


@dataclass
class LoadRun:
    input_path: Path
    recursive: bool
    outcomes: list[FileOutcome] = field(default_factory=list)

    def documents(self) -> list[NormalizedDocument]:
        return [item.document for item in self.outcomes if item.document is not None]

    def counts(self) -> dict[str, int]:
        loaded = skipped_unsupported = skipped_image_only = failed = 0
        for item in self.outcomes:
            if item.status == "loaded":
                loaded += 1
            elif item.status == "failed":
                failed += 1
            elif item.reason and item.reason.startswith("unsupported_format"):
                skipped_unsupported += 1
            elif item.reason == "image_only":
                skipped_image_only += 1
        return {
            "discovered": len(self.outcomes),
            "loaded": loaded,
            "skipped_unsupported": skipped_unsupported,
            "skipped_image_only": skipped_image_only,
            "failed": failed,
        }


def discover_files(config: DocumentsConfig) -> list[Path]:
    root = config.input_path
    if not root.exists():
        return []
    if root.is_file():
        return [root]

    iterator = root.rglob("*") if config.recursive else root.iterdir()
    files = [
        path
        for path in iterator
        if path.is_file() and not path.name.startswith(".")
    ]
    return sorted(files, key=lambda path: path.as_posix().lower())


def load_documents(
    config: DocumentsConfig | None = None,
    *,
    cwd: Path | None = None,
    display_root: Path | None = None,
) -> LoadRun:
    working = cwd or Path.cwd()
    resolved = config or load_documents_config(cwd=working)
    rel_root = display_root or working
    run = LoadRun(input_path=resolved.input_path, recursive=resolved.recursive)

    for path in discover_files(resolved):
        display = _display_path(path, rel_root)
        suffix = path.suffix.lower()
        if suffix != ".pdf":
            ext = suffix.lstrip(".") or "unknown"
            run.outcomes.append(
                FileOutcome(
                    path=display,
                    status="skipped",
                    reason=f"unsupported_format ({ext})",
                )
            )
            continue
        try:
            document = load_pdf(path, display_source=display)
        except PdfLoadError as exc:
            run.outcomes.append(
                FileOutcome(path=display, status="failed", error=str(exc))
            )
            continue
        except Exception as exc:  # noqa: BLE001 — per-file failure, continue batch
            run.outcomes.append(
                FileOutcome(path=display, status="failed", error=str(exc))
            )
            continue

        if is_image_only(document):
            run.outcomes.append(
                FileOutcome(path=display, status="skipped", reason="image_only")
            )
            continue

        run.outcomes.append(
            FileOutcome(
                path=display,
                status="loaded",
                title=document.metadata.title,
                pages=len(document.pages),
                blocks=document.block_count(),
                text_chars=document.text_chars(),
                document=document,
            )
        )
    return run


def _display_path(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()
