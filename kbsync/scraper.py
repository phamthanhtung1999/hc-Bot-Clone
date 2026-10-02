"""Fetch published articles from a Zendesk Help Center through its public API.

The Help Center API returns the article body as clean HTML (no site nav, header,
footer or ads), which is why we use it instead of crawling rendered pages.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Iterator

import requests

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class Article:
    id: int
    title: str
    html_url: str
    body: str
    updated_at: str = ""
    section_id: int | None = None
    labels: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_api(cls, raw: dict) -> "Article":
        return cls(
            id=int(raw["id"]),
            title=(raw.get("title") or "").strip(),
            html_url=raw.get("html_url") or "",
            body=raw.get("body") or "",
            updated_at=raw.get("updated_at") or "",
            section_id=raw.get("section_id"),
            labels=tuple(raw.get("label_names") or ()),
        )


class ZendeskClient:
    def __init__(
        self,
        base_url: str,
        locale: str = "en-us",
        session: requests.Session | None = None,
        per_page: int = 100,
        timeout: float = 30,
        max_retries: int = 5,
        backoff: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.locale = locale
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "kbsync/1.0")
        self.per_page = per_page
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff = backoff

    def _get(self, url: str) -> dict:
        for attempt in range(self.max_retries + 1):
            resp = self.session.get(url, timeout=self.timeout)
            if resp.status_code not in RETRY_STATUS:
                resp.raise_for_status()
                return resp.json()
            if attempt == self.max_retries:
                resp.raise_for_status()
            wait = float(resp.headers.get("Retry-After") or self.backoff * 2**attempt)
            log.warning("HTTP %s from %s, retrying in %.1fs", resp.status_code, url, wait)
            time.sleep(wait)
        raise RuntimeError("unreachable")

    def iter_articles(self, limit: int = 0) -> Iterator[Article]:
        """Yield published articles, following `next_page` until done or `limit` hit."""
        url: str | None = (
            f"{self.base_url}/api/v2/help_center/{self.locale}/articles.json"
            f"?per_page={self.per_page}&sort_by=position&sort_order=asc"
        )
        yielded = 0
        while url:
            page = self._get(url)
            for raw in page.get("articles", []):
                if raw.get("draft"):
                    continue
                yield Article.from_api(raw)
                yielded += 1
                if limit and yielded >= limit:
                    return
            url = page.get("next_page")
