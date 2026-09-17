from __future__ import annotations

from dataclasses import dataclass, field

from document_metadata_store.config import StoreConfig
from document_metadata_store.models import EmbeddedDocument
from document_metadata_store.pipeline.embedder import EmbedRun
from document_metadata_store.store.protocol import MetadataStore, PersistStats
from document_metadata_store.store.records import persist_document
from document_metadata_store.store.search import open_store


@dataclass
class StoreOutcome:
    path: str
    document: EmbeddedDocument
    records: int
    upserted: int
    skipped: int
    replaced: int


@dataclass
class StoreRun:
    provider: str
    collection: str
    persist_path: str
    outcomes: list[StoreOutcome] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "processed": len(self.outcomes),
            "records": sum(item.records for item in self.outcomes),
            "upserted": sum(item.upserted for item in self.outcomes),
            "skipped": sum(item.skipped for item in self.outcomes),
            "replaced": sum(item.replaced for item in self.outcomes),
            "failed": len(self.failed),
        }


def store_documents(
    embed_run: EmbedRun,
    config: StoreConfig,
    *,
    store: MetadataStore | None = None,
) -> StoreRun:
    run = StoreRun(
        provider=config.provider,
        collection=config.collection,
        persist_path=str(config.persist_path),
    )
    backend = store or open_store(config)
    for item in embed_run.outcomes:
        try:
            stats: PersistStats = persist_document(item.document, backend)
        except Exception as exc:  # noqa: BLE001 — continue batch
            run.failed.append((item.path, str(exc)))
            continue
        run.outcomes.append(
            StoreOutcome(
                path=item.path,
                document=item.document,
                records=stats.records,
                upserted=stats.upserted,
                skipped=stats.skipped,
                replaced=stats.replaced,
            )
        )
    return run
