"""Daily job: re-scrape the help center and push only new/changed articles.

    python main.py                # full run
    python main.py --scrape-only  # just write Markdown to ./articles
    python main.py --dry-run      # scrape + diff against the store, no upload

If LOG_GIST_ID and LOG_GIST_TOKEN are set, the run log and summary are also
published to that GitHub Gist so the job's logs have a public URL.
"""
from __future__ import annotations

import argparse
import dataclasses
import io
import json
import logging
import sys

from kbsync.config import Settings
from kbsync.pipeline import run, scrape

log = logging.getLogger("kbsync")


def _setup_logging(verbose: bool) -> io.StringIO:
    buffer = io.StringIO()
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    for stream in (sys.stdout, buffer):  # console for the platform, buffer for the Gist
        handler = logging.StreamHandler(stream)
        handler.setFormatter(fmt)
        root.addHandler(handler)
    for noisy in ("httpx", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return buffer


def _publish(settings: Settings, buffer: io.StringIO, status: str, summary) -> None:
    if not (settings.gist_id and settings.gist_token):
        return
    from kbsync.publish import publish_to_gist

    data = summary.__dict__ if summary is not None else None
    try:
        url = publish_to_gist(
            settings.gist_id,
            settings.gist_token,
            run_log=buffer.getvalue(),
            summary_json=json.dumps(data, indent=2) if data else "{}",
            status=status,
            summary=data,
        )
        log.info("Run log published: %s", url)
    except Exception as exc:  # publishing must never fail the sync itself
        log.warning("Could not publish run log to Gist: %s", exc)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="max articles to fetch (default: all)")
    parser.add_argument("--scrape-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    buffer = _setup_logging(args.verbose)
    settings = Settings.from_env()
    if args.limit is not None:
        settings = dataclasses.replace(settings, max_articles=args.limit)

    summary, status, code = None, "success", 0
    try:
        if args.scrape_only:
            scrape(settings)
            return 0
        summary = run(settings, dry_run=args.dry_run)
    except SystemExit as exc:  # e.g. missing API key
        log.error("%s", exc)
        status, code = "failed", 1
    except Exception:
        log.exception("Run failed")
        status, code = "failed", 1
    if not args.scrape_only:
        _publish(settings, buffer, status, summary)
    return code


if __name__ == "__main__":
    sys.exit(main())
