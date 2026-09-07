from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_INPUT_PATH = Path("documents")
DEFAULT_PREVIEW_BLOCKS = 0


@dataclass(frozen=True)
class DocumentsConfig:
    input_path: Path
    recursive: bool = True
    preview_blocks: int = DEFAULT_PREVIEW_BLOCKS


def load_documents_config(
    config_path: Path | None = None,
    *,
    cwd: Path | None = None,
) -> DocumentsConfig:
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

    return DocumentsConfig(
        input_path=input_path.resolve(),
        recursive=bool(recursive),
        preview_blocks=preview_blocks,
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
