from __future__ import annotations

import argparse
import sys
from pathlib import Path

from document_metadata_store.config import load_app_config
from document_metadata_store.console import (
    format_chunk_run,
    format_load_run,
    format_preprocess_run,
    format_structure_run,
)
from document_metadata_store.pipeline.chunker import chunk_documents
from document_metadata_store.pipeline.loader import load_documents
from document_metadata_store.pipeline.preprocessor import preprocess_documents
from document_metadata_store.pipeline.structure import extract_structures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="document-metadata-store",
        description="Document Metadata Store — load, preprocess, extract structure, and chunk.",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.yaml (default: CONFIG_PATH or ./config.yaml)",
    )
    parser.add_argument(
        "--preview-blocks",
        type=int,
        default=None,
        metavar="N",
        help="Print the first N blocks of each document (default: PREVIEW_BLOCKS / config, else 0)",
    )
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    config_path = Path(args.config) if args.config else None
    app = load_app_config(config_path, cwd=cwd)
    preview = (
        args.preview_blocks
        if args.preview_blocks is not None
        else app.documents.preview_blocks
    )
    if preview < 0:
        parser.error("--preview-blocks must be >= 0")
    load_run = load_documents(app.documents, cwd=cwd)
    sys.stdout.write(format_load_run(load_run, cwd=cwd, preview_blocks=preview))
    prep_run = preprocess_documents(load_run, app.preprocessing, app.llm)
    sys.stdout.write("\n")
    sys.stdout.write(format_preprocess_run(prep_run, preview_blocks=preview))
    struct_run = extract_structures(prep_run, app.preprocessing, app.llm)
    sys.stdout.write("\n")
    sys.stdout.write(format_structure_run(struct_run, preview_blocks=preview))
    chunk_run = chunk_documents(struct_run, app.chunking)
    sys.stdout.write("\n")
    sys.stdout.write(format_chunk_run(chunk_run, preview_blocks=preview))
    failed = (
        load_run.counts()["failed"]
        + prep_run.counts()["failed"]
        + struct_run.counts()["failed"]
        + chunk_run.counts()["failed"]
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
