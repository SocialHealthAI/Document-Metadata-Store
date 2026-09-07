from __future__ import annotations

import argparse
import sys
from pathlib import Path

from document_metadata_store.config import load_documents_config
from document_metadata_store.console import format_load_run
from document_metadata_store.pipeline.loader import load_documents


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="document-metadata-store",
        description="Document Metadata Store — document load (PDFs first).",
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
        help="Print the first N blocks of each loaded document (default: PREVIEW_BLOCKS / config, else 0)",
    )
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    config_path = Path(args.config) if args.config else None
    config = load_documents_config(config_path, cwd=cwd)
    preview = args.preview_blocks if args.preview_blocks is not None else config.preview_blocks
    if preview < 0:
        parser.error("--preview-blocks must be >= 0")
    run = load_documents(config, cwd=cwd)
    sys.stdout.write(format_load_run(run, cwd=cwd, preview_blocks=preview))
    return 1 if run.counts()["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
