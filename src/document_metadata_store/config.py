from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_INPUT_PATH = Path("documents")
DEFAULT_PREVIEW_BLOCKS = 0
DEFAULT_LLM_MODEL = "claude-sonnet-5"
DEFAULT_CHUNK_TARGET = 1000
DEFAULT_CHUNK_MAX = 1500
DEFAULT_CHUNK_MIN = 300
DEFAULT_CHUNK_OVERLAP = 100
DEFAULT_METADATA_SCHEMA_PATH = Path("metadata_schema.yaml")
DEFAULT_BATCH_SIZE = 50

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
class ChunkingConfig:
    strategy: str = "structural"
    target_size: int = DEFAULT_CHUNK_TARGET
    max_size: int = DEFAULT_CHUNK_MAX
    min_size: int = DEFAULT_CHUNK_MIN
    overlap: int = DEFAULT_CHUNK_OVERLAP


@dataclass(frozen=True)
class MetadataConfig:
    enabled: bool = True
    schema_path: Path = DEFAULT_METADATA_SCHEMA_PATH
    batch_size: int = DEFAULT_BATCH_SIZE


@dataclass(frozen=True)
class AppConfig:
    documents: DocumentsConfig
    preprocessing: PreprocessingConfig
    llm: LlmConfig
    chunking: ChunkingConfig
    metadata: MetadataConfig


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

    llm = LlmConfig(provider=provider, model=model, api_key=api_key)
    chunking = _chunking_config(data.get("chunking") or {})
    metadata = _metadata_config(data.get("metadata") or {}, data.get("processing") or {}, root)

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
        llm=llm,
        chunking=chunking,
        metadata=metadata,
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


def _chunking_config(raw: dict) -> ChunkingConfig:
    target = _chunk_int("CHUNK_TARGET_SIZE", raw.get("target_size", DEFAULT_CHUNK_TARGET), "target_size")
    maximum = _chunk_int("CHUNK_MAX_SIZE", raw.get("max_size", DEFAULT_CHUNK_MAX), "max_size")
    minimum = _chunk_int("CHUNK_MIN_SIZE", raw.get("min_size", DEFAULT_CHUNK_MIN), "min_size")
    overlap = _chunk_int("CHUNK_OVERLAP", raw.get("overlap", DEFAULT_CHUNK_OVERLAP), "overlap")
    if target <= 0 or maximum <= 0 or minimum < 0 or overlap < 0:
        raise ValueError("chunking sizes must be non-negative; target and max must be > 0")
    if minimum > maximum:
        raise ValueError("chunking min_size must be <= max_size")
    if minimum > target:
        raise ValueError("chunking min_size must be <= target_size")
    if target > maximum:
        raise ValueError("chunking target_size must be <= max_size")
    strategy = str(raw.get("strategy") or "structural")
    return ChunkingConfig(
        strategy=strategy,
        target_size=target,
        max_size=maximum,
        min_size=minimum,
        overlap=overlap,
    )


def _chunk_int(env_name: str, raw, field: str) -> int:
    env = os.environ.get(env_name)
    if env is not None and env != "":
        raw = env
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"chunking.{field} must be an integer, got {raw!r}") from exc


def _metadata_config(raw: dict, processing: dict, root: Path) -> MetadataConfig:
    enabled = raw.get("enabled", True)
    env_enabled = os.environ.get("METADATA_ENABLED")
    if env_enabled is not None and env_enabled != "":
        enabled = env_enabled
    if isinstance(enabled, str):
        enabled = enabled.lower() in {"1", "true", "yes"}
    schema_raw = (
        os.environ.get("METADATA_SCHEMA_PATH")
        or raw.get("schema")
        or DEFAULT_METADATA_SCHEMA_PATH
    )
    schema_path = Path(schema_raw)
    if not schema_path.is_absolute():
        schema_path = root / schema_path
    batch_size = _positive_int(
        "PROCESSING_BATCH_SIZE",
        processing.get("batch_size", DEFAULT_BATCH_SIZE),
        "processing.batch_size",
    )
    return MetadataConfig(
        enabled=bool(enabled),
        schema_path=schema_path.resolve(),
        batch_size=batch_size,
    )


def _positive_int(env_name: str, raw, field: str) -> int:
    env = os.environ.get(env_name)
    if env is not None and env != "":
        raw = env
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer, got {raw!r}") from exc
    if value < 1:
        raise ValueError(f"{field} must be >= 1")
    return value
