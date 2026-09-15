from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_FIELD_NAMES = ("topic", "geography", "population", "time_period")


@dataclass(frozen=True)
class FieldSpec:
    name: str
    required: bool = False
    description: str = ""


@dataclass(frozen=True)
class MetadataSchema:
    version: int
    fields: tuple[FieldSpec, ...]
    path: Path | None = None

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(item.name for item in self.fields)


def default_schema() -> MetadataSchema:
    return MetadataSchema(
        version=1,
        fields=tuple(FieldSpec(name=name) for name in DEFAULT_FIELD_NAMES),
    )


def load_metadata_schema(path: Path) -> MetadataSchema:
    if not path.is_file():
        schema = default_schema()
        return MetadataSchema(version=schema.version, fields=schema.fields, path=path)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Metadata schema root must be a mapping: {path}")
    raw_fields = loaded.get("fields") or {}
    if not isinstance(raw_fields, dict) or not raw_fields:
        raise ValueError(f"Metadata schema must list fields: {path}")
    fields: list[FieldSpec] = []
    for name, spec in raw_fields.items():
        info = spec if isinstance(spec, dict) else {}
        required = bool(info.get("required", False))
        description = str(info.get("description") or "")
        fields.append(FieldSpec(name=str(name), required=required, description=description))
    version = loaded.get("version", 1)
    try:
        version_n = int(version)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"metadata schema version must be an integer, got {version!r}") from exc
    return MetadataSchema(version=version_n, fields=tuple(fields), path=path)
