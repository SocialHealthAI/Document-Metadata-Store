from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_INPUT_PATH = Path("documents")
DEFAULT_PREVIEW_BLOCKS = 0
DEFAULT_LLM_MODEL = "claude-sonnet-5"

DEFAULT_EXCLUDE_SECTIONS = (
    "cover",
    "foreword",
    "acknowledgements",
    "table_of_contents",
    "list_of_figures",
    "list_of_tables",
    "abbreviations",
    "index",
)

DEFAULT_ALIASES: dict[str, tuple[str, ...]] = {
    "cover": ("cover", "title page"),
    "foreword": ("foreword", "forward", "message from", "preface"),
    "acknowledgements": (
        "acknowledgements",
        "acknowledgments",
        "acknowledgement",
        "acknowledgment",
    ),
    "table_of_contents": ("contents", "table of contents", "toc"),
    "list_of_figures": ("list of figures", "figures list"),
    "list_of_tables": ("list of tables", "tables list"),
    "abbreviations": ("abbreviations", "acronyms", "glossary", "abbreviations and acronyms"),
    "references": (
        "references",
        "bibliography",
        "sources and notes",
        "works cited",
    ),
    "index": ("index",),
}


@dataclass(frozen=True)
class DocumentsConfig:
    input_path: Path
    recursive: bool = True
    preview_blocks: int = DEFAULT_PREVIEW_BLOCKS


@dataclass(frozen=True)
class LlmConfig:
    provider: str | None = None
    model: str = DEFAULT_LLM_MODEL
    api_key: str | None = None

    def enabled(self) -> bool:
        return bool(self.provider and self.api_key)


@dataclass(frozen=True)
class PreprocessingConfig:
    enabled: bool = True
    exclude_sections: tuple[str, ...] = DEFAULT_EXCLUDE_SECTIONS
    aliases: dict[str, tuple[str, ...]] = field(default_factory=lambda: dict(DEFAULT_ALIASES))
    figures_mode: str = "captions_only"
    tables_preserve: bool = True


@dataclass(frozen=True)
class AppConfig:
    documents: DocumentsConfig
    preprocessing: PreprocessingConfig
    llm: LlmConfig


def load_documents_config(
    config_path: Path | None = None,
    *,
    cwd: Path | None = None,
) -> DocumentsConfig:
    return load_app_config(config_path, cwd=cwd).documents


def load_app_config(
    config_path: Path | None = None,
    *,
    cwd: Path | None = None,
) -> AppConfig:
    root = cwd or Path.cwd()
    path = Path(os.environ.get("CONFIG_PATH", config_path or DEFAULT_CONFIG_PATH))
    if not path.is_absolute():
        path = root / path

    data: dict = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Config root must be a mapping: {path}")
        data = loaded

    documents = data.get("documents") or {}
    raw_input = os.environ.get("DOCUMENTS_INPUT_PATH") or documents.get(
        "input_path", DEFAULT_INPUT_PATH
    )
    input_path = Path(raw_input)
    if not input_path.is_absolute():
        input_path = root / input_path

    recursive = documents.get("recursive", True)
    if isinstance(recursive, str):
        recursive = recursive.lower() in {"1", "true", "yes"}

    preview_blocks = _preview_blocks(documents.get("preview_blocks", DEFAULT_PREVIEW_BLOCKS))

    prep_raw = data.get("preprocessing") or {}
    enabled = prep_raw.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.lower() in {"1", "true", "yes"}

    exclude = prep_raw.get("exclude_sections") or list(DEFAULT_EXCLUDE_SECTIONS)
    exclude_sections = tuple(str(item) for item in exclude)

    aliases = dict(DEFAULT_ALIASES)
    raw_aliases = prep_raw.get("section_aliases") or {}
    if isinstance(raw_aliases, dict):
        for key, values in raw_aliases.items():
            if isinstance(values, list):
                aliases[str(key)] = tuple(str(v) for v in values)

    figures = prep_raw.get("figures") or {}
    tables = prep_raw.get("tables") or {}
    figures_mode = str(figures.get("mode", "captions_only"))
    tables_preserve = tables.get("preserve", True)
    if isinstance(tables_preserve, str):
        tables_preserve = tables_preserve.lower() in {"1", "true", "yes"}

    provider = os.environ.get("LLM_PROVIDER") or None
    if provider == "":
        provider = None
    model = os.environ.get("LLM_MODEL") or DEFAULT_LLM_MODEL
    api_key = os.environ.get("LLM_API_KEY") or None
    if api_key == "":
        api_key = None

    return AppConfig(
        documents=DocumentsConfig(
            input_path=input_path.resolve(),
            recursive=bool(recursive),
            preview_blocks=preview_blocks,
        ),
        preprocessing=PreprocessingConfig(
            enabled=bool(enabled),
            exclude_sections=exclude_sections,
            aliases=aliases,
            figures_mode=figures_mode,
            tables_preserve=bool(tables_preserve),
        ),
        llm=LlmConfig(provider=provider, model=model, api_key=api_key),
    )


def _preview_blocks(raw) -> int:
    env = os.environ.get("PREVIEW_BLOCKS")
    if env is not None and env != "":
        raw = env
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"preview_blocks must be an integer, got {raw!r}") from exc
    if value < 0:
        raise ValueError("preview_blocks must be >= 0")
    return value
