"""Daily job: re-scrape the help center and push only new/changed articles.

    python main.py                # full run
    python main.py --scrape-only  # just write Markdown to ./articles
    python main.py --dry-run      # scrape + diff against the store, no upload
"""
from __future__ import annotations

import argparse
import dataclasses
import logging
import sys

from kbsync.config import Settings
from kbsync.pipeline import run, scrape


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="max articles to fetch (default: all)")
    parser.add_argument("--scrape-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )
    for noisy in ("httpx", "openai", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings = Settings.from_env()
    if args.limit is not None:
        settings = dataclasses.replace(settings, max_articles=args.limit)

    try:
        if args.scrape_only:
            scrape(settings)
        else:
            run(settings, dry_run=args.dry_run)
    except SystemExit:
        raise
    except Exception:
        logging.getLogger("kbsync").exception("Run failed")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
