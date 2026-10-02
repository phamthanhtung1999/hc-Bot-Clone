"""Chunk-count estimation that mirrors OpenAI's `static` chunking strategy.

The vector-store API does not report how many chunks it produced, so we count
tokens locally with the same window/overlap and log the result.
"""
from __future__ import annotations

import math
from functools import lru_cache


@lru_cache(maxsize=1)
def _encoder():
    try:
        import tiktoken

        return tiktoken.get_encoding("o200k_base")
    except Exception:  # tiktoken missing or encoding not downloadable
        return None


def count_tokens(text: str) -> int:
    enc = _encoder()
    if enc is not None:
        return len(enc.encode(text, disallowed_special=()))
    return max(1, math.ceil(len(text) / 4))  # ~4 chars/token fallback


def chunks_for_tokens(n_tokens: int, size: int, overlap: int) -> int:
    """Windows of `size` tokens advancing by `size - overlap`."""
    if n_tokens <= 0:
        return 0
    if n_tokens <= size:
        return 1
    step = size - overlap
    return 1 + math.ceil((n_tokens - size) / step)


def estimate_chunks(text: str, size: int, overlap: int) -> int:
    return chunks_for_tokens(count_tokens(text), size, overlap)
