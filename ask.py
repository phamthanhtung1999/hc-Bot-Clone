"""Sanity check from the terminal: ask OptiBot a question against the vector store.

    python ask.py "How do I add a YouTube video?"

Uses the Responses API + file_search (the Assistants API was retired on
2026-08-26; the Playground equivalent is a saved Prompt with File search).
"""
from __future__ import annotations

import sys

from kbsync.config import Settings
from kbsync.prompt import SYSTEM_PROMPT
from kbsync.uploader import VectorStore, make_openai_client


def main() -> int:
    question = " ".join(sys.argv[1:]) or "How do I add a YouTube video?"
    s = Settings.from_env()
    client = make_openai_client(s.api_key)
    vs_id = VectorStore.resolve(client, s.vector_store_id, s.vector_store_name)

    resp = client.responses.create(
        model=s.model,
        instructions=SYSTEM_PROMPT,
        input=question,
        tools=[{"type": "file_search", "vector_store_ids": [vs_id], "max_num_results": 8}],
    )
    print(f"Q: {question}\n")
    print(resp.output_text)

    cited = []
    for item in resp.output:
        for part in getattr(item, "content", None) or []:
            for ann in getattr(part, "annotations", None) or []:
                if getattr(ann, "type", "") == "file_citation" and ann.filename not in cited:
                    cited.append(ann.filename)
    if cited:
        print("\nRetrieved files:", ", ".join(cited))
    return 0


if __name__ == "__main__":
    sys.exit(main())
