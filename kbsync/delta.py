"""Decide what to upload by comparing local docs with what the vector store holds.

State lives in the vector store itself: every uploaded file carries the
attributes `article_id` and `content_hash`. The daily job therefore needs no
database or volume — a fresh container lists the store and diffs against it.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .cleaner import Doc


@dataclass(frozen=True)
class RemoteFile:
    file_id: str
    article_id: str
    content_hash: str
    status: str = "completed"


@dataclass
class Plan:
    added: list[Doc] = field(default_factory=list)
    updated: list[tuple[Doc, list[RemoteFile]]] = field(default_factory=list)
    skipped: list[Doc] = field(default_factory=list)
    stale: list[RemoteFile] = field(default_factory=list)  # article no longer published

    def counts(self) -> dict[str, int]:
        return {
            "added": len(self.added),
            "updated": len(self.updated),
            "skipped": len(self.skipped),
            "stale": len(self.stale),
        }


def build_plan(docs: list[Doc], remote: list[RemoteFile]) -> Plan:
    by_article: dict[str, list[RemoteFile]] = {}
    for rf in remote:
        by_article.setdefault(rf.article_id, []).append(rf)

    plan = Plan()
    seen: set[str] = set()
    for doc in docs:
        seen.add(doc.article_id)
        existing = by_article.get(doc.article_id, [])
        if not existing:
            plan.added.append(doc)
            continue
        healthy = [rf for rf in existing if rf.status != "failed"]
        # Exactly one healthy copy with the same hash -> nothing to do.
        # Anything else (changed content, failed ingest, duplicates left by an
        # interrupted run) -> re-upload and remove every old copy.
        if len(existing) == 1 and healthy and healthy[0].content_hash == doc.content_hash:
            plan.skipped.append(doc)
        else:
            plan.updated.append((doc, existing))

    for article_id, files in by_article.items():
        if article_id not in seen:
            plan.stale.extend(files)
    return plan
