"""Thin wrapper around the OpenAI Files + Vector Stores API."""
from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Iterable

from .cleaner import Doc
from .delta import RemoteFile

log = logging.getLogger(__name__)


def make_openai_client(api_key: str) -> Any:
    from openai import OpenAI  # imported lazily so tests run without the SDK

    return OpenAI(api_key=api_key, max_retries=5, timeout=120)


class VectorStore:
    def __init__(self, client: Any, vector_store_id: str, chunk_size: int, chunk_overlap: int, workers: int = 4):
        self.client = client
        self.id = vector_store_id
        self.workers = max(1, workers)
        self.chunking_strategy = {
            "type": "static",
            "static": {"max_chunk_size_tokens": chunk_size, "chunk_overlap_tokens": chunk_overlap},
        }

    # ---- lookup -----------------------------------------------------------
    @staticmethod
    def resolve(client: Any, vector_store_id: str, name: str) -> str:
        """Use the given id, else find a store by name, else create it.

        Looking it up by name lets a stateless scheduled container find the same
        store every day without anyone copying ids around.
        """
        if vector_store_id:
            return vector_store_id
        for vs in client.vector_stores.list(limit=100):
            if getattr(vs, "name", None) == name:
                log.info("Using existing vector store %s (%s)", vs.id, name)
                return vs.id
        vs = client.vector_stores.create(name=name)
        log.info("Created vector store %s (%s)", vs.id, name)
        return vs.id

    def list_remote(self) -> list[RemoteFile]:
        remote: list[RemoteFile] = []
        untracked = 0
        for f in self.client.vector_stores.files.list(vector_store_id=self.id, limit=100):
            attrs = getattr(f, "attributes", None) or {}
            if "article_id" not in attrs:
                untracked += 1
                continue
            remote.append(
                RemoteFile(
                    file_id=f.id,
                    article_id=str(attrs["article_id"]),
                    content_hash=str(attrs.get("content_hash", "")),
                    status=getattr(f, "status", "completed"),
                )
            )
        if untracked:
            log.info("Ignoring %d vector-store files not created by this tool", untracked)
        return remote

    # ---- mutations --------------------------------------------------------
    def upload(self, doc: Doc) -> str:
        uploaded = self.client.files.create(
            file=(doc.filename, doc.content.encode("utf-8"), "text/markdown"),
            purpose="assistants",
        )
        self.client.vector_stores.files.create(
            vector_store_id=self.id,
            file_id=uploaded.id,
            attributes={
                "article_id": doc.article_id,
                "content_hash": doc.content_hash,
                "url": doc.url[:512],
                "title": doc.title[:512],
                "updated_at": doc.updated_at,
            },
            chunking_strategy=self.chunking_strategy,
        )
        return uploaded.id

    def remove(self, file_id: str) -> None:
        """Detach from the store and delete the underlying file object."""
        try:
            self.client.vector_stores.files.delete(file_id=file_id, vector_store_id=self.id)
        finally:
            try:
                self.client.files.delete(file_id)
            except Exception as exc:  # already gone is fine
                log.debug("files.delete(%s) ignored: %s", file_id, exc)

    def upload_many(self, docs: Iterable[Doc]) -> dict[str, str]:
        docs = list(docs)
        if not docs:
            return {}
        with ThreadPoolExecutor(self.workers) as pool:
            ids = list(pool.map(self.upload, docs))
        return {d.article_id: fid for d, fid in zip(docs, ids)}

    def remove_many(self, file_ids: Iterable[str]) -> None:
        file_ids = list(file_ids)
        if file_ids:
            with ThreadPoolExecutor(self.workers) as pool:
                list(pool.map(self.remove, file_ids))

    def wait_for(self, file_ids: Iterable[str], timeout: float = 900, poll: float = 3) -> dict[str, int]:
        """Block until every new file leaves `in_progress`; return status counts."""
        pending = set(file_ids)
        result = {"completed": 0, "failed": 0, "in_progress": 0}
        deadline = time.monotonic() + timeout
        while pending and time.monotonic() < deadline:
            for fid in list(pending):
                status = self.client.vector_stores.files.retrieve(file_id=fid, vector_store_id=self.id).status
                if status != "in_progress":
                    pending.discard(fid)
                    result["completed" if status == "completed" else "failed"] += 1
            if pending:
                time.sleep(poll)
        result["in_progress"] = len(pending)
        return result

    def stats(self) -> dict[str, Any]:
        vs = self.client.vector_stores.retrieve(self.id)
        counts = getattr(vs, "file_counts", None)
        return {
            "total_files": getattr(counts, "total", None),
            "completed_files": getattr(counts, "completed", None),
            "failed_files": getattr(counts, "failed", None),
            "usage_bytes": getattr(vs, "usage_bytes", None),
        }
