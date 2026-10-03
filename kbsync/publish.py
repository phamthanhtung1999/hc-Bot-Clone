"""Publish each run's log to a public GitHub Gist.

Hosting consoles (DigitalOcean, Render, ...) only show job logs to account
members. A secret Gist gives reviewers a public, stable URL; every run becomes
a new Gist revision, so the revision history doubles as the daily run history.

Files written to the Gist:
  run.log        full log of the latest run
  last_run.json  machine-readable summary of the latest run
  history.tsv    one line per run (appended)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

API = "https://api.github.com/gists/{gist_id}"
HISTORY = "history.tsv"
HISTORY_HEADER = "finished_at_utc\tstatus\tscraped\tadded\tupdated\tskipped\tfiles_embedded\tchunks_embedded\tduration_s\n"


def history_line(status: str, summary: dict | None) -> str:
    s = summary or {}
    cols = [
        datetime.now(timezone.utc).isoformat(timespec="seconds"),
        status,
        *(str(s.get(k, "")) for k in ("scraped", "added", "updated", "skipped", "files_embedded", "chunks_embedded", "duration_s")),
    ]
    return "\t".join(cols) + "\n"


def publish_to_gist(
    gist_id: str,
    token: str,
    run_log: str,
    summary_json: str,
    status: str,
    summary: dict | None = None,
    session: requests.Session | None = None,
    timeout: float = 20,
) -> str:
    """Update the Gist and return its public URL. Raises on HTTP errors."""
    http = session or requests.Session()
    url = API.format(gist_id=gist_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    current = http.get(url, headers=headers, timeout=timeout)
    current.raise_for_status()
    files = current.json().get("files", {})
    history = (files.get(HISTORY) or {}).get("content") or HISTORY_HEADER
    history += history_line(status, summary)

    resp = http.patch(
        url,
        headers=headers,
        json={
            "description": f"kb-sync daily job: last run {status} at "
            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "files": {
                "run.log": {"content": run_log or "(empty)"},
                "last_run.json": {"content": summary_json or "{}"},
                HISTORY: {"content": history},
            },
        },
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("html_url", f"https://gist.github.com/{gist_id}")
