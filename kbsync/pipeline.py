"""scrape → markdown → diff → upload delta → log."""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .chunks import estimate_chunks
from .cleaner import Doc, render
from .config import Settings
from .delta import build_plan
from .scraper import ZendeskClient
from .uploader import VectorStore

log = logging.getLogger("kbsync")


@dataclass
class RunSummary:
    started_at: str
    scraped: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    stale: int = 0
    deleted: int = 0
    files_embedded: int = 0
    chunks_embedded: int = 0
    chunks_total_estimate: int = 0
    ingest: dict[str, int] = field(default_factory=dict)
    vector_store_id: str = ""
    vector_store: dict[str, Any] = field(default_factory=dict)
    duration_s: float = 0.0
    dry_run: bool = False

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


def scrape(settings: Settings, zendesk: ZendeskClient | None = None) -> list[Doc]:
    zendesk = zendesk or ZendeskClient(settings.base_url, settings.locale)
    docs = [render(a) for a in zendesk.iter_articles(limit=settings.max_articles)]
    out = Path(settings.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    for doc in docs:
        (out / doc.filename).write_text(doc.content, encoding="utf-8")
    log.info("Scraped %d articles -> %s/", len(docs), out)
    return docs


def run(
    settings: Settings,
    *,
    client: Any = None,
    zendesk: ZendeskClient | None = None,
    dry_run: bool = False,
) -> RunSummary:
    t0 = time.monotonic()
    summary = RunSummary(started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"), dry_run=dry_run)

    docs = scrape(settings, zendesk)
    summary.scraped = len(docs)
    chunks = {d.article_id: estimate_chunks(d.content, settings.chunk_size, settings.chunk_overlap) for d in docs}
    summary.chunks_total_estimate = sum(chunks.values())

    if client is None:
        if not settings.api_key:
            raise SystemExit("API_KEY / OPENAI_API_KEY is not set (see .env.sample)")
        from .uploader import make_openai_client

        client = make_openai_client(settings.api_key)

    vs_id = VectorStore.resolve(client, settings.vector_store_id, settings.vector_store_name)
    store = VectorStore(client, vs_id, settings.chunk_size, settings.chunk_overlap, settings.upload_workers)
    summary.vector_store_id = vs_id

    plan = build_plan(docs, store.list_remote())
    c = plan.counts()
    summary.added, summary.updated, summary.skipped, summary.stale = c["added"], c["updated"], c["skipped"], c["stale"]
    log.info("Delta: added=%(added)d updated=%(updated)d skipped=%(skipped)d stale=%(stale)d", c)
    for doc in plan.added:
        log.info("  + %s", doc.filename)
    for doc, _ in plan.updated:
        log.info("  ~ %s", doc.filename)

    if dry_run:
        log.info("Dry run: nothing uploaded")
    else:
        to_upload = plan.added + [doc for doc, _ in plan.updated]
        new_ids = store.upload_many(to_upload)
        # Replace-then-delete: old copies are removed only after the new file exists,
        # so the assistant never loses an article mid-run.
        old_ids = [rf.file_id for _, olds in plan.updated for rf in olds]
        if settings.prune:
            old_ids += [rf.file_id for rf in plan.stale]
        store.remove_many(old_ids)
        summary.deleted = len(old_ids)

        summary.ingest = store.wait_for(new_ids.values())
        summary.files_embedded = len(new_ids)
        summary.chunks_embedded = sum(chunks[d.article_id] for d in to_upload)
        summary.vector_store = store.stats()

    summary.duration_s = round(time.monotonic() - t0, 1)
    log.info(
        "Embedded %d files (~%d chunks, %d tokens/chunk, %d overlap); store now ~%d chunks across %d articles",
        summary.files_embedded,
        summary.chunks_embedded,
        settings.chunk_size,
        settings.chunk_overlap,
        summary.chunks_total_estimate,
        summary.scraped,
    )
    log.info("RESULT added=%d updated=%d skipped=%d", summary.added, summary.updated, summary.skipped)

    path = Path(settings.summary_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary.to_json(), encoding="utf-8")
    return summary
