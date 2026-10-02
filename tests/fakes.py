"""In-memory stand-ins for the Zendesk HTTP session and the OpenAI client."""
from __future__ import annotations

import itertools
import json
from pathlib import Path
from types import SimpleNamespace

FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, payload=None, status=200, headers=None):
        self._payload = payload or {}
        self.status_code = status
        self.headers = headers or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    """Serves fixture pages; optional queue of error responses served first."""

    def __init__(self, pages=None, errors=None):
        self.pages = pages or [
            json.loads((FIXTURES / "articles_page1.json").read_text()),
            json.loads((FIXTURES / "articles_page2.json").read_text()),
        ]
        self.errors = list(errors or [])
        self.headers = {}
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if self.errors:
            return self.errors.pop(0)
        page = 2 if "page=2" in url else 1
        return FakeResponse(self.pages[page - 1])


class _Files:
    def __init__(self, store):
        self.s = store

    def create(self, file, purpose):
        fid = f"file-{next(self.s.counter)}"
        name, content, _ = file
        self.s.files_store[fid] = {"name": name, "content": content}
        return SimpleNamespace(id=fid)

    def delete(self, file_id):
        self.s.files_store.pop(file_id, None)
        self.s.deleted_files.append(file_id)


class _VSFiles:
    def __init__(self, store):
        self.s = store

    def create(self, vector_store_id, file_id, attributes=None, chunking_strategy=None):
        self.s.vs_files[file_id] = {"attributes": attributes or {}, "chunking": chunking_strategy, "status": "completed"}
        return SimpleNamespace(id=file_id, status="in_progress")

    def list(self, vector_store_id, limit=100):
        return [
            SimpleNamespace(id=fid, attributes=v["attributes"], status=v["status"]) for fid, v in self.s.vs_files.items()
        ]

    def retrieve(self, file_id, vector_store_id):
        return SimpleNamespace(id=file_id, status=self.s.vs_files[file_id]["status"])

    def delete(self, file_id, vector_store_id):
        self.s.vs_files.pop(file_id, None)


class _VectorStores:
    def __init__(self, store):
        self.s = store
        self.files = _VSFiles(store)

    def list(self, limit=100):
        return [SimpleNamespace(id=k, name=v) for k, v in self.s.stores.items()]

    def create(self, name):
        vid = f"vs_{len(self.s.stores) + 1}"
        self.s.stores[vid] = name
        return SimpleNamespace(id=vid)

    def retrieve(self, vector_store_id):
        n = len(self.s.vs_files)
        return SimpleNamespace(
            id=vector_store_id,
            usage_bytes=sum(len(self.s.files_store.get(f, {}).get("content", b"")) for f in self.s.vs_files),
            file_counts=SimpleNamespace(total=n, completed=n, failed=0, in_progress=0),
        )


class FakeOpenAI:
    def __init__(self):
        self.counter = itertools.count(1)
        self.files_store = {}
        self.stores = {}
        self.vs_files = {}
        self.deleted_files = []
        self.files = _Files(self)
        self.vector_stores = _VectorStores(self)
