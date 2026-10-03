"""Runtime settings, read from environment variables (and .env when present)."""
from __future__ import annotations

import os
from dataclasses import dataclass


def _load_dotenv() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:  # optional dependency
        return
    load_dotenv()


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    base_url: str = "https://support.optisigns.com"
    locale: str = "en-us"
    output_dir: str = "articles"
    summary_path: str = "artifacts/last_run.json"
    vector_store_id: str = ""
    vector_store_name: str = "optibot-kb"
    max_articles: int = 0  # 0 = every published article
    chunk_size: int = 1200  # tokens, OpenAI static chunking
    chunk_overlap: int = 200
    upload_workers: int = 4
    prune: bool = False  # delete vector-store files whose article disappeared
    model: str = "gpt-5-mini"  # only used by ask.py
    # Optional public run log: every run updates this GitHub Gist (see kbsync/publish.py).
    gist_id: str = ""
    gist_token: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv()
        env = os.environ.get
        return cls(
            # The brief runs `docker run -e API_KEY=...`; OPENAI_API_KEY also works.
            api_key=env("API_KEY") or env("OPENAI_API_KEY") or "",
            base_url=(env("HELP_CENTER_URL") or cls.base_url).rstrip("/"),
            locale=env("HELP_CENTER_LOCALE") or cls.locale,
            output_dir=env("OUTPUT_DIR") or cls.output_dir,
            summary_path=env("SUMMARY_PATH") or cls.summary_path,
            vector_store_id=env("VECTOR_STORE_ID") or "",
            vector_store_name=env("VECTOR_STORE_NAME") or cls.vector_store_name,
            max_articles=int(env("MAX_ARTICLES") or 0),
            chunk_size=int(env("CHUNK_SIZE") or cls.chunk_size),
            chunk_overlap=int(env("CHUNK_OVERLAP") or cls.chunk_overlap),
            upload_workers=int(env("UPLOAD_WORKERS") or cls.upload_workers),
            prune=_bool(env("PRUNE")),
            model=env("MODEL") or cls.model,
            gist_id=env("LOG_GIST_ID") or "",
            gist_token=env("LOG_GIST_TOKEN") or "",
        )
